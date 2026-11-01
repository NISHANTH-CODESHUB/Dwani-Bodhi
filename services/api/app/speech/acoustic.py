"""Acoustic model backends producing CTC log-probabilities over a character vocabulary.

Backends:
  * `Wav2Vec2Backend` — real model (default `ai4bharat/indicwav2vec-hindi`), needs the `speech` extra.
  * `SimulatedBackend` — deterministic log-probs synthesised from a known utterance; used by tests,
    the eval harness self-check and the offline demo. Never used to score real children.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from .devanagari import normalize

log = logging.getLogger(__name__)


class AcousticModel(Protocol):
    name: str
    blank_id: int
    delimiter_id: int | None
    frames_per_second: float
    vocab: dict[str, int]
    nonspeech_ids: set[int]  # blank, word delimiter and special tokens

    def log_probs(self, waveform_16k: np.ndarray) -> np.ndarray: ...

    def tokenize(self, text: str) -> list[int]: ...

    def detokenize(self, ids: list[int]) -> str: ...


class _VocabMixin:
    vocab: dict[str, int]
    delimiter_id: int | None

    def tokenize(self, text: str) -> list[int]:
        ids: list[int] = []
        text = normalize(text)
        i = 0
        while i < len(text):
            ch = text[i]
            if ch == " ":
                if self.delimiter_id is not None:
                    ids.append(self.delimiter_id)
                i += 1
                continue
            pair = text[i:i + 2]  # e.g. base + nukta, when the model has the precomposed letter
            if len(pair) == 2 and pair in self.vocab:
                ids.append(self.vocab[pair])
                i += 2
                continue
            tid = self.vocab.get(ch)
            if tid is None:
                log.debug("char %r not in acoustic vocab; skipped", ch)
            else:
                ids.append(tid)
            i += 1
        return ids

    def detokenize(self, ids: list[int]) -> str:
        inv = {v: k for k, v in self.vocab.items()}
        return "".join(" " if i == self.delimiter_id else inv.get(i, "") for i in ids)


class Wav2Vec2Backend(_VocabMixin):
    def __init__(self, model_id: str, device: str = "cpu") -> None:
        try:
            import torch
            from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor
        except ImportError as e:  # pragma: no cover - depends on optional extra
            raise RuntimeError("Install the speech extra: pip install -e '.[speech]'") from e
        import torch

        self._torch = torch
        self.name = model_id
        self.processor = Wav2Vec2Processor.from_pretrained(model_id)
        self.model = Wav2Vec2ForCTC.from_pretrained(model_id).to(device).eval()
        self.device = device
        raw_vocab: dict[str, int] = self.processor.tokenizer.get_vocab()
        self.delimiter_id = raw_vocab.get("|")
        self.vocab = {}
        for k, v in raw_vocab.items():
            nk = normalize(k) if k != "|" else k
            if len(k) == 1 and 1 <= len(nk) <= 2 or k == "|":
                self.vocab[nk] = v
        self.frames_per_second = 50.0  # wav2vec2: 20 ms stride
        specials = {v for k, v in raw_vocab.items() if len(k) > 1 and k.startswith("<")}
        # The CTC blank is not reliably declared: fairseq-converted models use <s> (id 0) while their
        # config says <pad>. Detect it empirically as the token dominating near-silence.
        configured = self.model.config.pad_token_id
        noise = np.random.default_rng(0).normal(0, 1e-3, 16000).astype(np.float32)
        ids, counts = np.unique(self.log_probs(noise).argmax(axis=1), return_counts=True)
        dominant = int(ids[counts.argmax()])
        self.blank_id = dominant if dominant in specials or dominant == configured else int(configured)
        if self.blank_id != configured:
            log.warning("CTC blank detected as id %s (config says %s)", self.blank_id, configured)
        self.nonspeech_ids = specials | {self.blank_id} | ({self.delimiter_id} if self.delimiter_id is not None else set())

    def log_probs(self, waveform_16k: np.ndarray) -> np.ndarray:
        torch = self._torch
        inputs = self.processor(waveform_16k, sampling_rate=16000, return_tensors="pt")
        with torch.inference_mode():
            logits = self.model(inputs.input_values.to(self.device)).logits[0]
        return torch.log_softmax(logits.float(), dim=-1).cpu().numpy()


@dataclass
class SimulatedUtterance:
    text: str  # what the "speaker" actually says
    frames_per_char: int = 4
    gap_frames: int = 3  # blank frames between characters
    lead_silence: int = 10
    word_pause: int = 8
    confidence: float = 0.9  # probability mass on the spoken char per frame
    seed: int = 0


class SimulatedBackend(_VocabMixin):
    """Builds plausible CTC posteriors for a known utterance. `log_probs` ignores the waveform and
    uses the utterance queued via `say()`; this keeps scoring code paths identical to production."""

    name = "simulated"
    frames_per_second = 50.0

    def __init__(self, alphabet: str | None = None) -> None:
        chars = alphabet or (
            "अआइईउऊऋएऐओऔऑकखगघङचछजझञटठडढणतथदधनपफबभमयरलवशषसह"
            "ािीुूृेैोौॉंँः़्"
        )
        self.vocab = {"<blank>": 0, "|": 1}
        for ch in chars:
            self.vocab.setdefault(ch, len(self.vocab))
        self.blank_id = 0
        self.delimiter_id = 1
        self.nonspeech_ids = {0, 1}
        self._pending: SimulatedUtterance | None = None
        self._lock = threading.Lock()

    def say(self, utt: SimulatedUtterance) -> None:
        with self._lock:
            self._pending = utt

    def synthesize(self, utt: SimulatedUtterance) -> np.ndarray:
        rng = np.random.default_rng(utt.seed)
        V = len(self.vocab)
        frames: list[int] = [self.blank_id] * utt.lead_silence
        for ch in normalize(utt.text):
            if ch == " ":
                frames += [self.delimiter_id] * 2 + [self.blank_id] * utt.word_pause
                continue
            tid = self.vocab.get(ch)
            if tid is None:
                continue
            frames += [tid] * utt.frames_per_char + [self.blank_id] * utt.gap_frames
        frames += [self.blank_id] * utt.lead_silence
        T = len(frames)
        probs = rng.dirichlet(np.ones(V) * 0.5, size=T) * (1 - utt.confidence)
        probs[np.arange(T), frames] += utt.confidence
        probs /= probs.sum(axis=1, keepdims=True)
        return np.log(probs)

    def log_probs(self, waveform_16k: np.ndarray) -> np.ndarray:
        with self._lock:
            utt = self._pending
        if utt is None:
            return np.log(np.full((max(1, len(waveform_16k) // 320), len(self.vocab)), 1.0 / len(self.vocab)))
        return self.synthesize(utt)


_MODEL: AcousticModel | None = None
_MODEL_LOCK = threading.Lock()


def get_acoustic_model() -> AcousticModel:
    """Process-wide singleton, configured by settings.SPEECH_BACKEND."""
    global _MODEL
    if _MODEL is None:
        with _MODEL_LOCK:
            if _MODEL is None:
                from ..config import get_settings

                s = get_settings()
                if s.speech_backend == "wav2vec2":
                    _MODEL = Wav2Vec2Backend(s.speech_model_id, s.speech_device)
                else:
                    _MODEL = SimulatedBackend()
                log.info("acoustic model loaded: %s", _MODEL.name)
    return _MODEL


def set_acoustic_model(model: AcousticModel | None) -> None:
    global _MODEL
    _MODEL = model
