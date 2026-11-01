"""TaRL-compatible level assignment with honest uncertainty (guide §8.5).

Level = highest rung whose key skills all have P(mastery) ≥ MASTERED, with all lower rungs also
passed. If the next rung up has any skill in the uncertain band, the level is flagged "checking".
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .graph import SkillGraph

MASTERED = 0.80
UNCERTAIN_LO, UNCERTAIN_HI = 0.35, 0.65


@dataclass
class LevelResult:
    domain: str
    rung_index: int  # -1 = below the first rung (Beginner)
    rung_id: str
    name_en: str
    name_hi: str
    certain: bool
    next_rung_id: str | None
    blocking_skills: list[str]  # skills holding the child below the next rung

    def to_dict(self) -> dict:
        return asdict(self)


def assign_level(graph: SkillGraph, skills: dict[str, float], domain: str) -> LevelResult:
    rungs = graph.ladders.get(domain, [])
    idx = -1
    for i, r in enumerate(rungs):
        if all(skills.get(s, 0.0) >= MASTERED for s in r.skills):
            idx = i
        else:
            break
    nxt = rungs[idx + 1] if idx + 1 < len(rungs) else None
    blocking = [s for s in (nxt.skills if nxt else ()) if skills.get(s, 0.0) < MASTERED]
    uncertain = any(UNCERTAIN_LO <= skills.get(s, 0.0) <= UNCERTAIN_HI for s in blocking)
    cur_uncertain = idx >= 0 and any(skills.get(s, 0.0) < MASTERED + 0.05 for s in rungs[idx].skills)
    if idx >= 0:
        r = rungs[idx]
        rid, en, hi = r.id, r.name_en, r.name_hi
    else:
        rid, en, hi = "beginner", "Beginner", "Beginner"
    return LevelResult(domain, idx, rid, en, hi, not (uncertain or cur_uncertain),
                       nxt.id if nxt else None, blocking)
