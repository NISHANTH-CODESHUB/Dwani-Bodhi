"""FastAPI application entry point. Stateless — run N replicas behind a load balancer."""

from __future__ import annotations

import logging
import os
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select, text
from starlette.concurrency import run_in_threadpool

from .api import auth, classroom, dashboard, jobs, sync
from .config import REPO_ROOT, get_settings
from .db import SessionLocal, create_all
from .models import Job, LLMCall
from .services.common import pack
from .services.discovery import load_approved_bugs
from .services.upkeep import run_upkeep

log = logging.getLogger("api")


_ready = False
_ready_lock = threading.Lock()


def init_app() -> None:
    """One-time start-up: safety checks, schema, content pack, approved bugs, data upkeep. Idempotent and
    thread-safe; called from the ASGI lifespan and, as a fallback, on the first request (some serverless
    runtimes never send lifespan events)."""
    global _ready
    if _ready:
        return
    with _ready_lock:
        if _ready:
            return
        s = get_settings()
        if s.env == "prod":
            if s.jwt_secret.startswith("dev-only") or len(s.jwt_secret) < 32 or s.phone_pepper == "dev-pepper":
                raise RuntimeError("set strong JWT_SECRET (>=32 chars) and PHONE_PEPPER in production")
            if s.allow_simulated_audio or s.speech_backend == "simulated":
                raise RuntimeError("production needs SPEECH_BACKEND=wav2vec2 or review, and ALLOW_SIMULATED_AUDIO=false")
            if s.auth_disabled:
                raise RuntimeError("AUTH_DISABLED must be false in production")
            if s.is_sqlite and os.environ.get("VERCEL"):
                raise RuntimeError("set DATABASE_URL to a Postgres database: a serverless disk is not persistent")
        if s.auto_migrate:
            from .migrate import upgrade_head
            upgrade_head()
        elif s.env != "prod":
            create_all()  # dev/test convenience; production uses Alembic
        errs = pack().validate()
        if errs:
            raise RuntimeError(f"content pack invalid: {errs[:5]}")
        with SessionLocal() as db:
            load_approved_bugs(db)
            run_upkeep(db)
        _ready = True


def create_app() -> FastAPI:
    s = get_settings()
    logging.basicConfig(level=s.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await run_in_threadpool(init_app)
        yield

    app = FastAPI(title="Dhwani-Bodhi API", version="0.1.0", lifespan=lifespan,
                  description="Misconception-level foundational learning diagnostics (Hindi literacy + numeracy).")
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in s.cors_origins.split(",")],
                       allow_methods=["*"], allow_headers=["*"])

    @app.middleware("http")
    async def timing(request: Request, call_next):
        if not _ready:
            await run_in_threadpool(init_app)
        t0 = time.perf_counter()
        resp = await call_next(request)
        resp.headers["X-Response-Time-ms"] = f"{(time.perf_counter() - t0) * 1000:.1f}"
        return resp

    app.include_router(auth.router)
    app.include_router(classroom.router)
    app.include_router(sync.router)
    app.include_router(dashboard.router)
    app.include_router(jobs.router)

    @app.get("/health")
    def health() -> dict:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
            queued = dict(db.execute(select(Job.queue, func.count()).where(Job.status == "queued").group_by(Job.queue)).all())
            failed = db.scalar(select(func.count()).select_from(Job).where(Job.status == "failed"))
            spend = db.scalar(select(func.coalesce(func.sum(LLMCall.cost_usd), 0.0)))
        finally:
            db.close()
        return {"ok": True, "env": s.env, "content_version": pack().version, "queued": queued,
                "failed_jobs": failed, "llm_mode": "live" if s.llm_live else "offline",
                "speech_backend": s.speech_backend, "llm_spend_usd_total": round(float(spend or 0), 4)}

    @app.get("/metrics", response_class=PlainTextResponse)
    def metrics() -> str:
        db = SessionLocal()
        try:
            rows = db.execute(select(Job.queue, Job.status, func.count()).group_by(Job.queue, Job.status)).all()
        finally:
            db.close()
        lines = ["# TYPE dhwani_jobs gauge"]
        lines += [f'dhwani_jobs{{queue="{q}",status="{st}"}} {n}' for q, st, n in rows]
        return "\n".join(lines) + "\n"

    # Serve the built PWA (apps/web/dist) from the same origin when present.
    dist = Path(REPO_ROOT / "apps" / "web" / "dist")
    if dist.exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        # The shell and service worker must be revalidated on every load, or phones keep running an old
        # app after a deploy; hashed /assets/* files are immutable.
        no_cache = {"Cache-Control": "no-cache"}
        shell = {"index.html", "sw.js", "manifest.webmanifest", "registerSW.js"}

        @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
        def spa(path: str):
            # Unknown API routes must be a JSON 404, never the HTML shell (clients would fail parsing it).
            if path == "v1" or path.startswith(("v1/", "docs/", "health/")):
                return JSONResponse({"detail": "Not Found"}, status_code=404)
            f = dist / path
            if path and f.is_file() and dist in f.resolve().parents:
                return FileResponse(f, headers=no_cache if path in shell else None)
            # A missing *file* (e.g. an unrecorded /audio/hi/x.mp3) must 404, not return the app shell —
            # otherwise clients mistake index.html for the asset.
            if "." in path.rsplit("/", 1)[-1]:
                return PlainTextResponse("not found", status_code=404)
            return FileResponse(dist / "index.html", headers=no_cache)

    return app


app = create_app()
