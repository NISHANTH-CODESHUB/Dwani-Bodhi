"""Alembic must build the exact schema in models.py from an empty database (production never uses create_all)."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1]


def _alembic(db_url: str, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "DATABASE_URL": db_url}
    return subprocess.run([sys.executable, "-m", "alembic", *args], check=False, cwd=API_DIR, env=env,
                          capture_output=True, text=True, timeout=180)


def test_migrations_upgrade_downgrade_and_match_models():
    with tempfile.TemporaryDirectory() as d:
        url = f"sqlite:///{(Path(d) / 'm.db').as_posix()}"
        for args in (("upgrade", "head"), ("check",), ("downgrade", "base"), ("upgrade", "head")):
            r = _alembic(url, *args)
            assert r.returncode == 0, f"alembic {' '.join(args)} failed:\n{r.stdout}\n{r.stderr}"
