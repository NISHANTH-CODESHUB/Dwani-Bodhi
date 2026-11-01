"""Reading evaluation + calibration (guide §14).

Real data (D-R1 planted-error / D-R2 consented children):
    python eval/run_reading_eval.py --manifest eval/datasets/dr1/manifest.csv [--fit eval/calibration.json]
  manifest.csv columns: clip, target, label_status (CORRECT|ERROR), label_rule (MLEN|ASP|...|""), group
  Requires SPEECH_BACKEND=wav2vec2 (pip install -e "services/api[speech]").

Pipeline self-check without audio (synthetic posteriors; NOT a quality claim):
    python eval/run_reading_eval.py --simulate 400

Reports: word accuracy, abstention, error-type macro-F1, ECE, per-group accuracy, and the N1 ablation
(ECCL vs free ASR string match).
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api"))

from app.speech.acoustic import SimulatedBackend, SimulatedUtterance, get_acoustic_model  # noqa: E402
from app.speech.calibration import expected_calibration_error, isotonic_fit  # noqa: E402
from app.speech.ctc import greedy_decode  # noqa: E402
from app.speech.devanagari import normalize  # noqa: E402
from app.speech.eccl import CORRECT_STATUSES, ERROR, UNSURE, EcclConfig, score_word  # noqa: E402
from app.speech.mutations import generate_candidates  # noqa: E402


def load_rows(args) -> list[dict]:
    if args.simulate:
        rng = random.Random(3)
        words = [w for w in "नदी पीला मीठा फल घर भालू खाना किताब मेला संतरा चाँद बंदर थाली दिन फूल केला".split()]
        rows = []
        for i in range(args.simulate):
            t = rng.choice(words)
            cands = generate_candidates(t)
            if rng.random() < 0.35 and len(cands) > 1:
                c = rng.choice(cands[1:])
                rows.append({"clip": None, "target": t, "spoken": c.text, "label_status": "ERROR", "label_rule": c.rule,
                             "group": rng.choice(["f", "m"]), "conf": rng.uniform(0.35, 0.95)})
            else:
                rows.append({"clip": None, "target": t, "spoken": t, "label_status": "CORRECT", "label_rule": "",
                             "group": rng.choice(["f", "m"]), "conf": rng.uniform(0.35, 0.95)})
        return rows
    with open(args.manifest, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest")
    ap.add_argument("--simulate", type=int, default=0)
    ap.add_argument("--fit", help="write calibration JSON here")
    ap.add_argument("--out", default=str(ROOT / "eval" / "reports" / "reading_report.json"))
    args = ap.parse_args()
    rows = load_rows(args)
    model = SimulatedBackend() if args.simulate else get_acoustic_model()
    cfg = EcclConfig()
    results = []
    for r in rows:
        if args.simulate:
            lp = model.synthesize(SimulatedUtterance(r["spoken"], confidence=r["conf"], seed=len(results)))
        else:
            from app.speech.audio import decode_to_16k_mono, trim_silence
            lp = model.log_probs(trim_silence(decode_to_16k_mono(Path(r["clip"]).read_bytes())))
        v = score_word(lp, r["target"], model, cfg=cfg)
        free = model.detokenize(greedy_decode(lp, model.blank_id)).replace(" ", "")
        results.append({**{k: r[k] for k in ("target", "label_status", "label_rule", "group")},
                        "status": v.status, "rule": v.rule, "p_correct": v.p_correct, "confidence": v.confidence,
                        "free_asr_correct": free == normalize(r["target"])})

    decided = [x for x in results if x["status"] != UNSURE]
    gold_ok = lambda x: x["label_status"] == "CORRECT"  # noqa: E731
    pred_ok = lambda x: x["status"] in CORRECT_STATUSES  # noqa: E731
    acc = sum(gold_ok(x) == pred_ok(x) for x in decided) / max(1, len(decided))
    free_acc = sum(gold_ok(x) == x["free_asr_correct"] for x in results) / max(1, len(results))
    # error-type macro F1 over gold error rules
    rules = sorted({x["label_rule"] for x in results if x["label_rule"]})
    f1s = {}
    for rule in rules:
        tp = sum(x["label_rule"] == rule and x["status"] == ERROR and x["rule"] == rule for x in decided)
        fp = sum(x["label_rule"] != rule and x["status"] == ERROR and x["rule"] == rule for x in decided)
        fn = sum(x["label_rule"] == rule and not (x["status"] == ERROR and x["rule"] == rule) for x in decided)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1s[rule] = round(2 * prec * rec / (prec + rec), 3) if prec + rec else 0.0
    by_group = defaultdict(list)
    for x in decided:
        by_group[x["group"]].append(gold_ok(x) == pred_ok(x))
    ece = expected_calibration_error([x["p_correct"] for x in results], [int(gold_ok(x)) for x in results])
    report = {
        "synthetic": bool(args.simulate), "n": len(results),
        "word_accuracy_on_decided": round(acc, 3), "abstention_rate": round(1 - len(decided) / max(1, len(results)), 3),
        "error_type_macro_f1": round(sum(f1s.values()) / max(1, len(f1s)), 3), "f1_by_rule": f1s,
        "ece_p_correct": round(ece, 3),
        "accuracy_by_group": {g: round(sum(v) / len(v), 3) for g, v in by_group.items()},
        "ablation_N1": {"eccl_accuracy": round(acc, 3), "free_asr_accuracy": round(free_acc, 3),
                        "note": "free ASR cannot type errors at all; ECCL types them by construction"},
        "status_counts": dict(Counter(x["status"] for x in results)),
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.fit:
        xs, ys = isotonic_fit([x["p_correct"] for x in results], [int(gold_ok(x)) for x in results])
        Path(args.fit).write_text(json.dumps({"calibration": {"correct": [xs, ys]}}, indent=2), encoding="utf-8")
        print("calibration written to", args.fit, "— set ECCL_CALIBRATION to use it in production")


if __name__ == "__main__":
    main()
