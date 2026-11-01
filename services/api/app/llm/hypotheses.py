"""Bug discovery loop (guide §6.2.4): Claude proposes procedures in the safe grammar, our executor
verifies them against real unexplained answers, and a human approves before anything is used."""

from __future__ import annotations

import json

from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import get_settings
from ..diagnosis.bugs import DEFAULT_LIBRARY
from ..diagnosis.procedures import ProcedureSpec, correct_answer, execute
from . import client

HYPO_SYSTEM = """You are an expert in children's arithmetic misconceptions (Brown & Burton BUGGY; VanLehn repair theory).
You receive problems where children's written answers are NOT explained by the existing bug library.
Propose systematic wrong procedures that would produce these exact answers, expressed ONLY in this JSON grammar
(ProcedureSpec): op ('+'|'-'), column ('standard'|'abs_diff'), borrow ('standard'|'no_decrement'|'always'),
zero_top ('standard'|'write_zero'|'write_bottom'), borrow_across_zero ('standard'|'nine_no_propagate'),
carry ('standard'|'drop'|'write_both'), align ('right'|'left'), special ('none'|'op_swap'|'all_digits_sum'|'reverse_answer').
Only propose procedures that differ from the existing library. Prefer procedures that explain several answers.
If no procedure in this grammar fits, say so in `notes` and return an empty list."""


class Proposal(BaseModel):
    spec: ProcedureSpec
    description_en: str
    description_hi: str


class Proposals(BaseModel):
    proposals: list[Proposal]
    notes: str


def propose(db: Session, unexplained: list[dict]) -> Proposals:
    existing = [{"id": b.id, "spec": b.spec.model_dump()} for b in DEFAULT_LIBRARY.bugs.values()]
    content = ("EXISTING LIBRARY:\n" + json.dumps(existing) + "\n\nUNEXPLAINED ANSWERS:\n"
               + json.dumps(unexplained, ensure_ascii=False))
    return client.parse(db, purpose="hypothesis", model=get_settings().model_hypothesis, system=HYPO_SYSTEM,
                        content=content, output_format=Proposals, max_tokens=4000, effort="high")


def verify_proposal(spec: ProcedureSpec, cases: list[dict]) -> tuple[list[str], bool]:
    """Returns (ids of cases reproduced, safe) — unsafe if the procedure 'explains' a correct answer
    by coinciding with correct arithmetic everywhere (i.e. it is not a bug at all)."""
    reproduced = []
    differs_somewhere = False
    for c in cases:
        if spec.op != c["op"]:
            continue
        pred = execute(spec, c["a"], c["b"])
        corr = correct_answer(c["a"], c["b"], c["op"])
        if pred is not None and corr is not None and pred != str(corr):
            differs_somewhere = True
        if pred is not None and pred == c["answer"]:
            reproduced.append(c["response_id"])
    return reproduced, differs_somewhere
