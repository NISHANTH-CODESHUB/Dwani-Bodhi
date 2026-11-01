"""Symbolic verification of a child's written answer (guide §6.2.1).

A misconception is attributed to an answer ONLY if a bug procedure reproduces it exactly.
Confirmation across items happens in the learner model (Beta-Binomial, ≥2 reproductions).
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from .bugs import DEFAULT_LIBRARY, BugLibrary
from .procedures import Op, correct_answer

CORRECT = "CORRECT"
BUG = "BUG"
SLIP = "SLIP"
UNEXPLAINED = "UNEXPLAINED"
BLANK = "BLANK"
ILLEGIBLE = "ILLEGIBLE"


@dataclass
class AnswerVerdict:
    a: int
    b: int
    op: str
    answer: str | None
    correct: str | None
    status: str
    matching_bugs: list[str] = field(default_factory=list)
    # bugs that were *testable* on this item: they predict an answer different from the correct one.
    # Needed by the learner model: a correct answer is evidence against exactly these bugs.
    discriminable_bugs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def normalize_answer(raw: str | None) -> str | None:
    if raw is None:
        return None
    s = re.sub(r"[\s,]", "", str(raw))
    s = s.translate(str.maketrans("०१२३४५६७८९", "0123456789"))  # Devanagari digits
    if not s:
        return None
    if "?" in s:
        return "?"
    s = s.lstrip("0") or ("0" if s else s)
    return s if s.isdigit() else "?"


def is_slip(answer: str, correct: str) -> bool:
    """Same length, exactly one digit off by one — a fact slip, not a misconception."""
    if len(answer) != len(correct) or answer == correct:
        return False
    diffs = [(int(x), int(y)) for x, y in zip(answer, correct) if x != y]
    return len(diffs) == 1 and abs(diffs[0][0] - diffs[0][1]) == 1


def verify(a: int, b: int, op: Op, raw_answer: str | None, library: BugLibrary = DEFAULT_LIBRARY) -> AnswerVerdict:
    c = correct_answer(a, b, op)
    c_s = None if c is None else str(c)
    ans = normalize_answer(raw_answer)
    preds = {bug.id: bug.apply(a, b) for bug in library.for_op(op)}
    discriminable = [bid for bid, p in preds.items() if p is not None and p != c_s]
    base = {"a": a, "b": b, "op": op, "answer": ans, "correct": c_s, "discriminable_bugs": discriminable}
    if ans is None:
        return AnswerVerdict(status=BLANK, **base)
    if ans == "?":
        return AnswerVerdict(status=ILLEGIBLE, **base)
    if ans == c_s:
        return AnswerVerdict(status=CORRECT, **base)
    matches = [bid for bid, p in preds.items() if p == ans]
    if matches:
        return AnswerVerdict(status=BUG, matching_bugs=matches, **base)
    if c_s and is_slip(ans, c_s):
        return AnswerVerdict(status=SLIP, **base)
    return AnswerVerdict(status=UNEXPLAINED, **base)
