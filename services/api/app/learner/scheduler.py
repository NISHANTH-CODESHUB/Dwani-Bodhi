"""'Who to assess today' under a teacher-time budget (guide §8.7)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

from .bkt import entropy


@dataclass
class ChildScheduleInput:
    child_id: str
    skills: dict[str, float]
    key_skills: list[str]
    last_assessed: date | None
    recheck_due: bool
    consent: bool = True


@dataclass
class ScheduledChild:
    child_id: str
    priority: float
    reasons: list[str]


W_UNCERTAINTY = 1.0
W_STALENESS = 0.6
W_RECHECK = 1.0
W_NEVER = 2.0


def priority(c: ChildScheduleInput, today: date) -> ScheduledChild:
    reasons: list[str] = []
    keys = c.key_skills or list(c.skills)
    unc = sum(entropy(c.skills.get(s, 0.5)) for s in keys) / max(1, len(keys))
    score = W_UNCERTAINTY * unc
    if unc > 0.7:
        reasons.append("uncertain")
    if c.last_assessed is None:
        score += W_NEVER
        reasons.append("never_assessed")
    else:
        days = (today - c.last_assessed).days
        score += W_STALENESS * min(1.0, days / 14)
        if days >= 14:
            reasons.append("due")
    if c.recheck_due:
        score += W_RECHECK
        reasons.append("recheck")
    return ScheduledChild(c.child_id, round(score, 4), reasons or ["routine"])


def pick_today(children: list[ChildScheduleInput], today: date, budget_minutes: float = 12.0,
               avg_session_minutes: float = 2.5, assessed_today: set[str] | None = None) -> list[ScheduledChild]:
    k = max(1, math.floor(budget_minutes / avg_session_minutes))
    done = assessed_today or set()
    ranked = sorted(
        (priority(c, today) for c in children if c.consent and c.child_id not in done),
        key=lambda s: (-s.priority, s.child_id),
    )
    return ranked[:k]
