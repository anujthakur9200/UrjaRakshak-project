"""
Configuration — UrjaRakshak
============================
Reads from environment variables / .env file.

Required in production:
  DATABASE_URL  — PostgreSQL or Supabase connection string
  SECRET_KEY    — 32+ character JWT signing secret

Safe defaults are provided for local development so the server
starts without a .env file (uses SQLite-compatible warning message
and a dev-only secret).
"""

import json
import sys
import logging
from functools import lru_cache
from typing import List, Optional

from pydantic import Field, field_validator, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

_DEV_SECRET = "urjarakshak-dev-secret-key-NOT-for-production-32ch"
_DEV_DB     = "postgresql+asyncpg://postgres:postgres@localhost:5432/urjarakshak"


class Settings(BaseSettings):
    """All application settings. model_config must be first in pydantic-settings v2."""

    # ── pydantic-settings v2 config (MUST be first) ─────────────────────
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",          # ignore unknown env vars silently
    )

    # ── Application ──────────────────────────────────────────────────────
    APP_NAME:    str = "UrjaRakshak"
    VERSION:     str = "2.3.0"
    ENVIRONMENT: str = Field(default="development")
    DEBUG:       bool = Field(default=False)

    # ── Server ───────────────────────────────────────────────────────────
    HOST: str = Field(default="0.0.0.0")
    PORT: int = Field(default=8000)

    # ── Database ─────────────────────────────────────────────────────────
    # Defaults to local postgres so server starts without a .env file in dev
    DATABASE_URL: str = Field(default=_DEV_DB)

    # ── Security ─────────────────────────────────────────────────────────
    # Dev default so server starts; production MUST override via env var
    SECRET_KEY: str = Field(default=_DEV_SECRET)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60)   # 1 hour

    # ── CORS ─────────────────────────────────────────────────────────────
    ALLOWED_ORIGINS: List[str] = Field(
        default=[
            "https://urjarakshak.vercel.app",
            "http://localhost:3000",
            "http://localhost:3001",
        ]
    )
    CORS_ALLOW_ORIGIN_REGEX: Optional[str] = Field(default=None)

    # ── AI Services ──────────────────────────────────────────────────────
    ANTHROPIC_API_KEY: Optional[str] = Field(default=None)
    OPENAI_API_KEY:    Optional[str] = Field(default=None)
    GROQ_API_KEY:      Optional[str] = Field(default=None)
    HUGGINGFACE_TOKEN: Optional[str] = Field(default=None)
    AI_MODEL: str = Field(default="claude-haiku-4-5-20251001")

    # ── Ethics & Privacy ─────────────────────────────────────────────────
    ENABLE_STRICT_ETHICS:  bool = Field(default=True)
    ENABLE_AUDIT_LOGGING:  bool = Field(default=True)
    DATA_RETENTION_DAYS:   int  = Field(default=90)

    # ── Physics Engine ───────────────────────────────────────────────────
    PHYSICS_MIN_CONFIDENCE:          float = Field(default=0.5)
    PHYSICS_TEMPERATURE_CELSIUS:     float = Field(default=25.0)
    MEASUREMENT_UNCERTAINTY_PERCENT: float = Field(default=1.0)

    # ── Features ─────────────────────────────────────────────────────────
    ENABLE_WEBSOCKETS:       bool = Field(default=True)
    ENABLE_AI_ANALYSIS:      bool = Field(default=False)
    ENABLE_REAL_TIME_UPDATES:bool = Field(default=True)

    # ── Multi-Tenancy ─────────────────────────────────────────────────────
    ENABLE_MULTI_TENANT: bool = Field(default=True)
    DEFAULT_ORG_PLAN:    str  = Field(default="free")

    # ── Streaming ─────────────────────────────────────────────────────────
    MAX_SSE_CONNECTIONS_PER_SUBSTATION: int = Field(default=50)
    STREAMING_HEARTBEAT_SECONDS:        int = Field(default=30)

    # ── Drift Detection ───────────────────────────────────────────────────
    ENABLE_AUTO_DRIFT_CHECK:      bool  = Field(default=True)
    DRIFT_CHECK_INTERVAL_HOURS:   int   = Field(default=24)
    DRIFT_PSI_RETRAIN_THRESHOLD:  float = Field(default=0.25)

    # ── Transformer Aging ─────────────────────────────────────────────────
    ENABLE_AGING_ANALYSIS:         bool  = Field(default=True)
    DEFAULT_AMBIENT_TEMP_C:        float = Field(default=30.0)
    DEFAULT_TRANSFORMER_LIFE_YEARS:float = Field(default=30.0)

    # ── External / Monitoring (all optional) ─────────────────────────────
    REDIS_URL:           Optional[str] = Field(default=None)
    CLOUDINARY_URL:      Optional[str] = Field(default=None)
    SENDGRID_API_KEY:    Optional[str] = Field(default=None)
    SENTRY_DSN:          Optional[str] = Field(default=None)
    BETTER_STACK_TOKEN:  Optional[str] = Field(default=None)

    # ── Validators ───────────────────────────────────────────────────────

    @field_validator("ENVIRONMENT")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        allowed = {"development", "staging", "production", "test"}
        if v not in allowed:
            raise ValueError(f"ENVIRONMENT must be one of {sorted(allowed)}")
        return v

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        return v

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        ok_prefixes = (
            "postgresql://",
            "postgresql+asyncpg://",
            "postgres://",
            # Allow SQLite for testing and local development
            "sqlite://",
            "sqlite+aiosqlite://",
        )
        if not any(v.startswith(p) for p in ok_prefixes):
            raise ValueError(
                "DATABASE_URL must be a PostgreSQL connection string "
                "(postgresql:// or postgresql+asyncpg://) or SQLite for testing "
                "(sqlite:// or sqlite+aiosqlite://)"
            )
        return v

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_allowed_origins(cls, v) -> List[str]:
        """Accept JSON array or comma-separated string from env var."""
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("["):
                return json.loads(v)
            return [o.strip() for o in v.split(",") if o.strip()]
        return v  # already a list (from default_factory or pydantic parsing)

    # ── Computed properties ───────────────────────────────────────────────

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == "development"

    @property
    def has_ai_configured(self) -> bool:
        return bool(self.ANTHROPIC_API_KEY or self.OPENAI_API_KEY or self.HUGGINGFACE_TOKEN)

    @property
    def using_dev_defaults(self) -> bool:
        return self.SECRET_KEY == _DEV_SECRET or self.DATABASE_URL == _DEV_DB


