"""Background work for hosts without a long-running worker (Vercel and other serverless platforms).

* `POST /v1/jobs/run` — the app calls this after a sync while results are still pending, so scoring,
  learner updates and plans finish within seconds instead of waiting for a worker.
* `GET /v1/cron/tick` — scheduled maintenance (purge expired media, weekly Action Cards, stale jobs).
  Vercel Cron calls it with `Authorization: Bearer $CRON_SECRET`.

With a classic deployment (Docker: API + `python -m app.jobs.worker --scheduler`) neither is needed.
"""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from ..config import get_settings
from ..jobs.worker import drain_for, pending_jobs, schedule_tick
from ..security import Principal, current_principal

router = APIRouter(prefix="/v1", tags=["jobs"])


def run_inline_jobs() -> dict:
    s = get_settings()
    queues = s.inline_queue_list
    ran = drain_for(s.inline_budget_s, queues) if s.inline_jobs else 0
    return {"ran": ran, "pending": pending_jobs(queues if s.inline_jobs else None)}


@router.post("/jobs/run")
async def run_jobs(_: Principal = Depends(current_principal)) -> dict:
    return await run_in_threadpool(run_inline_jobs)


@router.get("/cron/tick")
async def cron_tick(request: Request) -> dict:
    secret = get_settings().cron_secret
    given = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if not secret or not hmac.compare_digest(given, secret):
        raise HTTPException(401, "cron secret required")

    def tick() -> dict:
        schedule_tick()
        return run_inline_jobs() if get_settings().inline_jobs else {"ran": 0, "pending": pending_jobs()}

    return await run_in_threadpool(tick)
