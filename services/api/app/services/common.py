from __future__ import annotations

from datetime import UTC, date, datetime

from ..config import get_settings
from ..content.pack import ContentPack, get_pack


def pack() -> ContentPack:
    return get_pack(get_settings().content_pack_dir)


def as_utc(dt: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes; treat them as UTC so comparisons never mix naive/aware."""
    if dt is None:
        return None
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def utcnow() -> datetime:
    return datetime.now(UTC)


def today() -> date:
    return utcnow().date()


def iso_week(d: date) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"
