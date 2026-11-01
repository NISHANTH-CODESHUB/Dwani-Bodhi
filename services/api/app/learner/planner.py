"""Adaptive session planning by expected information gain (novelty N3, guide §6.3.2).

Plans are computed on the server whenever a phone syncs and cached on the phone, so the next
session runs fully offline. Within-session adaptivity is limited to the simple rules in `rules`.
"""

from __future__ import annotations

import random
import zlib
from dataclasses import asdict, dataclass, field
from datetime import date

from ..content.pack import ContentPack
from ..content.schema import TAP_TYPES, Item
from .bkt import BKTParams, entropy, expected_info_gain
from .state import SPOKEN, TAP4, WRITTEN, LearnerState, reading_misconception_id

REUSE_DAYS = 28


@dataclass
class PlannedItem:
    item_id: str
    type: str
    block: str
    gain: float
    reason: str


@dataclass
class SessionPlan:
    child_id: str
    items: list[PlannedItem]
    est_seconds: float
    rules: dict = field(default_factory=dict)
    content_version: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _params(item: Item) -> BKTParams:
    if item.type in TAP_TYPES or item.type == "comprehension":
        return TAP4
    if item.type == "slate":
        return WRITTEN
    return SPOKEN


def _mis_id(item: Item, probe: str) -> str:
    return probe if item.type == "slate" or item.type in TAP_TYPES else reading_misconception_id(probe)


def item_gain(item: Item, state: LearnerState, pack: ContentPack) -> tuple[float, str]:
    params = _params(item)
    g = 0.0
    for s in item.skills:
        p = state.skills.get(s, 0.3)
        w = pack.graph.skills[s].weight if s in pack.graph.skills else 1.0
        g += w * expected_info_gain(p, params)
    mis_probes = item.probes + [o.probe for o in item.options if o.probe]
    for probe in mis_probes:
        m = state.misconceptions.get(_mis_id(item, probe))
        mean = m.mean if m else 0.2
        g += 0.5 * entropy(mean) * (1.0 if m and m.hits > 0 else 0.4)
    reason = "info"
    touched = set(item.skills) | {_mis_id(item, p) for p in mis_probes}
    if touched & state.recheck:
        g += 0.6
        reason = "recheck"
    elif any(state.misconceptions.get(_mis_id(item, p)) and state.misconceptions[_mis_id(item, p)].hits > 0
             for p in mis_probes):
        reason = "confirm"
    return g, reason


def _eligible(item: Item, state: LearnerState, last_seen: dict[str, date], today: date) -> bool:
    if item.grade > state.grade + 1:
        return False
    seen = last_seen.get(item.id)
    return seen is None or (today - seen).days >= REUSE_DAYS


def plan_session(state: LearnerState, pack: ContentPack, last_seen: dict[str, date] | None = None,
                 today: date | None = None, budget_s: float = 150.0, seed: int | None = None) -> SessionPlan:
    today = today or date.today()
    last_seen = last_seen or {}
    rng = random.Random(seed if seed is not None else zlib.crc32(f"{state.child_id}:{today.isoformat()}".encode()))
    sk = state.skills
    plan: list[PlannedItem] = []
    used = 0.0

    def pick(types: tuple[str, ...], block: str, quota: int, extra_filter=None) -> list[Item]:
        nonlocal used
        cands = [i for i in pack.items_of(*types) if _eligible(i, state, last_seen, today)
                 and (extra_filter is None or extra_filter(i))]
        scored = []
        for it in cands:
            g, why = item_gain(it, state, pack)
            scored.append((g + rng.random() * 1e-3, why, it))
        scored.sort(key=lambda t: -t[0])
        out = []
        for g, why, it in scored[:quota]:
            if used + it.est_seconds > budget_s and block != "closing":
                break
            plan.append(PlannedItem(it.id, it.type, block, round(g, 4), why))
            used += it.est_seconds
            out.append(it)
        return out

    letters_weak = min(sk.get("L2", 0), sk.get("L3", 0)) < 0.8
    if letters_weak:
        pick(("akshara",), "aksharas", 4)
    pick(("word", "nonword"), "words", 6 if letters_weak else 7)
    ready_for_text = sk.get("L7", 0) >= 0.45 or sk.get("L9", 0) >= 0.4
    passage: list[Item] = []
    if ready_for_text:
        band = pack.benchmarks.passage_band_by_grade.get(state.grade, 1)
        if sk.get("L9", 0) < 0.5:
            band = 1
        passage = pick(("passage",), "passage", 1, lambda i: (i.band or 1) == band) or pick(("passage",), "passage", 1)
    reading_mis = [k for k, v in state.misconceptions.items() if k.startswith("READ_") and v.hits > 0]
    if any(k in ("READ_ASP", "READ_VIS") for k in reading_mis) or not state.speech_variants:
        pick(("repeat",), "control", 2)
    # EGMA-style maths block: number identification, quantity comparison, counting objects, missing number.
    # Children still building number sense (M1) get one extra short task so the picture is not one-item thin.
    pick(TAP_TYPES, "numeracy", 4 if sk.get("M1", 0) < 0.6 else 3)

    # close on an item the child very likely gets right (motivation)
    easy = sorted(
        (i for i in pack.items_of("akshara", "tap_number") if all(sk.get(s, 0) >= 0.85 for s in i.skills)),
        key=lambda i: i.id,
    )
    if easy:
        it = easy[rng.randrange(len(easy))]
        plan.append(PlannedItem(it.id, it.type, "closing", 0.0, "success"))
        used += it.est_seconds

    rules = {
        "silence_timeout_s": 6,
        "max_item_seconds": {"akshara": 6, "word": 8, "nonword": 8, "repeat": 8, "passage": 60},
        "discontinue_after_silent_aksharas": 3,
        "on_discontinue": "skip_to_blocks:control,numeracy,closing",
        "passage_has_questions": bool(passage and passage[0].questions),
        "stop_block_after_silent": 3,
    }
    return SessionPlan(state.child_id, plan, round(used, 1), rules, pack.version)


def plan_class_slate(states: list[LearnerState], pack: ContentPack, recent_ids: set[str] | None = None,
                     n: int = 2, today: date | None = None) -> list[dict]:
    """Choose today's whole-class slate problems maximising summed information over the class."""
    recent_ids = recent_ids or set()
    grades = {s.grade for s in states} or {1}
    max_grade = max(grades)
    cands = [i for i in pack.items_of("slate") if i.id not in recent_ids and i.grade <= max_grade + 1]
    scored = []
    for it in cands:
        total = sum(item_gain(it, st, pack)[0] for st in states)
        scored.append((total, it))
    scored.sort(key=lambda t: (-t[0], t[1].id))
    chosen: list[Item] = []
    for _, it in scored:
        if len(chosen) >= n:
            break
        if any(c.op == it.op and c.skills == it.skills for c in chosen) and len(scored) > n * 3:
            continue  # prefer a mix of operations/skills
        chosen.append(it)
    return [{"item_id": i.id, "a": i.a, "b": i.b, "op": i.op, "skills": i.skills} for i in chosen]
