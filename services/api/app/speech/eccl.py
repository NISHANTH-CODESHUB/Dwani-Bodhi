"""Expectation-Constrained Confusion-Lattice (ECCL) scoring — novelty N1 (guide §6.1).

We know the text the child should read, so instead of open ASR we compute the CTC likelihood of
the correct reading and of every pedagogically meaningful mis-reading, and take the posterior over
that closed candidate set. The winning candidate's rule *is* the error type.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import asdict, dataclass, field

import numpy as np

from .acoustic import AcousticModel
from .ctc import ctc_nll, forced_align, greedy_decode, speech_fraction
from .devanagari import aksharas, normalize
from .mutations import Candidate, generate_candidates
from .regions import STANDARD, RegionProfile

CORRECT = "CORRECT"
CORRECT_DIALECT = "CORRECT_DIALECT"
ERROR = "ERROR"
UNSURE = "UNSURE"
OTHER = "OTHER"
NO_SPEECH = "NO_SPEECH"
SKIPPED = "SKIPPED"

CORRECT_STATUSES = {CORRECT, CORRECT_DIALECT}


@dataclass
class EcclConfig:
    tau_correct: float = 0.75  # posterior mass on correct (+dialect) readings to accept
    tau_error: float = 0.70  # posterior on a single mutation to call an error
    mutation_prior_nats: float = 1.0  # a-priori penalty for each mis-reading vs the correct reading
    dialect_prior_nats: float = 0.3
    min_speech_fraction: float = 0.04
    other_edit_ratio: float = 0.6  # free decode this far from every candidate → OTHER
    long_gap_ms: float = 300.0
    # optional isotonic calibration: key -> (xs, ys); keys "correct" or a rule id
    calibration: dict[str, tuple[list[float], list[float]]] = field(default_factory=dict)

    def calibrate(self, key: str, p: float) -> float:
        xs_ys = self.calibration.get(key)
        if not xs_ys:
            return p
        xs, ys = xs_ys
        return float(np.interp(p, xs, ys))


@dataclass
class Alternative:
    text: str
    rule: str | None
    detail: str
    p: float


@dataclass
class WordVerdict:
    target: str
    status: str
    p_correct: float = 0.0
    rule: str | None = None
    site: int | None = None
    detail: str = ""
    produced: str | None = None
    confidence: float = 0.0  # calibrated confidence in `status`
    alternatives: list[Alternative] = field(default_factory=list)
    onset_ms: float | None = None
    duration_ms: float | None = None
    max_gap_ms: float | None = None
    long_gaps: int = 0
    sounding_out: bool = False

    @property
    def is_correct(self) -> bool:
        return self.status in CORRECT_STATUSES

    def to_dict(self) -> dict:
        return asdict(self)


def _edit_ratio(a: str, b: str) -> float:
    if not a and not b:
        return 0.0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1] / max(len(a), len(b))


def _timing(log_probs: np.ndarray, ids: list[int], model: AcousticModel, cfg: EcclConfig, n_aks: int) -> dict:
    spans, _ = forced_align(log_probs, ids, model.blank_id)
    if not spans:
        return {}
    ms = 1000.0 / model.frames_per_second
    gaps = [(b.start - a.end) * ms for a, b in itertools.pairwise(spans)]
    long_gaps = sum(g >= cfg.long_gap_ms for g in gaps)
    return {
        "onset_ms": spans[0].start * ms,
        "duration_ms": (spans[-1].end - spans[0].start) * ms,
        "max_gap_ms": max(gaps) if gaps else 0.0,
        "long_gaps": long_gaps,
        "sounding_out": n_aks >= 2 and long_gaps >= max(1, (n_aks - 1) / 2),
    }


def score_word(
    log_probs: np.ndarray,
    target: str,
    model: AcousticModel,
    profile: RegionProfile = STANDARD,
    cfg: EcclConfig | None = None,
) -> WordVerdict:
    cfg = cfg or EcclConfig()
    target = normalize(target)
    n_aks = len(aksharas(target))
    if speech_fraction(log_probs, model.nonspeech_ids) < cfg.min_speech_fraction:
        return WordVerdict(target, NO_SPEECH, confidence=1.0)
    # Null hypothesis: "nothing was said". Without it, silence would hand the win to the correct reading
    # (all candidates equally unlikely, and only mistakes carry a prior penalty).
    null_nll = ctc_nll(log_probs, [], model.blank_id)

    cands: list[Candidate] = generate_candidates(target, extra=profile.variants(target))
    logits, kept = [], []
    for c in cands:
        ids = model.tokenize(c.text)
        if not ids:
            continue
        nll = ctc_nll(log_probs, ids, model.blank_id)
        if math.isinf(nll):
            continue
        prior = 0.0 if c.is_target else (cfg.dialect_prior_nats if c.rule == "DIALECT" else cfg.mutation_prior_nats)
        logits.append(-nll - prior)
        kept.append(c)
    if not kept:
        return WordVerdict(target, UNSURE, detail="no scorable candidates")

    arr = np.asarray(logits)
    z = max(arr.max(), -null_nll)
    p_null = float(np.exp(-null_nll - z))
    post = np.exp(arr - z)
    total = post.sum() + p_null
    if p_null / total >= 0.5:
        return WordVerdict(target, NO_SPEECH, confidence=p_null / total)
    post /= post.sum()
    order = np.argsort(-post)
    best = kept[int(order[0])]
    p_best = float(post[order[0]])
    p_correct = float(sum(p for p, c in zip(post, kept) if c.is_target or c.rule == "DIALECT"))
    alts = [Alternative(kept[i].text, kept[i].rule, kept[i].detail, float(post[i])) for i in order[:4]]

    free = model.detokenize(greedy_decode(log_probs, model.blank_id)).replace(" ", "")
    timing = _timing(log_probs, model.tokenize(best.text), model, cfg, n_aks)
    base = dict(target=target, p_correct=p_correct, alternatives=alts, **timing)

    if free and _edit_ratio(free, best.text) > cfg.other_edit_ratio and _edit_ratio(free, target) > cfg.other_edit_ratio:
        return WordVerdict(status=OTHER, produced=free, confidence=1 - p_best, **base)
    if p_correct >= cfg.tau_correct:
        conf = cfg.calibrate("correct", p_correct)
        if best.rule == "DIALECT":
            return WordVerdict(status=CORRECT_DIALECT, produced=best.text, detail=best.detail, confidence=conf, **base)
        return WordVerdict(status=CORRECT, produced=target, confidence=conf, **base)
    if not best.is_target and best.rule != "DIALECT" and p_best >= cfg.tau_error:
        return WordVerdict(
            status=ERROR, rule=best.rule, site=best.site, detail=best.detail, produced=best.text,
            confidence=cfg.calibrate(best.rule or "", p_best), **base,
        )
    return WordVerdict(status=UNSURE, produced=best.text, confidence=1 - abs(p_correct - 0.5) * 2, **base)
