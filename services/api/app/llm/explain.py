"""Evidence-grounded plain-English explanation of a child's profile for the teacher (guide §9.1).

The server never knows the child's name: the output uses the placeholder {{child}}, which the
phone replaces from its local roster.
"""

from __future__ import annotations

import json

from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import get_settings
from . import client

EXPLAIN_SYSTEM = """You explain one child's learning evidence to their government-school teacher in simple, warm, plain English.
Use ONLY the evidence JSON provided — never add facts, guesses about home life, or labels like "weak" or "slow".
Refer to the child only as {{child}}. Mention how sure the system is (use the given confidence words).
Say what the child CAN do first, then the one or two specific confusions with an example, then one next step.
At most 5 short bullet points."""


class Explanation(BaseModel):
    summary_hi: str
    bullets_hi: list[str]
    next_step_hi: str


def generate(db: Session, evidence: dict, ref: str | None = None) -> Explanation:
    return client.parse(db, purpose="explain", model=get_settings().model_explain, system=EXPLAIN_SYSTEM,
                        content="EVIDENCE:\n" + json.dumps(evidence, ensure_ascii=False, indent=1),
                        output_format=Explanation, max_tokens=1500, effort="low", ref=ref)


def template(evidence: dict) -> Explanation:
    lv = evidence.get("levels", {})
    lit = lv.get("literacy", {}).get("name_hi", "—")
    num = lv.get("numeracy", {}).get("name_hi", "—")
    bullets = [f"Reading: level {lit}; Maths: level {num}."]
    for m in evidence.get("confusions", [])[:2]:
        ex = f" (e.g. {m['examples'][0]})" if m.get("examples") else ""
        bullets.append(f"{m['description_hi']}{ex} — {m['certainty_hi']}.")
    if evidence.get("checking"):
        bullets.append("Some things are still being checked; we will look again in the next session.")
    nxt = evidence.get("suggested_activity_hi") or "Include them in this week's card activity."
    return Explanation(summary_hi=f"{{{{child}}}}'s current level: Reading — {lit}, Maths — {num}.",
                       bullets_hi=bullets, next_step_hi=nxt)
