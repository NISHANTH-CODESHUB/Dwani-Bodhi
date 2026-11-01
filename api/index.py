"""Vercel serverless entry point: the FastAPI app from services/api.

vercel.json rewrites /v1/* and /health here as `/api/index?__vp=<original path>`. Vercel normally passes
the original URL through; if it ever arrives as /api/index, the `__vp` parameter restores it.
"""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api"))

from app.main import app as fastapi_app  # noqa: E402


async def app(scope, receive, send):
    if scope["type"] == "http":
        pairs = parse_qsl(scope.get("query_string", b"").decode(), keep_blank_values=True)
        original = next((v for k, v in pairs if k == "__vp"), None)
        if original is not None:
            rest = urlencode([(k, v) for k, v in pairs if k != "__vp"])
            path = scope["path"] if scope["path"].startswith(("/v1", "/health")) else original
            scope = {**scope, "path": path, "raw_path": path.encode(), "query_string": rest.encode()}
    await fastapi_app(scope, receive, send)
