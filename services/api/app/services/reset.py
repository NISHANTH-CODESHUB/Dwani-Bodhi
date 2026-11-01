"""Full data reset ("fresh start"): every teacher account, class, child, answer, plan, card, job and media
file is deleted. The schema, the content pack and the reviewed bug library stay."""

from __future__ import annotations

import contextlib

from sqlalchemy import delete, func, select

from ..db import SessionLocal
from ..models import (
    ActionCard,
    AssessmentSession,
    AuditSample,
    AuthAttempt,
    Blob,
    BlobData,
    Child,
    ClassDay,
    Classroom,
    ClassroomTeacher,
    Job,
    LearnerAux,
    LLMCall,
    MisconceptionState,
    Plan,
    Recheck,
    Response,
    School,
    SkillState,
    SlatePhoto,
    TeacherOverride,
    User,
)
from ..storage import get_store

# Children before parents (foreign keys).
ORDER = [TeacherOverride, AuditSample, Recheck, ActionCard, Response, AssessmentSession, SlatePhoto, Plan,
         SkillState, MisconceptionState, LearnerAux, ClassDay, Child, ClassroomTeacher, Classroom, School,
         Job, LLMCall, AuthAttempt, BlobData, Blob, User]


def reset_all_data() -> dict[str, int]:
    counts: dict[str, int] = {}
    with SessionLocal() as db:
        store = get_store(db)
        for key in db.scalars(select(Blob.key).where(Blob.deleted_at.is_(None))).all():
            with contextlib.suppress(Exception):  # a missing file is fine; the row goes anyway
                store.delete(key)
        for model in ORDER:
            counts[model.__tablename__] = int(db.scalar(select(func.count()).select_from(model)) or 0)
            db.execute(delete(model))
        db.commit()
    return counts
