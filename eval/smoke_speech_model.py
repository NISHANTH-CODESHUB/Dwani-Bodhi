"""Smoke test for the real acoustic model (run on Day 1 / after any model change).

    SPEECH_BACKEND=wav2vec2 python eval/smoke_speech_model.py [--clip some_hindi_word.wav --target नदी]

Checks: model loads; vocabulary covers every character used by the content pack; silence → NO_SPEECH;
real-time factor on CPU; optionally scores a real recording.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api"))
os.environ.setdefault("SPEECH_BACKEND", "wav2vec2")

from app.config import get_settings  # noqa: E402
from app.content.pack import get_pack  # noqa: E402
from app.speech.acoustic import get_acoustic_model  # noqa: E402
from app.speech.devanagari import normalize  # noqa: E402
from app.speech.eccl import score_word  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clip")
    ap.add_argument("--target")
    args = ap.parse_args()
    t0 = time.perf_counter()
    model = get_acoustic_model()
    print(f"loaded {model.name} in {time.perf_counter() - t0:.1f}s; vocab={len(model.vocab)}")

    cp = get_pack(get_settings().content_pack_dir)
    used = set()
    for it in cp.items.values():
        for ch in normalize(it.text or ""):
            if ch.strip() and "ऀ" <= ch <= "ॿ" and ch not in "।॥":
                used.add(ch)
    missing = sorted(ch for ch in used if ch not in model.vocab and not any(ch in k for k in model.vocab))
    print(f"content chars: {len(used)}; missing from model vocab: {missing or 'none'}")

    silence = np.zeros(16000 * 2, dtype=np.float32) + np.random.default_rng(0).normal(0, 1e-3, 32000).astype(np.float32)
    t0 = time.perf_counter()
    lp = model.log_probs(silence)
    dt = time.perf_counter() - t0
    v = score_word(lp, "नदी", model)
    print(f"silence → {v.status} (frames={lp.shape[0]}, RTF={dt / 2.0:.3f})")

    if args.clip:
        from app.speech.audio import decode_to_16k_mono, signal_quality, trim_silence
        wave = decode_to_16k_mono(Path(args.clip).read_bytes())
        print("quality:", signal_quality(wave))
        v = score_word(model.log_probs(trim_silence(wave)), args.target, model)
        print(v.status, v.rule, v.detail, round(v.confidence, 3), [(a.text, round(a.p, 3)) for a in v.alternatives])
    ok = v.status == "NO_SPEECH" if not args.clip else True
    print("SMOKE", "OK" if ok and not missing else "CHECK")


if __name__ == "__main__":
    main()
