"""Application configuration — loaded from environment variables."""

from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.domain.document.entity import DEFAULT_MAX_FILE_SIZE_BYTES

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

    # RLS layer-2 (SP-3, ADR-008). When enabled, request-path transactions drop to the
    # non-bypass RLS_APP_ROLE and set the app.clan_id GUC. Disabling is the code-free
    # rollback switch (RLS off → the application layer still fully enforces isolation).
    RLS_ENABLED: bool = True
    RLS_APP_ROLE: str = "familyroots_app"

    # Supabase / PostgreSQL
    DATABASE_URL: str = "postgresql+psycopg://postgres:password@localhost:5432/family_roots"
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_STORAGE_BUCKET: str = "family-roots-files"

    # Public avatar bucket (ADR-036). Deliberately a SECOND bucket: everything in
    # SUPABASE_STORAGE_BUCKET is private and read through short-lived presigned URLs,
    # while objects published here are world-readable forever by design. Keeping the
    # two apart is what stops "make avatars public" from making every document public.
    # The bucket itself is created by hand in the Supabase dashboard (public read,
    # see docs/architecture/storage.md); when it is missing the avatar write path
    # fails with a mapped 503 rather than storing a URL that never resolves.
    SUPABASE_AVATAR_BUCKET: str = "family-roots-avatars"

    # Cache-Control max-age (seconds) stamped on published avatar objects. The object
    # path is stable per person, so a replaced avatar keeps its URL and only becomes
    # visible to a cache after this window — short by default for that reason.
    AVATAR_CACHE_CONTROL_SECONDS: int = 300

    # Firebase FCM
    FIREBASE_CREDENTIALS_PATH: str = "./firebase-credentials.json"

    # Sentry
    SENTRY_DSN: str = ""

    # Metrics — opt-in RED metrics for a Prometheus scraper. Off by default because
    # nothing scrapes it yet; the token keeps route names and request volumes from
    # being readable by anyone who finds the path.
    METRICS_ENABLED: bool = False
    METRICS_TOKEN: str = ""

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:8080"]
    ALLOWED_HOSTS: list[str] = ["*"]

    # Rate limiting — only trust X-Forwarded-For when behind a trusted proxy/LB.
    # None means "not decided": fine in dev (resolves False), rejected in
    # production, where an accidental False behind a proxy collapses every client
    # into the proxy's one rate bucket and stamps audit rows with the proxy IP,
    # while an accidental True on a directly-exposed service lets clients spoof
    # their address. Production must choose explicitly.
    RATE_LIMIT_TRUST_FORWARDED_FOR: bool | None = None

    @property
    def trust_forwarded_for(self) -> bool:
        """Resolved XFF trust — the explicit value, or False when unset (dev)."""
        return bool(self.RATE_LIMIT_TRUST_FORWARDED_FOR)

    # Document upload — the platform-wide max upload size (MB), env-tunable without a
    # code change. Defaults to the document domain's built-in policy so there is a
    # single source for the number. (Per-clan overrides are a future clan_settings
    # feature; the dead clan_settings.max_upload_size_mb column is NOT wired yet.)
    MAX_UPLOAD_SIZE_MB: int = DEFAULT_MAX_FILE_SIZE_BYTES // (1024 * 1024)

    @property
    def max_upload_bytes(self) -> int:
        """The resolved upload limit in bytes (the application injects this)."""
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    # Scheduler — the platform's authoritative timezone. The anniversary cron fires
    # at NOTIFICATION_CRON_HOUR in this zone AND all of the job's date math is computed
    # against "today" in this zone, so there is a single clock (no container-local vs
    # DB-server-tz mismatch). Vietnamese genealogy platform → Asia/Ho_Chi_Minh.
    # DESIGN NOTE: this is a single global platform zone; a clan in another timezone
    # still gets notified on VN "today" at VN 07:00. Per-clan timezone is out of scope
    # for M4 — revisit if the platform serves clans across zones.
    SCHEDULER_TIMEZONE: str = "Asia/Ho_Chi_Minh"
    NOTIFICATION_CRON_HOUR: int = 7

    # Password reset — the web/mobile page the recovery email links to; empty →
    # Supabase falls back to the project's Site URL.
    PASSWORD_RESET_REDIRECT_URL: str = ""

    # Email verification — the web/mobile page the signup confirmation email links
    # to; empty → Supabase falls back to the project's Site URL.
    EMAIL_VERIFY_REDIRECT_URL: str = ""

    # Invitations
    INVITATION_TTL_DAYS: int = 7

    # Document retention (ADR-019): soft-deleted documents are recoverable for this
    # many days after deleted_at, after which the daily purge job removes the blob
    # and row permanently.
    DOCUMENT_RETENTION_DAYS: int = 30

    # DB connection pool (ADR-028/H5): env-tunable so pool sizing can be adjusted
    # without a code change. Defaults match the previous hardcoded values.
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

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

    @field_validator("SCHEDULER_TIMEZONE")
    @classmethod
    def _validate_timezone(cls, value: str) -> str:
        """Fail fast at config load with a clear message on a bad tz name, rather than
        an opaque ZoneInfoNotFoundError deep in scheduler module import."""
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"SCHEDULER_TIMEZONE '{value}' is not a valid IANA timezone") from exc
        return value

    @model_validator(mode="after")
    def _enforce_production_safety(self) -> Settings:
        if self.METRICS_ENABLED and not self.METRICS_TOKEN:
            raise ValueError("METRICS_TOKEN must be set when METRICS_ENABLED is true")
        if self.APP_ENV == "production":
            if self.APP_SECRET_KEY == "change-me-in-production":
                raise ValueError("APP_SECRET_KEY must be set to a real secret in production")
            if self.APP_DEBUG:
                raise ValueError("APP_DEBUG must be False in production")
            if self.ALLOWED_HOSTS == ["*"]:
                raise ValueError("ALLOWED_HOSTS must be set explicitly in production")
            # A localhost DSN in production almost certainly means DATABASE_URL was
            # never wired — fail fast rather than boot against a non-existent local DB.
            if "localhost" in self.DATABASE_URL or "127.0.0.1" in self.DATABASE_URL:
                raise ValueError(
                    "DATABASE_URL must point at the production database, not localhost"
                )
            # CORS must be real origins (not the localhost dev defaults, not wildcard —
            # "*" is also invalid with allow_credentials=True).
            if self.CORS_ORIGINS == ["*"] or any(
                "localhost" in origin for origin in self.CORS_ORIGINS
            ):
                raise ValueError("CORS_ORIGINS must be explicit production origins")
            # Auth cannot work without the Supabase project URL + keys; fail fast at
            # boot instead of 401/503-ing every request (a missing key previously
            # surfaced only as per-request failures that were hard to diagnose).
            if not self.SUPABASE_URL:
                raise ValueError("SUPABASE_URL must be set in production")
            if not self.SUPABASE_ANON_KEY:
                raise ValueError("SUPABASE_ANON_KEY must be set in production (sign-in)")
            if not self.SUPABASE_SERVICE_ROLE_KEY:
                raise ValueError(
                    "SUPABASE_SERVICE_ROLE_KEY must be set in production (register/storage)"
                )
            if self.RATE_LIMIT_TRUST_FORWARDED_FOR is None:
                raise ValueError(
                    "RATE_LIMIT_TRUST_FORWARDED_FOR must be set explicitly in production: "
                    "true behind a trusted proxy/LB (Render), false when directly exposed"
                )
        return self


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()


settings = get_settings()
