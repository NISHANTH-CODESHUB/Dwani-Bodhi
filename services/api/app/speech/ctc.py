"""Pure-NumPy CTC utilities: sequence negative log-likelihood and Viterbi forced alignment.

Kept independent of PyTorch so that scoring logic is testable without a GPU stack and so
acoustic inference (model) and scoring (this) can scale on different workers.
All inputs are log-probabilities of shape (T, V) (log-softmax over the vocabulary per frame).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

NEG_INF = -1e30


def _extend(labels: list[int], blank: int) -> np.ndarray:
    ext = [blank]
    for lab in labels:
        ext.extend([lab, blank])
    return np.asarray(ext, dtype=np.int64)


def _skip_mask(ext: np.ndarray, blank: int) -> np.ndarray:
    """allow transition s-2 -> s when ext[s] is a label different from ext[s-2]."""
    allow = np.zeros(len(ext), dtype=bool)
    if len(ext) > 2:
        allow[2:] = (ext[2:] != blank) & (ext[2:] != ext[:-2])
    return allow


def ctc_nll(log_probs: np.ndarray, labels: list[int], blank: int = 0) -> float:
    """-log P(labels | audio) under CTC (forward algorithm in log space)."""
    T = log_probs.shape[0]
    if not labels:
        return float(-log_probs[:, blank].sum())
    ext = _extend(labels, blank)
    S = len(ext)
    if T < len(labels):
        return float("inf")
    skip = _skip_mask(ext, blank)
    alpha = np.full(S, NEG_INF)
    alpha[0] = log_probs[0, ext[0]]
    alpha[1] = log_probs[0, ext[1]]
    emit = log_probs[:, ext]  # (T, S)
    for t in range(1, T):
        prev1 = np.concatenate(([NEG_INF], alpha[:-1]))
        prev2 = np.concatenate(([NEG_INF, NEG_INF], alpha[:-2]))
        prev2 = np.where(skip, prev2, NEG_INF)
        alpha = np.logaddexp(np.logaddexp(alpha, prev1), prev2) + emit[t]
    total = np.logaddexp(alpha[-1], alpha[-2]) if S > 1 else alpha[-1]
    return float(-total) if total > NEG_INF / 2 else float("inf")


@dataclass(frozen=True)
class TokenSpan:
    token_index: int  # index into the label sequence
    label: int
    start: int  # first frame (inclusive)
    end: int  # last frame (exclusive)
    score: float  # mean log-prob of the token over its frames


def forced_align(log_probs: np.ndarray, labels: list[int], blank: int = 0) -> tuple[list[TokenSpan], float]:
    """Viterbi best path for `labels`. Returns per-token spans and the path log-prob."""
    T = log_probs.shape[0]
    if not labels or T < len(labels):
        return [], NEG_INF
    ext = _extend(labels, blank)
    S = len(ext)
    skip = _skip_mask(ext, blank)
    emit = log_probs[:, ext]
    delta = np.full(S, NEG_INF)
    delta[0], delta[1] = emit[0, 0], emit[0, 1]
    back = np.zeros((T, S), dtype=np.int8)  # 0 stay, 1 from s-1, 2 from s-2
    for t in range(1, T):
        prev1 = np.concatenate(([NEG_INF], delta[:-1]))
        prev2 = np.where(skip, np.concatenate(([NEG_INF, NEG_INF], delta[:-2])), NEG_INF)
        stacked = np.stack([delta, prev1, prev2])
        choice = stacked.argmax(axis=0)
        delta = stacked[choice, np.arange(S)] + emit[t]
        back[t] = choice
    end_state = S - 1 if delta[S - 1] >= delta[S - 2] else S - 2
    best = float(delta[end_state])
    states = np.empty(T, dtype=np.int64)
    s = end_state
    for t in range(T - 1, -1, -1):
        states[t] = s
        s -= int(back[t, s])
    spans: list[TokenSpan] = []
    t = 0
    while t < T:
        s = states[t]
        if s % 2 == 1:  # label state
            start = t
            while t < T and states[t] == s:
                t += 1
            k = (s - 1) // 2
            score = float(log_probs[start:t, labels[k]].mean())
            spans.append(TokenSpan(k, labels[k], start, t, score))
        else:
            t += 1
    return spans, best


def greedy_decode(log_probs: np.ndarray, blank: int = 0) -> list[int]:
    ids = log_probs.argmax(axis=1)
    out: list[int] = []
    prev = -1
    for i in ids:
        if i != prev and i != blank:
            out.append(int(i))
        prev = i
    return out


def speech_fraction(log_probs: np.ndarray, nonspeech_ids: set[int] | int = 0) -> float:
    """Share of frames whose most likely token is a real character (not blank/delimiter/special)."""
    ids = log_probs.argmax(axis=1)
    if not len(ids):
        return 0.0
    ns = {nonspeech_ids} if isinstance(nonspeech_ids, int) else set(nonspeech_ids)
    return float((~np.isin(ids, list(ns))).mean())
