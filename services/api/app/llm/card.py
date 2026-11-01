"""Monday Action Card generation (novelty N5, guide §6.5, §9.3).

Claude Opus may only SELECT activities from the vetted library and adapt wording/examples to the
class's own confusions. Output is schema-validated and checked; any failure → deterministic template.
"""

from __future__ import annotations

import json

import yaml
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..config import get_settings
from ..content.schema import Activity
from . import client

CARD_SYSTEM_HEAD = """You are a warm, practical foundational-learning coach writing a one-screen weekly plan ("Action Card") for a government primary-school teacher in India. The teacher reads simple, plain English. She has 10 minutes per group, chalk, a blackboard, slates and everyday objects.

Hard rules:
1. Choose activities ONLY by `id` from the ACTIVITY LIBRARY below, and only ids listed as candidates for that group. Never invent an activity.
2. Write in simple, warm, plain English. Short sentences. No jargon. Keep Hindi letters/words that children practise (e.g. ि/ी, कमल) in Devanagari.
3. Use the class's own example words/problems given in the summary (they are the exact items children confused).
4. Never use any personal name. Refer to children only by counts ("9 children").
5. Materials: only those listed in the chosen activity.
6. 3-5 steps per group, each step at most ~25 words. Total card readable in 2 minutes.
7. `why_hi` states the evidence honestly. Each confusion has `n_confirmed` (verified twice or more) and `n_suspected` (seen, not yet verified). State confirmed counts plainly ("7 children are confirmed to read ी as ि"). Suspected counts must be hedged ("possibly", "still being checked") and never presented as fact.
8. Add one short encouraging `teacher_tip_hi`.

ACTIVITY LIBRARY (YAML):
"""


HEDGES = ("possibly", "maybe", "may ", "might", "likely", "checking", "checked", "seems")


class CardGroup(BaseModel):
    group_key: str = Field(description="the group key from the summary")
    activity_id: str
    title_hi: str
    why_hi: str
    steps_hi: list[str]
    example_items: list[str]


class CardOut(BaseModel):
    headline_hi: str
    groups: list[CardGroup]
    teacher_tip_hi: str


def library_yaml(activities: dict[str, Activity]) -> str:
    rows = [a.model_dump(exclude={"variations_hi", "reviewed_by"}, exclude_none=True) for a in activities.values()]
    return yaml.safe_dump(rows, allow_unicode=True, sort_keys=False, width=140)


def generate(db: Session, summary: dict, activities: dict[str, Activity], ref: str | None = None,
             fix: list[str] | None = None) -> CardOut:
    system = CARD_SYSTEM_HEAD + library_yaml(activities)
    content = ("CLASS SUMMARY (this week):\n" + json.dumps(summary, ensure_ascii=False, indent=1)
               + "\n\nWrite this week's Action Card. One entry in `groups` per summary group, same group_key.")
    if fix:
        content += "\n\nA previous draft broke these rules; avoid them: " + "; ".join(fix)
    return client.parse(db, purpose="action_card", model=get_settings().model_card, system=system,
                        content=content, output_format=CardOut, max_tokens=6000, effort="medium", ref=ref)


def validate(card: CardOut, summary: dict, activities: dict[str, Activity]) -> list[str]:
    errs = []
    groups = {g["key"]: g for g in summary.get("groups", [])}
    for g in card.groups:
        if g.group_key not in groups:
            errs.append(f"unknown group {g.group_key}")
            continue
        if g.activity_id not in activities:
            errs.append(f"invented activity {g.activity_id}")
        elif g.activity_id not in groups[g.group_key].get("candidate_activities", []):
            errs.append(f"activity {g.activity_id} not a candidate for {g.group_key}")
        if not 2 <= len(g.steps_hi) <= 6:
            errs.append(f"{g.group_key}: {len(g.steps_hi)} steps")
        if any(len(s) > 260 for s in g.steps_hi):
            errs.append(f"{g.group_key}: step too long")
        top = groups[g.group_key].get("top_confusions") or []
        if top and not any(t.get("n_confirmed", 1) for t in top) and not any(h in g.why_hi for h in HEDGES):
            errs.append(f"{g.group_key}: why_hi states a suspected (unverified) confusion as fact")
    if not card.groups:
        errs.append("no groups")
    return errs
