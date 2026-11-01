"""Classroom endpoints (the class teacher only): classes, bootstrap, roster, today, cards, profiles,
confirm queue."""

from __future__ import annotations

import zlib
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response as RawResponse
from pydantic import BaseModel, Field
from sqlalchemy import String, and_, cast, delete, or_, select, update
from sqlalchemy.orm import Session

from ..db import get_db
from ..jobs.queue import enqueue
from ..learner.misconceptions import SUSPECTED
from ..llm import explain as llm_explain
from ..llm.client import LLMUnavailable
from ..models import (
    AssessmentSession,
    Blob,
    Child,
    Classroom,
    Job,
    LearnerAux,
    LLMCall,
    MisconceptionState,
    Plan,
    Recheck,
    Response,
    SkillState,
    TeacherOverride,
)
from ..security import Principal, current_principal, ensure_child, ensure_classroom
from ..services import accounts, planning, reports
from ..services import cards as card_svc
from ..services.common import as_utc, pack
from ..services.slates import confirm_slate_answer
from ..services.students import assign_register_no
from ..speech.mutations import RULES
from ..storage import get_store

router = APIRouter(prefix="/v1", tags=["classroom"])


@router.get("/bootstrap")
def bootstrap(_: Principal = Depends(current_principal)) -> dict:
    """Everything the phone caches for offline use. Clients compare `version` and re-download on change."""
    cp = pack()
    return {
        "version": cp.version, "language": cp.language,
        "items": [i.model_dump(exclude_none=True) for i in cp.items.values()],
        "prompts": cp.prompts,
        "skills": [{"id": s.id, "domain": s.domain, "name_hi": s.name_hi, "name_en": s.name_en}
                   for s in cp.graph.skills.values()],
        "ladders": {d: [{"id": r.id, "name_hi": r.name_hi, "name_en": r.name_en} for r in rungs]
                    for d, rungs in cp.graph.ladders.items()},
        "benchmarks": cp.benchmarks.model_dump(),
        "activities": {a.id: {"title_hi": a.title_hi, "materials": a.materials, "minutes": a.minutes}
                       for a in cp.activities.values()},
    }


# ---------------------------------------------------------------------------------- classes
@router.post("/classrooms")
def create_classroom(body: accounts.ClassroomFields, p: Principal = Depends(current_principal),
                     db: Session = Depends(get_db)) -> dict:
    """A teacher adds another class (same or another school). Returns the updated class list."""
    room = accounts.create_classroom(db, p.user, body)
    db.commit()
    return {"id": room.id, "classrooms": accounts.classrooms_for(db, p.user)}


class ClassroomPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    grades: list[int] | None = Field(None, min_length=1, max_length=5)
    region_profile: str | None = Field(None, max_length=64)
    daily_kiosk_budget_min: float | None = Field(None, ge=3, le=60)


@router.patch("/classrooms/{cid}")
def update_classroom(cid: str, body: ClassroomPatch, p: Principal = Depends(current_principal),
                     db: Session = Depends(get_db)) -> dict:
    room: Classroom = ensure_classroom(db, p, cid)
    if body.name is not None:
        name = " ".join(body.name.split())
        if not name:
            raise HTTPException(422, "class name must not be empty")
        room.name = name
    if body.grades is not None:
        if any(g < 1 or g > 5 for g in body.grades):
            raise HTTPException(422, "grades must be between 1 and 5")
        room.grades = sorted(set(body.grades))
    if body.region_profile is not None:
        room.region_profile = accounts.check_region(body.region_profile)
    if body.daily_kiosk_budget_min is not None:
        room.daily_kiosk_budget_min = body.daily_kiosk_budget_min
    db.commit()
    return {"id": room.id, "classrooms": accounts.classrooms_for(db, p.user)}


# ----------------------------------------------------------------------------------- roster
class ChildIn(BaseModel):
    id: str = Field(min_length=36, max_length=36, description="UUID generated on the phone")
    grade: int = Field(ge=1, le=5)
    aruco_slot: int = Field(ge=0, le=99)
    gender: Literal["f", "m", "x"] | None = None
    consent_status: Literal["pending", "granted", "withdrawn"] = "pending"


