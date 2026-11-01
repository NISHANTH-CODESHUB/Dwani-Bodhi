"""Calibration file produced by `eval/run_reading_eval.py --fit` and consumed by production scoring.

Format (JSON): {"tau_correct": float, "tau_error": float, "mutation_prior_nats": float,
                "calibration": {"correct": [[xs], [ys]], "MLEN": [[xs], [ys]], ...}}
"""

from __future__ import annotations

import itertools
import json
import os
from functools import lru_cache
from pathlib import Path

import numpy as np

from .eccl import EcclConfig


@lru_cache(maxsize=1)
def load_eccl_config() -> EcclConfig:
    path = os.environ.get("ECCL_CALIBRATION")
    if not path or not Path(path).exists():
        return EcclConfig()
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    cfg = EcclConfig()
    for k in ("tau_correct", "tau_error", "mutation_prior_nats", "dialect_prior_nats"):
        if k in data:
            setattr(cfg, k, float(data[k]))
    cfg.calibration = {k: (list(v[0]), list(v[1])) for k, v in data.get("calibration", {}).items()}
    return cfg


def isotonic_fit(scores: list[float], labels: list[int], bins: int = 10) -> tuple[list[float], list[float]]:
    """Pool-adjacent-violators on binned scores → monotone map score → empirical accuracy."""
    if not scores:
        return [0.0, 1.0], [0.0, 1.0]
    order = np.argsort(scores)
    s = np.asarray(scores)[order]
    y = np.asarray(labels, dtype=float)[order]
    edges = np.quantile(s, np.linspace(0, 1, bins + 1))
    xs, ys, ws = [], [], []
    for lo, hi in itertools.pairwise(edges):
        m = (s >= lo) & (s <= hi)
        if m.any():
            xs.append(float(s[m].mean()))
            ys.append(float(y[m].mean()))
            ws.append(int(m.sum()))
    i = 0
    while i < len(ys) - 1:  # PAV
        if ys[i] > ys[i + 1]:
            tot = ws[i] + ws[i + 1]
            merged = (ys[i] * ws[i] + ys[i + 1] * ws[i + 1]) / tot
            mx = (xs[i] * ws[i] + xs[i + 1] * ws[i + 1]) / tot
            ys[i:i + 2], xs[i:i + 2], ws[i:i + 2] = [merged], [mx], [tot]
            i = max(0, i - 1)
        else:
            i += 1
    return xs, ys


def expected_calibration_error(conf: list[float], correct: list[int], bins: int = 10) -> float:
    conf_a, corr_a = np.asarray(conf), np.asarray(correct, dtype=float)
    ece = 0.0
    for lo in np.linspace(0, 1, bins, endpoint=False):
        m = (conf_a >= lo) & (conf_a < lo + 1 / bins)
        if m.any():
            ece += m.mean() * abs(conf_a[m].mean() - corr_a[m].mean())
    return float(ece)
