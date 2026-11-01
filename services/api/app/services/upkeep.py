"""Idempotent data upkeep run at every start (API and demo seeder). Every step is a no-op when there is
nothing to do."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from .students import backfill_register_numbers

log = logging.getLogger("upkeep")


def run_upkeep(db: Session) -> None:
    n = backfill_register_numbers(db)
    db.commit()
    if n:
        log.info("upkeep: %d register numbers assigned", n)
