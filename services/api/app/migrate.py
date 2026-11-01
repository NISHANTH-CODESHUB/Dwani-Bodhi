"""Apply Alembic migrations from inside the app (AUTO_MIGRATE=true).

Serverless deploys (Vercel) have no release step in which to run `alembic upgrade head`, so the first
cold start does it. On Postgres an advisory lock makes concurrent cold starts wait for one another
instead of racing; a database that is already at head costs one cheap version check.
"""

from __future__ import annotations

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from .config import get_settings
from .db import get_engine

log = logging.getLogger("migrate")
API_DIR = Path(__file__).resolve().parents[1]
_LOCK_ID = 0x0D4A_B0D1  # arbitrary, constant advisory-lock key for this app


def upgrade_head() -> None:
    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "migrations"))
    cfg.attributes["configure_logger"] = False
    engine = get_engine()
    if engine.dialect.name != "postgresql":
        command.upgrade(cfg, "head")
        return
    with engine.connect() as conn:
        conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": _LOCK_ID})
        try:
            command.upgrade(cfg, "head")
        finally:
            conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _LOCK_ID})
            conn.commit()
    log.info("database schema is at head (%s)", get_settings().database_url.split("@")[-1])
