"""Application configuration — loaded from environment variables."""

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    DATABASE_URL: str = "postgresql+asyncpg://postgres:password@localhost:5432/family_roots"
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

    # Scheduler
    NOTIFICATION_CRON_HOUR: int = 7
    NOTIFICATION_DAYS_BEFORE: int = 7

    # Invitations
    INVITATION_TTL_DAYS: int = 7

    @model_validator(mode="after")
    def _enforce_production_safety(self) -> Settings:
        if self.APP_ENV == "production":
            if self.APP_SECRET_KEY == "change-me-in-production":
                raise ValueError("APP_SECRET_KEY must be set to a real secret in production")
            if self.APP_DEBUG:
                raise ValueError("APP_DEBUG must be False in production")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()


settings = get_settings()
