"""Slate evaluation (guide §14, datasets D-S1 / D-S2) and the N2 ablation.

Real data:
    python eval/run_slate_eval.py --labels eval/datasets/ds1/labels.json [--model claude-haiku-5-5]
  labels.json: [{"image": "photo1.jpg", "problems": [{"a":52,"b":19,"op":"-"}, ...],
                 "slates": [{"marker": 3, "answers": ["47", "75"]}, ...]}]
  Needs ANTHROPIC_API_KEY for transcription (each call is logged with its cost).

Synthetic pipeline check (marker detection + cropping + bug verification; no API calls):
    python eval/run_slate_eval.py --synthetic 20
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels")
    ap.add_argument("--synthetic", type=int, default=0)
    ap.add_argument("--model", help="override MODEL_SLATE (e.g. claude-haiku-5-5 vs claude-sonnet-5-5)")
    ap.add_argument("--out", default=str(ROOT / "eval" / "reports" / "slate_report.json"))
    args = ap.parse_args()
    if args.model:
        os.environ["MODEL_SLATE"] = args.model

    from app.db import SessionLocal, create_all
    from app.demo import slate_photo
    from app.diagnosis.bugs import DEFAULT_LIBRARY
    from app.diagnosis.verify import verify
    from app.llm import slate as llm_slate
    from app.llm.client import LLMUnavailable
    from app.vision.slates import detect_and_crop

    create_all()
    cases = []
    if args.synthetic:
        rng = random.Random(5)
        bugs = [b for b in DEFAULT_LIBRARY.bugs.values()]
        for i in range(args.synthetic):
            probs = [{"a": 52, "b": 19, "op": "-"}, {"a": 47, "b": 38, "op": "+"}]
            slates = []
            for slot in rng.sample(range(1, 60), 4):
                ans = []
                for p in probs:
                    b = rng.choice(bugs + [None, None])
                    a = b.apply(p["a"], p["b"]) if b and b.spec.op == p["op"] else None
                    ans.append(a or str(p["a"] + p["b"] if p["op"] == "+" else p["a"] - p["b"]))
                slates.append({"marker": slot, "answers": ans})
            img = slate_photo([(s["marker"], s["answers"]) for s in slates], probs)
            cases.append({"image_bytes": img, "problems": probs, "slates": slates})
    else:
        base = Path(args.labels).parent
        for c in json.loads(Path(args.labels).read_text(encoding="utf-8")):
            cases.append({**c, "image_bytes": (base / c["image"]).read_bytes()})

    stats = Counter()
    bug_tp = bug_fp = bug_fn = 0
    with SessionLocal() as db:
        for c in cases:
            crops, meta = detect_and_crop(c["image_bytes"])
            found = {cr.marker_id: cr for cr in crops}
            probs = [{"problem_id": f"p{i + 1}", **p} for i, p in enumerate(c["problems"])]
            for s in c["slates"]:
                stats["slates"] += 1
                cr = found.get(s["marker"])
                if cr is None:
                    stats["marker_missed"] += 1
                    continue
                stats["marker_found"] += 1
                reading = None
                try:
                    reading = llm_slate.transcribe(db, cr.jpeg, "image/jpeg", probs)
                except LLMUnavailable:
                    stats["llm_unavailable"] += 1
                for p, gold in zip(probs, s["answers"]):
                    gold_v = verify(p["a"], p["b"], p["op"], gold)
                    if reading is None:
                        pred_answer, conf = gold, 1.0  # pipeline-only check: assume perfect transcription
                    else:
                        pr = next((x for x in reading.problems if x.problem_id == p["problem_id"]), None)
                        pred_answer = pr.child_answer if pr else None
                        conf = llm_slate.answer_confidence(pr) if pr else 0.0
                    if conf < 0.75:
                        stats["abstained"] += 1
                        continue
                    stats["answers"] += 1
                    stats["exact"] += int((pred_answer or "") == gold)
                    pv = verify(p["a"], p["b"], p["op"], pred_answer)
                    g, q = set(gold_v.matching_bugs), set(pv.matching_bugs)
                    bug_tp += len(g & q)
                    bug_fp += len(q - g)
                    bug_fn += len(g - q)
    report = {
        "synthetic": bool(args.synthetic), "transcription": "assumed perfect" if stats["llm_unavailable"] else "claude",
        "model": os.environ.get("MODEL_SLATE", "default"),
        "marker_detection_rate": round(stats["marker_found"] / max(1, stats["slates"]), 3),
        "answer_exact_match": round(stats["exact"] / max(1, stats["answers"]), 3),
        "abstention_rate": round(stats["abstained"] / max(1, stats["answers"] + stats["abstained"]), 3),
        "bug_precision": round(bug_tp / max(1, bug_tp + bug_fp), 3),
        "bug_recall": round(bug_tp / max(1, bug_tp + bug_fn), 3),
        "counts": dict(stats),
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
