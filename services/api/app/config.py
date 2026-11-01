"""Runtime configuration (12-factor: everything from environment / .env)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", str(REPO_ROOT / ".env")),
                                      extra="ignore", populate_by_name=True)

    env: Literal["dev", "test", "prod"] = Field("dev", alias="APP_ENV")
    database_url: str = Field(f"sqlite:///{(REPO_ROOT / 'data' / 'dhwani.db').as_posix()}", alias="DATABASE_URL")
    jwt_secret: str = Field("dev-only-change-me-please-32-bytes-min", alias="JWT_SECRET")
    jwt_ttl_hours: int = Field(24 * 30, alias="JWT_TTL_HOURS")
    phone_pepper: str = Field("dev-pepper", alias="PHONE_PEPPER")
    cors_origins: str = Field("*", alias="CORS_ORIGINS")
    # Dev/demo only: POST /v1/auth/open issues a session for any role without phone + PIN. Refused in prod.
    auth_disabled: bool = Field(False, alias="AUTH_DISABLED")
    # "Create account" as admin activates at once (no approval); other admins above are notified.
    # Set to false to require approval for admin sign-ups as well.
    admin_self_signup: bool = Field(True, alias="ADMIN_SELF_SIGNUP")

    content_pack_dir: str = Field(str(REPO_ROOT / "content" / "packs" / "hi-IN"), alias="CONTENT_PACK_DIR")

    blob_backend: Literal["local", "s3"] = Field("local", alias="BLOB_BACKEND")
    blob_dir: str = Field(str(REPO_ROOT / "data" / "blobs"), alias="BLOB_DIR")
    s3_bucket: str | None = Field(None, alias="S3_BUCKET")
    s3_endpoint: str | None = Field(None, alias="S3_ENDPOINT")
    audio_retention_hours: int = Field(0, alias="AUDIO_RETENTION_HOURS")  # 0 = delete right after scoring
    # Slate crops (answer region only) are kept for the teacher's confirm queue, then purged.
    slate_crop_retention_days: int = Field(30, alias="SLATE_CROP_RETENTION_DAYS")

    speech_backend: Literal["simulated", "wav2vec2"] = Field("simulated", alias="SPEECH_BACKEND")
    speech_model_id: str = Field("Harveenchadha/vakyansh-wav2vec2-hindi-him-4200", alias="SPEECH_MODEL_ID")
    speech_device: str = Field("cpu", alias="SPEECH_DEVICE")
    allow_simulated_audio: bool = Field(True, alias="ALLOW_SIMULATED_AUDIO")  # dev/demo only; False in prod

    llm_mode: Literal["auto", "live", "offline"] = Field("auto", alias="LLM_MODE")
    anthropic_api_key: str | None = Field(None, alias="ANTHROPIC_API_KEY")
    model_slate: str = Field("claude-sonnet-5-5", alias="MODEL_SLATE")
    model_card: str = Field("claude-opus-5-5", alias="MODEL_CARD")
    model_explain: str = Field("claude-opus-5-5", alias="MODEL_EXPLAIN")
    model_hypothesis: str = Field("claude-opus-5-5", alias="MODEL_HYPOTHESIS")
    daily_llm_budget_usd: float = Field(5.0, alias="DAILY_LLM_BUDGET_USD")

    min_cell_size: int = Field(5, alias="MIN_CELL_SIZE")
    default_kiosk_budget_min: float = Field(12.0, alias="DEFAULT_KIOSK_BUDGET_MIN")
    worker_poll_seconds: float = Field(1.0, alias="WORKER_POLL_SECONDS")
    log_level: str = Field("INFO", alias="LOG_LEVEL")

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
