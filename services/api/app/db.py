"""Database engine/session. Postgres in production; SQLite for dev/tests. Schema via Alembic."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import JSON, create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings

JSONType = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        s = get_settings()
        kwargs: dict = {"pool_pre_ping": True, "future": True}
        if s.is_sqlite:
            path = s.database_url.replace("sqlite:///", "")
            if path and path != ":memory:":
                Path(path).parent.mkdir(parents=True, exist_ok=True)
            kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
        else:
            kwargs.update(pool_size=10, max_overflow=20)
        _engine = create_engine(s.database_url, **kwargs)
        if s.is_sqlite:
            @event.listens_for(_engine, "connect")
            def _pragmas(dbapi_conn, _):  # pragma: no cover - trivial
                cur = dbapi_conn.cursor()
                cur.execute("PRAGMA journal_mode=WAL")
                cur.execute("PRAGMA foreign_keys=ON")
                cur.close()
        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    return _engine


def reset_engine() -> None:
    """Used by tests after changing settings."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine, _SessionLocal = None, None


def SessionLocal() -> Session:
    get_engine()
    assert _SessionLocal is not None
    return _SessionLocal()


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def create_all() -> None:
    """Dev/test convenience. Production uses `alembic upgrade head`."""
    from . import models  # noqa: F401 - register tables

    engine = get_engine()
    Base.metadata.create_all(engine)
    _add_missing_columns(engine)


def _add_missing_columns(engine) -> None:
    """Dev SQLite only: add columns introduced after the DB file was created (additive, never drops).
    Columns must be nullable or carry a server_default — the same rule Alembic migrations follow here."""
    if engine.dialect.name != "sqlite":
        return
    from sqlalchemy import UniqueConstraint, inspect, text

    insp = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in have:
                    continue
                default = f" DEFAULT {col.server_default.arg}" if col.server_default is not None else ""
                ddl = col.type.compile(dialect=engine.dialect)
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {ddl}{default}'))
                # SQLite cannot add a UNIQUE column: enforce single-column unique constraints with an index.
                for uc in table.constraints:
                    if isinstance(uc, UniqueConstraint) and [c.name for c in uc.columns] == [col.name]:
                        name = uc.name or f"uq_{table.name}_{col.name}"
                        conn.execute(text(f'CREATE UNIQUE INDEX IF NOT EXISTS "{name}" ON "{table.name}" ("{col.name}")'))
