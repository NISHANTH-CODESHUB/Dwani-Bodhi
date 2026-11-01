"""Read models for the teacher app (child-level data never includes names)."""

from __future__ import annotations

from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..learner.misconceptions import CONFIRMED, SUSPECTED
from ..models import Child, LearnerAux, MisconceptionState, Response, SkillState
from .cards import _examples
from .catalog import certainty_hi, describe
from .common import pack


def child_evidence(db: Session, child: Child) -> dict:
    cp = pack()
    aux = db.get(LearnerAux, child.id)
    skills = {r.skill_id: round(r.p, 3) for r in db.scalars(select(SkillState).where(SkillState.child_id == child.id))}
    confusions = []
    for m in db.scalars(select(MisconceptionState).where(MisconceptionState.child_id == child.id,
                                                         MisconceptionState.status.in_([CONFIRMED, SUSPECTED]))):
        mean = m.alpha / (m.alpha + m.beta)
        d = describe(m.mis_id)
        confusions.append({**d, "status": m.status, "mean": round(mean, 3),
                           "certainty_hi": certainty_hi(mean, m.status == CONFIRMED),
                           "examples": _examples(db, [child.id], m.mis_id, 3)})
    confusions.sort(key=lambda x: (x["status"] != CONFIRMED, -x["mean"]))
    recent = db.scalars(select(Response).where(Response.child_id == child.id).order_by(Response.created_at.desc())
                        .limit(30)).all()
    return {
        "child_id": child.id, "grade": child.grade, "aruco_slot": child.aruco_slot,
        "levels": (aux.levels if aux else {}) or {},
        "skills": [{"id": sid, "name_hi": cp.graph.skills[sid].name_hi, "domain": cp.graph.skills[sid].domain,
                    "p": skills.get(sid), "checking": sid in set((aux.recheck if aux else []) or [])}
                   for sid in cp.graph.skills],
        "confusions": confusions,
        "checking": sorted((aux.recheck if aux else []) or []),
        "wcpm_history": (aux.wcpm_history if aux else []) or [],
        "speech_variants": (aux.speech_variants if aux else []) or [],
        "last_assessed": aux.last_assessed.isoformat() if aux and aux.last_assessed else None,
        "recent": [{"id": r.id, "item_id": r.item_id, "type": r.item_type, "status": r.status,
                    "verdict": _short_verdict(r), "confidence": r.confidence,
                    "at": r.created_at.isoformat() if r.created_at else None} for r in recent],
    }


def _short_verdict(r: Response) -> dict:
    v = r.verdict or {}
    if r.item_type == "passage" and "wcpm" in v:
        return {k: v.get(k) for k in ("wcpm", "wcpm_low", "wcpm_high", "accuracy", "attempted", "correct")}
    keep = ("status", "rule", "detail", "produced", "target", "correct", "chosen", "probe", "answer", "matching_bugs")
    return {k: v[k] for k in keep if k in v}


def class_overview(db: Session, classroom_id: str) -> dict:
    kids = db.scalars(select(Child).where(Child.classroom_id == classroom_id, Child.deleted_at.is_(None))).all()
    lit, num = Counter(), Counter()
    rows = []
    for c in kids:
        aux = db.get(LearnerAux, c.id)
        lv = (aux.levels if aux else {}) or {}
        lit[lv.get("literacy", {}).get("rung_id", "unassessed")] += 1
        num[lv.get("numeracy", {}).get("rung_id", "unassessed")] += 1
        n_conf = db.scalar(select(func.count()).select_from(MisconceptionState).where(
            MisconceptionState.child_id == c.id, MisconceptionState.status == CONFIRMED))
        rows.append({"child_id": c.id, "grade": c.grade, "aruco_slot": c.aruco_slot, "consent": c.consent_status,
                     "literacy": lv.get("literacy"), "numeracy": lv.get("numeracy"),
                     "confirmed_confusions": n_conf,
                     "last_assessed": aux.last_assessed.isoformat() if aux and aux.last_assessed else None})
    return {"n_children": len(kids), "literacy_levels": dict(lit), "numeracy_levels": dict(num), "children": rows}
