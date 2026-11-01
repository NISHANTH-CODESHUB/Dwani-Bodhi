"""In-app notifications (admin dashboard bell): sign-up requests, new admins, approvals."""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..models import Notification, User
from .common import utcnow

SIGNUP_REQUEST = "signup_request"
ADMIN_JOINED = "admin_joined"
ACCOUNT_APPROVED = "account_approved"


def notify(db: Session, recipients: Iterable[User], kind: str, title: str, body: str = "",
           subject_user_id: str | None = None) -> int:
    n = 0
    for u in {u.id: u for u in recipients}.values():
        db.add(Notification(recipient_id=u.id, kind=kind, title=title[:200], body=body,
                            subject_user_id=subject_user_id))
        n += 1
    return n


def resolve(db: Session, subject_user_id: str, kinds: Iterable[str] = (SIGNUP_REQUEST,)) -> None:
    """A request was handled (approved/rejected) by someone: clear it from every admin's bell."""
    db.execute(update(Notification)
               .where(Notification.subject_user_id == subject_user_id, Notification.kind.in_(list(kinds)),
                      Notification.read_at.is_(None))
               .values(read_at=utcnow()))


def notification_out(n: Notification) -> dict:
    return {"id": n.id, "kind": n.kind, "title": n.title, "body": n.body, "subject_user_id": n.subject_user_id,
            "created_at": n.created_at.isoformat() if n.created_at else None,
            "read": n.read_at is not None}


def list_for(db: Session, user_id: str, limit: int = 50) -> dict:
    rows = db.scalars(select(Notification).where(Notification.recipient_id == user_id)
                      .order_by(Notification.created_at.desc()).limit(limit)).all()
    unread = db.scalars(select(Notification.id).where(Notification.recipient_id == user_id,
                                                      Notification.read_at.is_(None))).all()
    return {"unread": len(unread), "items": [notification_out(n) for n in rows]}
