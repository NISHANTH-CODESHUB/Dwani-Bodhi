"""Diagnostic item engineering for arithmetic (novelty N3, guide §6.3.1).

Keeps only problems on which the targeted bugs predict *pairwise different* answers that also
differ from the correct answer and from one-digit slips — so every wrong answer is informative.
"""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass

from .bugs import DEFAULT_LIBRARY, BugLibrary
from .procedures import correct_answer


@dataclass(frozen=True)
class SkillSpace:
    skill_id: str
    op: str
    a_range: tuple[int, int]
    b_range: tuple[int, int]
    regroup: bool | None  # True: must need carry/borrow; False: must not; None: any
    target_bugs: tuple[str, ...]


SPACES: dict[str, SkillSpace] = {
    "M6": SkillSpace("M6", "+", (10, 89), (10, 89), False, ("ADD_LEFT_ALIGN", "OP_SWAP_ADD", "ADD_ALL_DIGITS")),
    "M7": SkillSpace("M7", "+", (15, 89), (15, 89), True,
                     ("ADD_NO_CARRY", "ADD_CARRY_WRITE_BOTH", "OP_SWAP_ADD", "ADD_ALL_DIGITS", "ANSWER_REVERSED_ADD")),
    "M8": SkillSpace("M8", "-", (20, 99), (10, 89), False, ("OP_SWAP_SUB", "SUB_ALWAYS_BORROW")),
    "M9": SkillSpace("M9", "-", (30, 99), (11, 89), True,
                     ("SUB_SMALLER_FROM_LARGER", "SUB_BORROW_NO_DECREMENT", "SUB_ZERO_MINUS_N_IS_ZERO",
                      "SUB_ZERO_MINUS_N_IS_N", "OP_SWAP_SUB")),
    "M10": SkillSpace("M10", "-", (200, 999), (100, 899), True,
                      ("SUB_SMALLER_FROM_LARGER", "SUB_BORROW_NO_DECREMENT", "SUB_BORROW_ACROSS_ZERO")),
}


def needs_regroup(a: int, b: int, op: str) -> bool:
    da, db = str(a)[::-1], str(b)[::-1]
    carry = 0
    for i in range(max(len(da), len(db))):
        x = int(da[i]) if i < len(da) else 0
        y = int(db[i]) if i < len(db) else 0
        if op == "+":
            if x + y + carry >= 10:
                return True
        else:
            if x - carry < y:
                return True
            carry = 0
    return False


@dataclass
class MathItem:
    id: str
    skill_id: str
    op: str
    a: int
    b: int
    correct: str
    signature: dict[str, str]  # bug id -> predicted answer (only discriminating, applicable bugs)
    discrimination: float  # share of target bugs this item can tell apart
    collisions: list[list[str]]

    def to_dict(self) -> dict:
        return asdict(self)


def analyse(a: int, b: int, op: str, targets: tuple[str, ...], library: BugLibrary = DEFAULT_LIBRARY) -> MathItem | None:
    c = correct_answer(a, b, op)  # type: ignore[arg-type]
    if c is None:
        return None
    cs = str(c)
    sig: dict[str, str] = {}
    by_answer: dict[str, list[str]] = {}
    for bid in targets:
        bug = library.get(bid)
        if bug is None:
            continue
        p = bug.apply(a, b)
        # Keep predictions that look like a one-digit slip (e.g. a dropped carry): verify() checks
        # bugs before slips, and confirmation needs two independent reproductions anyway.
        if p is None or p == cs:
            continue
        sig[bid] = p
        by_answer.setdefault(p, []).append(bid)
    collisions = [v for v in by_answer.values() if len(v) > 1]
    distinct = len(by_answer)
    disc = distinct / len(targets) if targets else 0.0
    return MathItem(f"{op}:{a}:{b}", "", op, a, b, cs, sig, round(disc, 3), collisions)


def generate(skill_id: str, n: int = 12, seed: int = 7, library: BugLibrary = DEFAULT_LIBRARY) -> list[MathItem]:
    sp = SPACES[skill_id]
    rng = random.Random(seed)
    pool: list[MathItem] = []
    for a in range(sp.a_range[0], sp.a_range[1] + 1):
        for b in range(sp.b_range[0], sp.b_range[1] + 1):
            if sp.op == "-" and b >= a:
                continue
            if sp.regroup is not None and needs_regroup(a, b, sp.op) != sp.regroup:
                continue
            item = analyse(a, b, sp.op, sp.target_bugs, library)
            if item is None or item.collisions:
                continue
            item.skill_id = skill_id
            item.id = f"{skill_id}:{sp.op}:{a}:{b}"
            pool.append(item)
    if not pool:
        return []
    best = max(i.discrimination for i in pool)
    top = [i for i in pool if i.discrimination >= 0.6 * best]
    keys = {id(i): rng.random() for i in top}
    top.sort(key=lambda i: (-i.discrimination, keys[id(i)]))
    chosen: list[MathItem] = []
    used: set[int] = set()
    for it in top:  # diversity: avoid reusing operands
        if it.a in used or it.b in used:
            continue
        chosen.append(it)
        used.update((it.a, it.b))
        if len(chosen) >= n:
            break
    return chosen
