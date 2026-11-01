"""Daily classroom plan: who to assess today (N4) + today's discriminating slate problems (N3)."""

from __future__ import annotations

from datetime import UTC, date, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..learner.planner import plan_class_slate, plan_session
from ..learner.scheduler import ChildScheduleInput, pick_today
from ..models import Child, ClassDay, Classroom, LearnerAux, Plan, Response
from .common import pack, today
from .learner import _last_seen, load_state

KEY_SKILLS = ["L3", "L4", "L7", "L9", "L10", "M2", "M5", "M7", "M9"]


def build_today(db: Session, classroom_id: str, day: date | None = None, force: bool = False) -> ClassDay:
    day = day or today()
    existing = db.scalar(select(ClassDay).where(ClassDay.classroom_id == classroom_id, ClassDay.day == day))
    if existing and not force:
        return existing
    cp = pack()
    room = db.get(Classroom, classroom_id)
    kids = db.scalars(select(Child).where(Child.classroom_id == classroom_id, Child.deleted_at.is_(None))).all()
    states, inputs = [], []
    for c in kids:
        st = load_state(db, c, cp)
        aux = db.get(LearnerAux, c.id)
        states.append(st)
        inputs.append(ChildScheduleInput(c.id, st.skills, KEY_SKILLS, aux.last_assessed if aux else None,
                                         bool(st.recheck), c.consent_status == "granted"))
    chosen = pick_today(inputs, day, room.daily_kiosk_budget_min if room else 12.0)
    for sc in chosen:  # ensure every chosen child has a fresh offline plan
        has_plan = db.scalar(select(Plan.id).where(Plan.child_id == sc.child_id, Plan.consumed.is_(False)))
        if not has_plan:
            st = next(s for s in states if s.child_id == sc.child_id)
            db.add(Plan(child_id=sc.child_id, plan=plan_session(st, cp, _last_seen(db, sc.child_id), day).to_dict()))
    recent = set(db.scalars(select(Response.item_id).where(
        Response.item_type == "slate", Response.child_id.in_([c.id for c in kids]),
        Response.created_at >= as_utc_dt(day - timedelta(days=14)))).all()) if kids else set()
    consented = [s for s, c in zip(states, kids) if c.consent_status == "granted"]
    slate = plan_class_slate(consented or states, cp, recent, n=2)
    if existing:
        existing.children = [sc.__dict__ for sc in chosen]
        existing.slate_problems = slate
        row = existing
    else:
        row = ClassDay(classroom_id=classroom_id, day=day, children=[sc.__dict__ for sc in chosen], slate_problems=slate)
        db.add(row)
    try:
        db.commit()
    except IntegrityError:
        # Two first requests of the day raced (e.g. teacher + scheduler): keep the row that won.
        db.rollback()
        other = db.scalar(select(ClassDay).where(ClassDay.classroom_id == classroom_id, ClassDay.day == day))
        if other is None:
            raise
        return other
    return row


def as_utc_dt(d: date):
    from datetime import datetime, time
    return datetime.combine(d, time.min, tzinfo=UTC)


def latest_plan(db: Session, child_id: str) -> dict | None:
    row = db.scalar(select(Plan).where(Plan.child_id == child_id).order_by(Plan.created_at.desc()))
    return {"plan_id": row.id, **row.plan} if row else None