@lru_cache()
def get_settings() -> Settings:
    """Return cached Settings. Fails fast on misconfiguration."""
    try:
        s = Settings()
        if s.using_dev_defaults and s.is_production:
            print("❌ FATAL: Dev defaults detected in production!", file=sys.stderr)
            sys.exit(1)
        if s.using_dev_defaults:
            logger.warning(
                "⚠️  Running with dev defaults — set DATABASE_URL and SECRET_KEY in .env"
            )
        return s
    except ValidationError as e:
        print("❌ Configuration error:", file=sys.stderr)
        for err in e.errors():
            print(f"  {'.'.join(str(x) for x in err['loc'])}: {err['msg']}", file=sys.stderr)
        sys.exit(1)


settings = get_settings()


def validate_production_settings() -> None:
    """Extra checks for production deployment."""
    if not settings.is_production:
        return
    errors = []
    if settings.DEBUG:
        errors.append("DEBUG must be False in production")
    if settings.SECRET_KEY == _DEV_SECRET:
        errors.append("SECRET_KEY must be changed from the dev default")
    if settings.DATABASE_URL == _DEV_DB:
        errors.append("DATABASE_URL must be set to a real database")
    if "localhost" in " ".join(settings.ALLOWED_ORIGINS):
        errors.append("ALLOWED_ORIGINS should not contain localhost in production")
    if errors:
        for e in errors:
            print(f"❌ Production check failed: {e}", file=sys.stderr)
        sys.exit(1)


if settings.is_production:
    validate_production_settings()


__all__ = ["settings", "Settings", "get_settings"]