def _released_slot(child_id: str) -> int:
    """Negative, per-child unique slot for deleted children (keeps the (classroom, slot) constraint)."""
    return -1 - (zlib.crc32(child_id.encode()) & 0x3FFFFFFF)


def _child_out(c: Child) -> dict:
    return {"id": c.id, "register_no": c.register_no, "grade": c.grade, "aruco_slot": c.aruco_slot,
            "gender": c.gender, "consent_status": c.consent_status}


@router.get("/classrooms/{cid}/children")
def list_children(cid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> list[dict]:
    ensure_classroom(db, p, cid)
    rows = db.scalars(select(Child).where(Child.classroom_id == cid, Child.deleted_at.is_(None))
                      .order_by(Child.aruco_slot)).all()
    return [_child_out(c) for c in rows]


@router.post("/classrooms/{cid}/children")
def upsert_child(cid: str, body: ChildIn, p: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    ensure_classroom(db, p, cid)
    erased = db.get(Child, body.id)
    if erased is not None and erased.deleted_at is not None:
        # A stale offline edit must never bring an erased child (and its consent) back.
        raise HTTPException(410, "this child's data was erased")
    clash = db.scalar(select(Child).where(Child.classroom_id == cid, Child.aruco_slot == body.aruco_slot,
                                          Child.id != body.id))
    if clash is not None and clash.deleted_at is None:
        raise HTTPException(409, f"ID card {body.aruco_slot} already assigned")
    if clash is not None:  # a deleted child still holds the slot under the unique constraint → release it
        clash.aruco_slot = _released_slot(clash.id)
        db.flush()
    c = db.get(Child, body.id)
    if c is None:
        c = Child(id=body.id, classroom_id=cid, grade=body.grade, aruco_slot=body.aruco_slot,
                  created_at=datetime.now(UTC))
        db.add(c)
        db.flush()
        assign_register_no(db, c)  # permanent STU-<year>-<seq>, returned to the phone
    elif c.classroom_id != cid:
        raise HTTPException(409, "child belongs to another classroom")
    c.grade, c.aruco_slot, c.gender = body.grade, body.aruco_slot, body.gender
    if body.consent_status != c.consent_status:
        c.consent_status = body.consent_status
        c.consent_at = datetime.now(UTC)
    db.commit()
    return _child_out(c)


@router.delete("/children/{child_id}")
def delete_child(child_id: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    """Right to erasure: removes all learning data and stored media for this child."""
    c = ensure_child(db, p, child_id)
    responses = db.scalars(select(Response).where(Response.child_id == child_id)).all()
    resp_ids = [r.id for r in responses]
    crop_keys = {(r.payload or {}).get("crop_key") for r in responses if r.item_type == "slate"} - {None}
    for b in db.scalars(select(Blob).where(or_(Blob.response_id.in_(resp_ids), Blob.key.in_(crop_keys)))):
        get_store(db).delete(b.key)
        db.delete(b)
    db.execute(delete(TeacherOverride).where(TeacherOverride.response_id.in_(resp_ids)))
    for model in (Response, SkillState, MisconceptionState, Plan, Recheck, LearnerAux, AssessmentSession):
        db.execute(delete(model).where(model.child_id == child_id))
    # Pending jobs that name this child, and the cost-log back-reference.
    for j in db.scalars(select(Job).where(Job.status != "running", cast(Job.payload, String).contains(child_id))):
        if (j.payload or {}).get("child_id") == child_id:
            db.delete(j)
    db.execute(update(LLMCall).where(LLMCall.ref == child_id).values(ref=None))
    c.deleted_at = datetime.now(UTC)
    c.consent_status = "withdrawn"
    c.aruco_slot = _released_slot(c.id)  # ID card can be reused immediately
    db.commit()
    return {"deleted": child_id}


# ------------------------------------------------------------------------------------ today
@router.get("/classrooms/{cid}/today")
def today(cid: str, force: bool = False, p: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    ensure_classroom(db, p, cid)
    day = planning.build_today(db, cid, force=force)
    return {"day": day.day.isoformat(), "slate_problems": day.slate_problems,
            "children": [{**c, "plan": planning.latest_plan(db, c["child_id"])} for c in day.children]}


@router.get("/children/{child_id}/plan")
def child_plan(child_id: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    ensure_child(db, p, child_id)
    plan = planning.latest_plan(db, child_id)
    if plan is None:
        from ..services.learner import update_child
        update_child(db, child_id)
        plan = planning.latest_plan(db, child_id)
    return plan or {}


# ------------------------------------------------------------------------------------ cards
@router.get("/classrooms/{cid}/card")
def get_card(cid: str, regenerate: bool = False, p: Principal = Depends(current_principal),
             db: Session = Depends(get_db)) -> dict:
    ensure_classroom(db, p, cid)
    row = card_svc.generate_card(db, cid, force=regenerate)
    return {"id": row.id, "week": row.week, "source": row.source, "card": row.card, "summary": row.summary,
            "created_at": row.created_at.isoformat()}


@router.get("/classrooms/{cid}/overview")
def overview(cid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    ensure_classroom(db, p, cid)
    return reports.class_overview(db, cid)


@router.get("/classrooms/{cid}/efficacy")
def class_efficacy(cid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> list[dict]:
    ensure_classroom(db, p, cid)
    return card_svc.efficacy(db, [cid])


# -------------------------------------------------------------------------------- profiles
@router.get("/children/{child_id}/profile")
def profile(child_id: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    c = ensure_child(db, p, child_id)
    return reports.child_evidence(db, c)


@router.get("/children/{child_id}/explain")
def explain(child_id: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    c = ensure_child(db, p, child_id)
    ev = reports.child_evidence(db, c)
    slim = {k: ev[k] for k in ("grade", "levels", "confusions", "checking", "wcpm_history")}
    slim["skills"] = [s for s in ev["skills"] if s["p"] is not None]
    try:
        out, source = llm_explain.generate(db, slim, ref=child_id), "llm"
    except LLMUnavailable:
        out, source = llm_explain.template(slim), "template"
    return {"source": source, **out.model_dump()}


# ------------------------------------------------------------------- "not sure" queue
@router.get("/classrooms/{cid}/unsure")
def unsure(cid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> list[dict]:
    """Items the system could not score confidently, most useful first. The teacher's time budget is
    0–3 min/week (GUIDE §5.3), so ranking matters more than completeness."""
    ensure_classroom(db, p, cid)
    kids = db.scalars(select(Child.id).where(Child.classroom_id == cid, Child.deleted_at.is_(None))).all()
    rows = db.scalars(select(Response).where(Response.child_id.in_(kids), Response.status == "unsure")
                      .order_by(Response.created_at.desc()).limit(200)).all()
    suspected = {(m.child_id, m.mis_id) for m in db.scalars(select(MisconceptionState).where(
        MisconceptionState.child_id.in_(kids), MisconceptionState.status == SUSPECTED))}
    cp = pack()
    now = datetime.now(UTC)
    # One query for all media still on file (purged crops/audio must not be offered for review).
    crop_keys = {(r.payload or {}).get("crop_key") for r in rows if r.item_type == "slate"} - {None}
    live = db.scalars(select(Blob).where(Blob.deleted_at.is_(None), or_(
        and_(Blob.kind == "audio", Blob.response_id.in_([r.id for r in rows])), Blob.key.in_(crop_keys)))).all()
    audio_of = {b.response_id: b for b in live if b.kind == "audio"}
    live_keys = {b.key for b in live}
    out = []
    for r in rows:
        item = cp.items.get(r.item_id)
        audio = audio_of.get(r.id)
        has_media = audio is not None or (r.item_type == "slate" and (r.payload or {}).get("crop_key") in live_keys)
        probes = [f"READ_{p}" for p in (item.probes if item else [])]
        priority, reason = 0.0, None
        if any((r.child_id, m) in suspected for m in probes):
            priority, reason = priority + 3, "verifies_suspected"  # one answer can confirm or clear a confusion
        if r.item_type == "slate" and (r.verdict or {}).get("status") == "NEEDS_READING":
            priority, reason = priority + 2, reason or "needs_reading"
        if (audio is not None and audio.delete_after is not None
                and (as_utc(audio.delete_after) - now).total_seconds() < 2 * 86400):
            priority, reason = priority + 1, reason or "expiring"
        if not has_media:
            priority -= 10  # nothing to listen to or look at: the teacher cannot verify it
        out.append({"id": r.id, "child_id": r.child_id, "item_id": r.item_id, "type": r.item_type,
                    "text": item.text if item else None, "verdict": r.verdict,
                    "problem": (r.payload or {}).get("problem"), "priority": priority, "reason": reason,
                    "media": f"/v1/responses/{r.id}/media" if has_media else None})
    out.sort(key=lambda e: -e["priority"])  # stable: newest first within a priority
    return out[:50]


@router.get("/responses/{rid}/media")
def media(rid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> RawResponse:
    r = db.get(Response, rid)
    if r is None:
        raise HTTPException(404, "not found")
    ensure_child(db, p, r.child_id)
    if r.item_type == "slate":
        key = (r.payload or {}).get("crop_key")
        if not key:
            raise HTTPException(404, "no crop")
        b = db.scalar(select(Blob).where(Blob.key == key, Blob.deleted_at.is_(None)))
        if b is None:
            raise HTTPException(410, "slate crop already deleted (privacy retention)")
    else:
        b = db.scalar(select(Blob).where(Blob.response_id == rid, Blob.kind == "audio", Blob.deleted_at.is_(None)))
        if b is None:
            raise HTTPException(410, "audio already deleted (privacy retention)")
    try:
        data = get_store(db).get(b.key)
    except FileNotFoundError as e:
        raise HTTPException(410, "media no longer stored") from e
    return RawResponse(data, media_type=b.mime or "image/jpeg", headers={"Cache-Control": "private, no-store"})


class ConfirmIn(BaseModel):
    correct: bool | None = None  # voice/tap items: was the reading correct?
    rule: str | None = None  # optional error type chosen by the teacher
    answer: str | None = None  # slate items: the answer the teacher reads on the crop


@router.post("/responses/{rid}/confirm")
def confirm(rid: str, body: ConfirmIn, p: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    r = db.get(Response, rid)
    if r is None:
        raise HTTPException(404, "not found")
    ensure_child(db, p, r.child_id)
    # Only queued items can be confirmed. Re-confirming an already-applied response would add its evidence
    # to the learner model a second time (incremental updates cannot subtract the old verdict).
    if r.status != "unsure":
        raise HTTPException(409, f"response is '{r.status}', only 'unsure' responses can be confirmed")
    if body.rule is not None and body.rule not in RULES:
        raise HTTPException(422, f"unknown error rule; expected one of {', '.join(RULES)}")
    old = r.verdict
    if r.item_type == "slate":
        if body.answer is None or not (r.payload or {}).get("problem"):
            raise HTTPException(422, "answer is required for slate items")
        confirm_slate_answer(r, body.answer)
    else:
        if body.correct is None:
            raise HTTPException(422, "correct is required")
        v = dict(r.verdict or {})
        v.update(status="CORRECT" if body.correct else "ERROR", rule=None if body.correct else body.rule,
                 confidence=1.0, teacher_confirmed=True)
        r.verdict, r.confidence, r.status = v, 1.0, "confirmed"
    r.applied = False
    db.add(TeacherOverride(response_id=r.id, user_id=p.user.id, old=old, new=r.verdict))
    enqueue(db, "update_learner", {"child_id": r.child_id}, dedupe_key=f"learner:{r.child_id}")
    db.commit()
    return {"id": r.id, "status": r.status, "verdict": r.verdict}
