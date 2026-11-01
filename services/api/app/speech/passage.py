"""Oral reading fluency scoring for connected text (guide §6.1.4).

1. Forced-align the whole expected passage (CTC Viterbi) to locate each word.
2. Words whose aligned frames carry almost no evidence are treated as not read (SKIPPED).
3. Each located word is re-scored with ECCL on its own segment (with padding).
4. WCPM is reported as a range: low counts UNSURE as wrong, high counts them as right.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

import numpy as np

from .acoustic import AcousticModel
from .ctc import forced_align
from .devanagari import words as split_words
from .eccl import CORRECT_STATUSES, SKIPPED, UNSURE, EcclConfig, WordVerdict, score_word
from .regions import STANDARD, RegionProfile


@dataclass
class PassageConfig:
    pad_ms: float = 150.0
    presence_min_prob: float = 0.08  # mean per-frame prob of the word's chars along the path
    time_limit_s: float = 60.0
    eccl: EcclConfig = field(default_factory=EcclConfig)


@dataclass
class PassageVerdict:
    n_words: int
    words: list[dict]
    attempted: int
    correct: int
    unsure: int
    reading_seconds: float
    wcpm: float
    wcpm_low: float
    wcpm_high: float
    accuracy: float

    def to_dict(self) -> dict:
        return asdict(self)


def score_passage(
    log_probs: np.ndarray,
    passage: str,
    model: AcousticModel,
    profile: RegionProfile = STANDARD,
    cfg: PassageConfig | None = None,
) -> PassageVerdict:
    cfg = cfg or PassageConfig()
    fps = model.frames_per_second
    ws = split_words(passage)
    ids: list[int] = []
    ranges: list[tuple[int, int]] = []
    for i, w in enumerate(ws):
        if i and model.delimiter_id is not None:
            ids.append(model.delimiter_id)
        tok = model.tokenize(w)
        ranges.append((len(ids), len(ids) + len(tok)))
        ids.extend(tok)
    spans, _ = forced_align(log_probs, ids, model.blank_id)
    by_tok = {s.token_index: s for s in spans}
    pad = round(cfg.pad_ms / 1000.0 * fps)
    T = log_probs.shape[0]
    log_min = math.log(cfg.presence_min_prob)

    verdicts: list[tuple[WordVerdict, float, float]] = []  # verdict, start_s, end_s
    for w, (a, b) in zip(ws, ranges):
        wspans = [by_tok[k] for k in range(a, b) if k in by_tok]
        if not wspans:
            verdicts.append((WordVerdict(w, SKIPPED), math.nan, math.nan))
            continue
        start, end = wspans[0].start, wspans[-1].end
        presence = float(np.mean([s.score for s in wspans]))
        if presence < log_min:
            verdicts.append((WordVerdict(w, SKIPPED, confidence=1.0), start / fps, end / fps))
            continue
        seg = log_probs[max(0, start - pad): min(T, end + pad)]
        v = score_word(seg, w, model, profile, cfg.eccl)
        verdicts.append((v, start / fps, end / fps))

    read = [(v, s, e) for v, s, e in verdicts if v.status != SKIPPED and not math.isnan(s)]
    if read:
        t0 = read[0][1]
        in_time = [(v, s, e) for v, s, e in read if s - t0 <= cfg.time_limit_s]
        t_end = min(in_time[-1][2], t0 + cfg.time_limit_s)
        seconds = max(1.0, t_end - t0)
    else:
        in_time, seconds = [], 0.0
    correct = sum(v.status in CORRECT_STATUSES for v, _, _ in in_time)
    unsure = sum(v.status == UNSURE for v, _, _ in in_time)
    per_min = 60.0 / seconds if seconds else 0.0
    words_out = []
    for idx, (v, s, e) in enumerate(verdicts):
        d = v.to_dict()
        d.update(index=idx, start_s=None if math.isnan(s) else round(s, 3), end_s=None if math.isnan(e) else round(e, 3))
        words_out.append(d)
    return PassageVerdict(
        n_words=len(ws), words=words_out, attempted=len(in_time), correct=correct, unsure=unsure,
        reading_seconds=round(seconds, 2),
        wcpm=round((correct + 0.5 * unsure) * per_min, 1),
        wcpm_low=round(correct * per_min, 1),
        wcpm_high=round((correct + unsure) * per_min, 1),
        accuracy=round(correct / len(in_time), 3) if in_time else 0.0,
    )
