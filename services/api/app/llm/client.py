"""Thin, accountable wrapper around the Anthropic SDK.

* Every call is logged to `llm_call` with token usage and USD cost (guide §9.4 #9).
* A daily budget guard stops spend before it exceeds DAILY_LLM_BUDGET_USD.
* Refusals and validation failures raise `LLMUnavailable`; callers fall back (teacher-confirm queue,
  template cards) so the product keeps working with no API key or during an outage.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TypeVar

from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import LLMCall

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

# USD per million tokens (input, output, cache_read). Cache writes (5-min TTL) bill at 1.25x input.
PRICES: dict[str, tuple[float, float, float]] = {
    "claude-opus-5-5": (4.00, 20.00, 0.20),
    "claude-sonnet-5-5": (2.00, 10.00, 0.20),
    "claude-haiku-5-5": (0.10, 0.50, 0.01),
}


class LLMUnavailable(RuntimeError):
    pass


def cost_usd(model: str, inp: int, out: int, cache_read: int = 0, cache_write: int = 0, batch: bool = False) -> float:
    pi, po, pc = PRICES.get(model, (4.0, 20.0, 0.4))
    c = (inp * pi + out * po + cache_read * pc + cache_write * pi * 1.25) / 1e6
    return c * (0.5 if batch else 1.0)


def spent_today(db: Session) -> float:
    since = datetime.now(UTC) - timedelta(days=1)
    return float(db.scalar(select(func.coalesce(func.sum(LLMCall.cost_usd), 0.0)).where(LLMCall.created_at >= since)))


_client = None


def _sdk():
    global _client
    if _client is None:
        import anthropic

        s = get_settings()
        _client = anthropic.Anthropic(api_key=s.anthropic_api_key) if s.anthropic_api_key else anthropic.Anthropic()
    return _client


def parse(
    db: Session,
    *,
    purpose: str,
    model: str,
    system: str,
    content: list[dict] | str,
    output_format: type[T],
    max_tokens: int = 4000,
    effort: str | None = None,
    ref: str | None = None,
) -> T:
    """Structured-output call with a cached system prompt. Raises LLMUnavailable on any failure."""
    s = get_settings()
    if not s.llm_live:
        raise LLMUnavailable("LLM offline mode")
    if spent_today(db) >= s.daily_llm_budget_usd:
        raise LLMUnavailable("daily LLM budget reached")
    import anthropic

    kwargs: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": content}],
        "output_format": output_format,
    }
    if effort:
        kwargs["output_config"] = {"effort": effort}
    rec = LLMCall(purpose=purpose, model=model, ref=ref)
    try:
        resp = _sdk().messages.parse(**kwargs)
    except (anthropic.AnthropicError, ValidationError, ValueError, TypeError) as e:
        # API/network/auth errors, a missing key in live mode, and outputs that fail schema validation
        # (out-of-range values, JSON truncated at max_tokens, refusal text) all degrade to the fallback path.
        rec.ok, rec.error = False, f"{type(e).__name__}: {e}"[:2000]
        db.add(rec)
        db.commit()
        log.warning("LLM %s call failed, using fallback: %s", purpose, rec.error[:200])
        raise LLMUnavailable(str(e)) from e
    u = resp.usage
    rec.input_tokens = u.input_tokens or 0
    rec.output_tokens = u.output_tokens or 0
    rec.cache_read_tokens = getattr(u, "cache_read_input_tokens", 0) or 0
    rec.cache_write_tokens = getattr(u, "cache_creation_input_tokens", 0) or 0
    rec.cost_usd = cost_usd(model, rec.input_tokens, rec.output_tokens, rec.cache_read_tokens, rec.cache_write_tokens)
    if resp.stop_reason in ("refusal", "max_tokens") or resp.parsed_output is None:
        rec.ok, rec.error = False, f"stop_reason={resp.stop_reason}"
        db.add(rec)
        db.commit()
        raise LLMUnavailable(rec.error)
    db.add(rec)
    db.commit()
    return resp.parsed_output
