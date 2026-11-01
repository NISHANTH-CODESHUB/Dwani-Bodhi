"""Print-ready ArUco ID cards (guide §6.2.2). 12 cards per A4 page at 300 dpi; print, laminate, cut.

    services/api/.venv/Scripts/python tools/make_aruco_cards.py --from 1 --to 48 --out tools/out
Card marker side ≈ 4 cm. The number under the marker is the child's roster slot in the app.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api"))

from app.vision.slates import make_marker_card  # noqa: E402

A4 = (3508, 2480)  # 300 dpi, portrait (h, w)
MARKER_PX = 472  # 4 cm at 300 dpi


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", type=int, default=1)
    ap.add_argument("--to", dest="end", type=int, default=48)
    ap.add_argument("--out", default=str(ROOT / "tools" / "out"))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    slots = list(range(args.start, args.end + 1))
    per_page, cols = 12, 3
    for page, i in enumerate(range(0, len(slots), per_page), start=1):
        sheet = np.full(A4, 255, np.uint8)
        for k, slot in enumerate(slots[i:i + per_page]):
            card = make_marker_card(slot, MARKER_PX)
            r, c = divmod(k, cols)
            y, x = 120 + r * (card.shape[0] + 60), 120 + c * (card.shape[1] + 120)
            sheet[y:y + card.shape[0], x:x + card.shape[1]] = card
        p = out / f"id_cards_page{page}.png"
        cv2.imwrite(str(p), sheet)
        print("wrote", p)


if __name__ == "__main__":
    main()
