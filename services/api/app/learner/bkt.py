"""Bayesian Knowledge Tracing with soft evidence and asymmetric prerequisite propagation (guide §8.1–8.3)."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class BKTParams:
    guess: float = 0.10
    slip: float = 0.10
    learn_per_week: float = 0.10


def clamp(p: float, lo: float = 0.001, hi: float = 0.999) -> float:
    return min(hi, max(lo, p))


def posterior(p: float, correct: bool, params: BKTParams) -> float:
    g, s = params.guess, params.slip
    if correct:
        num, den = p * (1 - s), p * (1 - s) + (1 - p) * g
    else:
        num, den = p * s, p * s + (1 - p) * (1 - g)
    return clamp(num / den if den > 0 else p)


def update(p: float, correct: bool, confidence: float, params: BKTParams) -> float:
    """Jeffrey-style soft evidence: blend the hard update with the prior by verdict confidence."""
    c = min(1.0, max(0.0, confidence))
    return clamp(c * posterior(p, correct, params) + (1 - c) * p)


def learn(p: float, weeks: float, params: BKTParams) -> float:
    """Between-session learning transition, applied for elapsed time."""
    if weeks <= 0:
        return p
    keep = (1 - params.learn_per_week) ** weeks
    return clamp(1 - (1 - p) * keep)


def propagate_success(p_prereq: float, strength: float, lam: float = 0.5) -> float:
    """Success on an advanced skill is strong evidence for its prerequisites (never the reverse)."""
    return clamp(p_prereq + lam * strength * (1 - p_prereq))


def entropy(p: float) -> float:
    p = clamp(p)
    return -(p * math.log2(p) + (1 - p) * math.log2(1 - p))


def expected_info_gain(p: float, params: BKTParams) -> float:
    """Expected reduction in entropy of mastery from observing one response."""
    p_corr = p * (1 - params.slip) + (1 - p) * params.guess
    h_after = p_corr * entropy(posterior(p, True, params)) + (1 - p_corr) * entropy(posterior(p, False, params))
    return max(0.0, entropy(p) - h_after)
