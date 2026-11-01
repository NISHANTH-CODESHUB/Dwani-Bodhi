"""Dashboards: notifications, student activity (teacher + admin), admin overview, students, teachers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..db import get_db
from ..jobs.queue import enqueue
from ..models import Child, Notification
from ..security import Principal, admin_scope, current_principal, ensure_child, ensure_classroom, require_role
from ..services import notify
from ..services import students as svc

router = APIRouter(prefix="/v1", tags=["dashboards"])
AdminP = Depends(require_role("admin"))


# ---------------------------------------------------------------------------------- notifications
@router.get("/notifications")
def notifications(p: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    return notify.list_for(db, p.user.id)


@router.post("/notifications/{nid}/read")
def read_notification(nid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    n = db.get(Notification, nid)
    if n is None or n.recipient_id != p.user.id:
        raise HTTPException(404, "notification not found")
    if n.read_at is None:
        n.read_at = datetime.now(UTC)
        db.commit()
    return notify.notification_out(n)


@router.post("/notifications/read-all")
def read_all(p: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    db.execute(update(Notification).where(Notification.recipient_id == p.user.id, Notification.read_at.is_(None))
               .values(read_at=datetime.now(UTC)))
    db.commit()
    return notify.list_for(db, p.user.id)


# ---------------------------------------------------------------------------------- student activity
@router.get("/classrooms/{cid}/activity")
def classroom_activity(cid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    ensure_classroom(db, p, cid)
    return svc.classroom_activity(db, cid)


@router.get("/children/{child_id}/activity")
def child_activity(child_id: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    child = ensure_child(db, p, child_id, teacher_only=True)
    return svc.child_activity(db, child)


# ---------------------------------------------------------------------------------- admin
@router.get("/admin/dashboard")
def admin_dashboard(p: Principal = AdminP, db: Session = Depends(get_db)) -> dict:
    return svc.admin_dashboard(db, admin_scope(db, p))


@router.get("/admin/teachers")
def admin_teachers(p: Principal = AdminP, db: Session = Depends(get_db)) -> list[dict]:
    scope = admin_scope(db, p)
    rooms = svc.scoped_rooms(db, scope)
    teachers = svc.scoped_teachers(db, scope, [r.id for r, _ in rooms])
    return svc.teacher_rows(db, teachers, rooms)


@router.get("/admin/students")
def admin_students(p: Principal = AdminP, db: Session = Depends(get_db),
                   school_id: str | None = None, classroom_id: str | None = None,
                   grade: int | None = Query(None, ge=1, le=5),
                   consent: Literal["pending", "granted", "withdrawn"] | None = None,
                   q: str | None = Query(None, max_length=32),
                   limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)) -> dict:
    return svc.admin_students(db, admin_scope(db, p), school_id=school_id, classroom_id=classroom_id, grade=grade,
                              consent=consent, q=q, limit=limit, offset=offset)


class StudentPatch(BaseModel):
    grade: int | None = Field(None, ge=1, le=5)
    consent_status: Literal["pending", "granted", "withdrawn"] | None = None


@router.patch("/admin/students/{child_id}")
def update_student(child_id: str, body: StudentPatch, p: Principal = AdminP, db: Session = Depends(get_db)) -> dict:
    """Admin corrections (grade, parental consent). The teacher's phone picks them up on its next sync."""
    child = ensure_child(db, p, child_id, teacher_only=True)
    if body.grade is not None and body.grade != child.grade:
        child.grade = body.grade
        enqueue(db, "update_learner", {"child_id": child.id}, dedupe_key=f"learner:{child.id}")
    if body.consent_status is not None and body.consent_status != child.consent_status:
        child.consent_status, child.consent_at = body.consent_status, datetime.now(UTC)
    db.commit()
    return svc.student_rows(db, [child])[0]


@router.get("/admin/students/by-register/{register_no}")
def student_by_register(register_no: str, p: Principal = AdminP, db: Session = Depends(get_db)) -> dict:
    child = db.scalar(select(Child).where(Child.register_no == register_no.strip().upper(),
                                          Child.deleted_at.is_(None)))
    if child is None:
        raise HTTPException(404, "no student with this register number")
    ensure_child(db, p, child.id, teacher_only=True)
    return svc.student_rows(db, [child])[0]
