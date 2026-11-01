"""Discovery loop orchestration (guide §6.2.4): collect UNEXPLAINED slate answers, ask Claude for
grammar-constrained procedures, keep only those that reproduce ≥2 answers from different children."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..diagnosis.bugs import DEFAULT_LIBRARY, Bug, BugLibrary
from ..diagnosis.procedures import ProcedureSpec
from ..llm import hypotheses
from ..llm.client import LLMUnavailable
from ..models import BugProposal, Response

MIN_CHILDREN = 2


def run_discovery(db: Session, limit: int = 60) -> dict:
    rows = db.scalars(select(Response).where(Response.item_type == "slate", Response.status.in_(["scored", "confirmed"]))
                      .order_by(Response.created_at.desc()).limit(2000)).all()
    cases = [{"response_id": r.id, "child_id": r.child_id, "a": r.verdict["a"], "b": r.verdict["b"],
              "op": r.verdict["op"], "answer": r.verdict["answer"]}
             for r in rows if r.verdict and r.verdict.get("status") == "UNEXPLAINED"][:limit]
    if len({c["child_id"] for c in cases}) < MIN_CHILDREN:
        return {"cases": len(cases), "proposals": 0}
    try:
        out = hypotheses.propose(db, [{k: c[k] for k in ("a", "b", "op", "answer")} for c in cases])
    except LLMUnavailable as e:
        return {"cases": len(cases), "error": str(e)}
    kept = 0
    by_id = {c["response_id"]: c for c in cases}
    for prop in out.proposals:
        reproduced, is_bug = hypotheses.verify_proposal(prop.spec, cases)
        kids = {by_id[r]["child_id"] for r in reproduced}
        if is_bug and len(kids) >= MIN_CHILDREN:
            db.add(BugProposal(spec=prop.spec.model_dump(), description=f"{prop.description_en} | {prop.description_hi}",
                               explains=reproduced))
            kept += 1
    db.commit()
    return {"cases": len(cases), "proposals": len(out.proposals), "kept": kept}


def bug_from_proposal(bp: BugProposal) -> Bug:
    spec = ProcedureSpec(**bp.spec)
    en, _, hi = bp.description.partition(" | ")
    skills = ("M9",) if spec.op == "-" else ("M7",)
    # No vetted activity targets a newly discovered bug yet, so cards fall back to level-based activities.
    return Bug(f"DISC_{bp.id[:8].upper()}", spec, skills, en.strip(), (hi or en).strip(), "discovered")


def load_approved_bugs(db: Session, library: BugLibrary = DEFAULT_LIBRARY) -> int:
    """Add human-approved discovered bugs to the live library (called at API/worker start and on approval)."""
    known = {b.spec for b in library.bugs.values()}
    added = 0
    for bp in db.scalars(select(BugProposal).where(BugProposal.status == "approved")):
        bug = bug_from_proposal(bp)
        if bug.id not in library.bugs and bug.spec not in known:
            library.add(bug)
            known.add(bug.spec)
            added += 1
    return added
