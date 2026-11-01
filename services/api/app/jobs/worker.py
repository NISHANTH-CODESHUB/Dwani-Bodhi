"""Job worker. Run one process per queue set; scale horizontally by running more processes.

    python -m app.jobs.worker --queues speech            # on CPU/GPU speech nodes
    python -m app.jobs.worker --queues vision,learner,llm --scheduler
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import socket
import time
import traceback
from datetime import timedelta

from sqlalchemy import select

from ..config import get_settings
from ..db import SessionLocal
from ..models import ActionCard, Child, Classroom, Job, Response
from ..services import cards, planning, scoring, slates
from ..services.common import iso_week, today, utcnow
from ..services.learner import update_child
from .queue import claim, complete, enqueue, fail, requeue_stale

log = logging.getLogger("worker")


def _hypothesize(db, payload):
    from ..services.discovery import run_discovery
    return run_discovery(db)


HANDLERS = {
    "score_voice": lambda db, p: scoring.score_voice(db, p["response_id"]),
    "process_slate": lambda db, p: slates.process_slate(db, p["photo_id"]),
    "update_learner": lambda db, p: update_child(db, p["child_id"]),
    "build_today": lambda db, p: planning.build_today(db, p["classroom_id"], force=True),
    "generate_card": lambda db, p: cards.generate_card(db, p["classroom_id"], force=p.get("force", False)),
    "hypothesize": _hypothesize,
    "purge_blobs": lambda db, p: scoring.purge_expired_blobs(db),
}


def run_once(queues: list[str], worker_id: str) -> bool:
    db = SessionLocal()
    try:
        job = claim(db, queues, worker_id)
        if job is None:
            return False
        handler = HANDLERS.get(job.kind)
        try:
            if handler is None:
                raise RuntimeError(f"no handler for {job.kind}")
            handler(db, job.payload)
            db.commit()
            complete(db, job)
        except Exception as e:
            db.rollback()
            log.exception("job %s (%s) failed", job.id, job.kind)
            job = db.merge(job)
            fail(db, job, f"{e}\n{traceback.format_exc()}")
        return True
    finally:
        db.close()


def drain(queues: list[str] | None = None, max_jobs: int = 10_000) -> int:
    """Process jobs until the queues are empty (used by tests, the demo seeder and the CLI)."""
    queues = queues or ["speech", "vision", "learner", "llm"]
    n = 0
    while n < max_jobs and run_once(queues, "drain"):
        n += 1
    return n


def schedule_tick() -> None:
    """Periodic maintenance: purge expired media, recover stale jobs, ensure this week's cards exist."""
    db = SessionLocal()
    try:
        requeue_stale(db)
        enqueue(db, "purge_blobs", {}, dedupe_key="purge_blobs")
        week = iso_week(today())
        have = set(db.scalars(select(ActionCard.classroom_id).where(ActionCard.week == week)).all())
        active_since = utcnow() - timedelta(days=21)
        # Only classrooms with recent activity get a card (an LLM call each): not every room whenever any is.
        active_rooms = set(db.scalars(
            select(Child.classroom_id).join(Response, Response.child_id == Child.id)
            .where(Response.created_at >= active_since, Child.deleted_at.is_(None)).distinct()).all())
        for room in db.scalars(select(Classroom)):
            if room.id not in have and room.id in active_rooms:
                enqueue(db, "generate_card", {"classroom_id": room.id}, dedupe_key=f"card:{room.id}:{week}")
        # Weekly bug discovery over unexplained slate answers (no-op offline; capped by the LLM budget).
        key = f"hypothesize:{week}"
        if db.scalar(select(Job.id).where(Job.dedupe_key == key)) is None:
            enqueue(db, "hypothesize", {}, dedupe_key=key)
        db.commit()
    finally:
        db.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--queues", default="speech,vision,learner,llm")
    ap.add_argument("--scheduler", action="store_true", help="also run periodic maintenance (one per cluster)")
    ap.add_argument("--schedule-every", type=int, default=600)
    args = ap.parse_args()
    logging.basicConfig(level=get_settings().log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    queues = [q.strip() for q in args.queues.split(",") if q.strip()]
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    stop = {"flag": False}
    signal.signal(signal.SIGINT, lambda *_: stop.update(flag=True))
    signal.signal(signal.SIGTERM, lambda *_: stop.update(flag=True))
    if "speech" in queues:
        from ..speech.acoustic import get_acoustic_model
        get_acoustic_model()  # load once, before taking jobs
    from ..services.discovery import load_approved_bugs
    with SessionLocal() as db:
        load_approved_bugs(db)
    log.info("worker %s on queues %s", worker_id, queues)
    last_tick = 0.0
    while not stop["flag"]:
        if args.scheduler and time.time() - last_tick > args.schedule_every:
            schedule_tick()
            last_tick = time.time()
        if not run_once(queues, worker_id):
            time.sleep(get_settings().worker_poll_seconds)
    log.info("worker stopped")


if __name__ == "__main__":
    main()
