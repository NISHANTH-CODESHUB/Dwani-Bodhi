"""Runtime configuration (12-factor: everything from environment / .env)."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]
# Vercel sets VERCEL=1 in every function: serverless-appropriate defaults (each can still be overridden).
ON_VERCEL = bool(os.environ.get("VERCEL"))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", str(REPO_ROOT / ".env")),
                                      extra="ignore", populate_by_name=True)

    env: Literal["dev", "test", "prod"] = Field("prod" if ON_VERCEL else "dev", alias="APP_ENV")
    database_url: str = Field(f"sqlite:///{(REPO_ROOT / 'data' / 'dhwani.db').as_posix()}", alias="DATABASE_URL")
    jwt_secret: str = Field("dev-only-change-me-please-32-bytes-min", alias="JWT_SECRET")
    jwt_ttl_hours: int = Field(24 * 30, alias="JWT_TTL_HOURS")
    phone_pepper: str = Field("dev-pepper", alias="PHONE_PEPPER")
    cors_origins: str = Field("*", alias="CORS_ORIGINS")
    # Use x-real-ip / x-forwarded-for for per-client throttling. Only behind a proxy that sets them (Vercel,
    # Caddy); otherwise a client could forge them.
    trust_proxy_headers: bool = Field(ON_VERCEL, alias="TRUST_PROXY_HEADERS")
    # Dev/demo only: POST /v1/auth/open signs in as the first teacher without phone + PIN. Refused in prod.
    auth_disabled: bool = Field(False, alias="AUTH_DISABLED")
    # Apply Alembic migrations on start-up (serverless deploys have no separate release step).
    auto_migrate: bool = Field(ON_VERCEL, alias="AUTO_MIGRATE")
    # Serverless (Vercel): one short-lived process per request, so no connection pool is kept open.
    db_null_pool: bool = Field(ON_VERCEL, alias="DB_NULL_POOL")

    content_pack_dir: str = Field(str(REPO_ROOT / "content" / "packs" / "hi-IN"), alias="CONTENT_PACK_DIR")

    # local disk (dev / VM) · s3 (any S3-compatible store) · db (bytes in the database; serverless hosts)
    blob_backend: Literal["local", "s3", "db"] = Field("db" if ON_VERCEL else "local", alias="BLOB_BACKEND")
    blob_dir: str = Field(str(REPO_ROOT / "data" / "blobs"), alias="BLOB_DIR")
    s3_bucket: str | None = Field(None, alias="S3_BUCKET")
    s3_endpoint: str | None = Field(None, alias="S3_ENDPOINT")
    audio_retention_hours: int = Field(0, alias="AUDIO_RETENTION_HOURS")  # 0 = delete right after scoring
    # Slate crops (answer region only) are kept for the teacher's confirm queue, then purged.
    slate_crop_retention_days: int = Field(30, alias="SLATE_CROP_RETENTION_DAYS")

    # wav2vec2: automatic ECCL scoring (needs the `speech` extra) · review: every recording goes to the
    # teacher's listen-and-confirm queue (hosts that cannot run the model, e.g. Vercel) · simulated: tests/demo
    speech_backend: Literal["simulated", "wav2vec2", "review"] = Field("review" if ON_VERCEL else "simulated",
                                                                     alias="SPEECH_BACKEND")
    speech_model_id: str = Field("Harveenchadha/vakyansh-wav2vec2-hindi-him-4200", alias="SPEECH_MODEL_ID")
    speech_device: str = Field("cpu", alias="SPEECH_DEVICE")
    allow_simulated_audio: bool = Field(not ON_VERCEL, alias="ALLOW_SIMULATED_AUDIO")  # dev/demo only; False in prod

    llm_mode: Literal["auto", "live", "offline"] = Field("auto", alias="LLM_MODE")
    anthropic_api_key: str | None = Field(None, alias="ANTHROPIC_API_KEY")
    model_slate: str = Field("claude-sonnet-5-5", alias="MODEL_SLATE")
    model_card: str = Field("claude-opus-5-5", alias="MODEL_CARD")
    model_explain: str = Field("claude-opus-5-5", alias="MODEL_EXPLAIN")
    model_hypothesis: str = Field("claude-opus-5-5", alias="MODEL_HYPOTHESIS")
    daily_llm_budget_usd: float = Field(5.0, alias="DAILY_LLM_BUDGET_USD")
    llm_timeout_s: float = Field(40.0 if ON_VERCEL else 120.0, alias="LLM_TIMEOUT_S")

    min_cell_size: int = Field(5, alias="MIN_CELL_SIZE")
    default_kiosk_budget_min: float = Field(12.0, alias="DEFAULT_KIOSK_BUDGET_MIN")
    worker_poll_seconds: float = Field(1.0, alias="WORKER_POLL_SECONDS")
    # No long-running worker (serverless): run queued jobs inside API requests, within a time budget.
    inline_jobs: bool = Field(ON_VERCEL, alias="INLINE_JOBS")
    # Queues the API may run inline. Drop "speech" when a separate speech worker drains that queue.
    inline_queues: str = Field("speech,vision,learner,llm", alias="INLINE_QUEUES")
    inline_budget_s: float = Field(20.0, alias="INLINE_BUDGET_S")
    # Shared secret for the scheduled maintenance endpoint (Vercel Cron sends it as a Bearer token).
    cron_secret: str | None = Field(None, alias="CRON_SECRET")
    log_level: str = Field("INFO", alias="LOG_LEVEL")

    @field_validator("database_url")
    @classmethod
    def _sqlalchemy_url(cls, v: str) -> str:
        """Hosted Postgres providers (Neon, Supabase, Vercel) hand out postgres:// URLs; use psycopg 3."""
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix):]
        return v

    @property
    def inline_queue_list(self) -> list[str]:
        return [q.strip() for q in self.inline_queues.split(",") if q.strip()]

    @property
    def llm_live(self) -> bool:
        if self.llm_mode == "offline":
            return False
        if self.llm_mode == "live":
            return True
        return bool(self.anthropic_api_key)

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
