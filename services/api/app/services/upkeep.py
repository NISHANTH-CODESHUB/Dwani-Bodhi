"""Idempotent data upkeep run at every start (API and demo seeder).

Alembic migrations do the same once for production databases; dev databases are built with
`create_all`, so these rules must also hold there. Every step is a no-op when there is nothing to do.
"""

from __future__ import annotations

import logging

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import ClassroomTeacher, Notification, User
from .students import backfill_register_numbers

log = logging.getLogger("upkeep")


def run_upkeep(db: Session) -> None:
    n = backfill_register_numbers(db)
    # The CRCC role is retired: those accounts can no longer sign in, so remove them.
    crcc = list(db.scalars(select(User.id).where(User.role == "crcc")))
    if crcc:
        db.execute(update(User).where(User.approver_id.in_(crcc)).values(approver_id=None))
        db.execute(delete(ClassroomTeacher).where(ClassroomTeacher.user_id.in_(crcc)))
        db.execute(delete(Notification).where(Notification.recipient_id.in_(crcc)))
        db.execute(delete(User).where(User.id.in_(crcc)))
    # Admin sign-ups need no approval: activate admin requests still waiting from before.
    activated = 0
    if get_settings().admin_self_signup:
        activated = db.execute(update(User).where(User.role == "admin", User.pending.is_(True))
                               .values(pending=False, active=True, approver_id=None)).rowcount or 0
    db.commit()
    if n or crcc or activated:
        log.info("upkeep: %d register numbers assigned, %d CRCC accounts removed, %d admin sign-ups activated",
                 n, len(crcc), activated)
