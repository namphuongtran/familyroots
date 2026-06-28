"""Application configuration — loaded from environment variables."""

from functools import lru_cache

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_CANONICAL_DB_DRIVER = "postgresql+psycopg"


class Settings(BaseSettings):
    """Application settings loaded from .env file and environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # App
    APP_ENV: str = "development"
    APP_SECRET_KEY: str = "change-me-in-production"
    APP_DEBUG: bool = False
    APP_PORT: int = 8000

    # Supabase / PostgreSQL
    DATABASE_URL: str = "postgresql+psycopg://postgres:password@localhost:5432/family_roots"
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_STORAGE_BUCKET: str = "family-roots-files"

    # Firebase FCM
    FIREBASE_CREDENTIALS_PATH: str = "./firebase-credentials.json"

    # Sentry
    SENTRY_DSN: str = ""

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:8080"]
    ALLOWED_HOSTS: list[str] = ["*"]

    # Rate limiting — only trust X-Forwarded-For when behind a trusted proxy/LB.
    RATE_LIMIT_TRUST_FORWARDED_FOR: bool = False

    # Scheduler
    NOTIFICATION_CRON_HOUR: int = 7
    NOTIFICATION_DAYS_BEFORE: int = 7

    # Invitations
    INVITATION_TTL_DAYS: int = 7

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        """Rewrite any supported URL form to the canonical psycopg v3 dialect.

        Render injects bare ``postgresql://`` (or historically ``postgres://``)
        via ``fromDatabase.connectionString``; older developer ``.env`` files may
        still carry ``+asyncpg`` or ``+psycopg2``. Normalizing here means the app
        engine (async) and Alembic (sync) always see one psycopg v3 URL.
        """
        if not isinstance(value, str) or "://" not in value:
            return value
        scheme, rest = value.split("://", 1)
        base = scheme.split("+", 1)[0]
        if base == "postgres":
            base = "postgresql"
        if base != "postgresql":
            return value  # leave non-postgres URLs untouched
        return f"{_CANONICAL_DB_DRIVER}://{rest}"

    @model_validator(mode="after")
    def _enforce_production_safety(self) -> Settings:
        if self.APP_ENV == "production":
            if self.APP_SECRET_KEY == "change-me-in-production":
                raise ValueError("APP_SECRET_KEY must be set to a real secret in production")
            if self.APP_DEBUG:
                raise ValueError("APP_DEBUG must be False in production")
            if self.ALLOWED_HOSTS == ["*"]:
                raise ValueError("ALLOWED_HOSTS must be set explicitly in production")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()


settings = get_settings()
