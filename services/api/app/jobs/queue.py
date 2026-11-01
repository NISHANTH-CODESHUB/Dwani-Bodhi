"""Database-backed job queue (guide §10.2). Postgres: `FOR UPDATE SKIP LOCKED` so any number of
workers can run per queue. SQLite (dev): optimistic claim via conditional UPDATE.

Queues: speech (CPU/GPU heavy) · vision · learner · llm — scale each independently.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, case, select, update
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Blob, Job, Response, SlatePhoto

QUEUE_OF = {
    "score_voice": "speech",
    "process_slate": "vision",
    "update_learner": "learner",
    "build_today": "learner",
    "generate_card": "llm",
    "hypothesize": "llm",
    "purge_blobs": "learner",
}


def now() -> datetime:
    return datetime.now(UTC)


def enqueue(db: Session, kind: str, payload: dict, dedupe_key: str | None = None,
            delay_s: float = 0.0, max_attempts: int = 5) -> Job | None:
    """Add a job. With `dedupe_key`, a job already queued (not yet running) with that key is reused."""
    if dedupe_key:
        existing = db.scalar(select(Job).where(Job.dedupe_key == dedupe_key, Job.status == "queued"))
        if existing:
            return existing
    job = Job(kind=kind, queue=QUEUE_OF.get(kind, "learner"), payload=payload, dedupe_key=dedupe_key,
              run_after=now() + timedelta(seconds=delay_s), max_attempts=max_attempts)
    db.add(job)
    db.flush()
    return job


def claim(db: Session, queues: list[str], worker_id: str) -> Job | None:
    s = get_settings()
    cond = and_(Job.queue.in_(queues), Job.status == "queued", Job.run_after <= now())
    if not s.is_sqlite:
        job = db.scalar(select(Job).where(cond).order_by(Job.run_after).limit(1).with_for_update(skip_locked=True))
        if job is None:
            return None
        job.status, job.locked_by, job.locked_at = "running", worker_id, now()
        job.attempts += 1
        db.commit()
        return job
    candidate = db.scalar(select(Job.id).where(cond).order_by(Job.run_after).limit(1))
    if candidate is None:
        return None
    res = db.execute(
        update(Job).where(Job.id == candidate, Job.status == "queued")
        .values(status="running", locked_by=worker_id, locked_at=now(), attempts=Job.attempts + 1)
    )
    db.commit()
    if res.rowcount != 1:
        return None
    return db.get(Job, candidate)


def complete(db: Session, job: Job) -> None:
    job.status, job.finished_at, job.last_error = "done", now(), None
    db.commit()


def release_media(db: Session, job: Job) -> None:
    """A job gave up for good: its classroom photo / raw child audio must still be deleted (privacy),
    and the object is marked as an error so it stops looking 'pending' forever."""
    payload = job.payload or {}
    if job.kind == "score_voice" and (rid := payload.get("response_id")):
        resp = db.get(Response, rid)
        if resp is not None and resp.status == "pending":
            resp.status, resp.verdict = "error", {"error": "scoring failed"}
        blobs = db.scalars(select(Blob).where(Blob.response_id == rid, Blob.deleted_at.is_(None))).all()
    elif job.kind == "process_slate" and (pid := payload.get("photo_id")):
        photo = db.get(SlatePhoto, pid)
        if photo is not None and photo.status == "pending":
            photo.status = "error"
        blobs = db.scalars(select(Blob).where(Blob.slate_photo_id == pid, Blob.kind == "slate_photo",
                                              Blob.deleted_at.is_(None))).all()
    else:
        return
    for b in blobs:
        b.delete_after = now()  # the next purge_blobs run removes the file


def fail(db: Session, job: Job, error: str) -> None:
    job.last_error = error[-4000:]
    if job.attempts >= job.max_attempts:
        job.status, job.finished_at = "failed", now()
        release_media(db, job)
    else:
        job.status = "queued"
        job.run_after = now() + timedelta(seconds=min(3600, 5 * math.pow(3, job.attempts - 1)))
    job.locked_by = None
    db.commit()


def requeue_stale(db: Session, older_than_s: int = 900) -> int:
    """Recover jobs whose worker died mid-run. A job that has used all its attempts (e.g. one that keeps
    crashing its worker) is failed instead of being retried forever."""
    cutoff = now() - timedelta(seconds=older_than_s)
    stale = and_(Job.status == "running", Job.locked_at < cutoff)
    dead = db.scalars(select(Job).where(stale, Job.attempts >= Job.max_attempts)).all()
    res = db.execute(update(Job).where(stale).values(
        status=case((Job.attempts >= Job.max_attempts, "failed"), else_="queued"), locked_by=None,
        last_error=case((Job.attempts >= Job.max_attempts, "worker stopped while running the job"),
                        else_=Job.last_error)))
    for job in dead:
        db.refresh(job)
        release_media(db, job)
    db.commit()
    return res.rowcount or 0
