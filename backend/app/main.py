"""FamilyRoots FastAPI application factory."""

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.database import AsyncSessionLocal, get_db
from app.core.exceptions import (
    AppError,
    app_exception_handler,
    domain_exception_handler,
    http_exception_handler,
    identity_unavailable_handler,
    integrity_error_handler,
    storage_not_found_handler,
    storage_unavailable_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.core.logging import configure_logging
from app.core.readiness import MIGRATIONS_CURRENT, migration_status
from app.domain.auth.identity_provider import IdentityUnavailableError
from app.domain.document.repository import StorageNotFoundError, StorageUnavailableError
from app.domain.shared.exceptions import DomainError
from app.middleware.language_middleware import LanguageMiddleware
from app.middleware.sentry_middleware import SentryMiddleware
from app.services.notification import init_firebase
from app.services.scheduler import start_scheduler, stop_scheduler
from app.services.translator import load_translations

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan — startup and shutdown logic.

    Each optional integration (Sentry, i18n, Firebase, scheduler) is isolated:
    a failure in one is logged but does not abort boot or skip the others, and
    shutdown runs in a finally block so teardown can't be skipped. The API can
    serve requests even if a non-critical side-channel (push, scheduling) is down.
    """
    configure_logging()

    def _safe(label: str, fn: Callable[[], object]) -> None:
        try:
            fn()
        except Exception:
            logger.exception("Startup step failed (continuing): %s", label)

    if settings.SENTRY_DSN:
        _safe(
            "sentry",
            lambda: sentry_sdk.init(
                dsn=settings.SENTRY_DSN,
                environment=settings.APP_ENV,
                traces_sample_rate=0.1 if settings.APP_ENV == "production" else 1.0,
            ),
        )
    _safe("translations", load_translations)
    _safe("firebase", init_firebase)
    _safe("scheduler", start_scheduler)

    # Auth config sanity (production fails fast in Settings; in dev we warn loudly
    # so a missing key shows up at boot, not as per-request 401/503s).
    if not settings.SUPABASE_URL:
        logger.warning("SUPABASE_URL is not set — JWT verification and auth will fail")
    elif not settings.SUPABASE_ANON_KEY or not settings.SUPABASE_SERVICE_ROLE_KEY:
        logger.warning(
            "Supabase keys incomplete (anon=%s, service_role=%s) — "
            "sign-in and/or register/storage will fail",
            "set" if settings.SUPABASE_ANON_KEY else "MISSING",
            "set" if settings.SUPABASE_SERVICE_ROLE_KEY else "MISSING",
        )

    # DB readiness: an unmigrated runtime DB means "relation does not exist" 500s
    # on nearly every endpoint. In production, refuse to boot (the deploy fails and
    # the previous version keeps serving); in dev, warn loudly and continue.
    try:
        async with AsyncSessionLocal() as session:
            status = await migration_status(session)
    except Exception as exc:
        status = f"db-unreachable ({type(exc).__name__})"
    if status != MIGRATIONS_CURRENT:
        message = (
            f"Database is not ready (migrations: {status}). "
            "Run `alembic upgrade head` against this database."
        )
        if settings.APP_ENV == "production":
            raise RuntimeError(message)
        logger.error(message)

    try:
        yield
    finally:
        _safe("scheduler-stop", stop_scheduler)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    application = FastAPI(
        title="FamilyRoots API",
        description="REST API for the FamilyRoots genealogy platform",
        version="0.1.0",
        docs_url="/docs" if settings.APP_DEBUG else None,
        redoc_url="/redoc" if settings.APP_DEBUG else None,
        lifespan=lifespan,
    )

    # Register custom exception handlers. AppError is matched before the base
    # StarletteHTTPException (more specific), so coded errors keep their envelope
    # while bare HTTPExceptions and 422 validation errors are normalized too.
    application.add_exception_handler(AppError, app_exception_handler)
    application.add_exception_handler(DomainError, domain_exception_handler)
    application.add_exception_handler(IdentityUnavailableError, identity_unavailable_handler)
    application.add_exception_handler(StorageUnavailableError, storage_unavailable_handler)
    application.add_exception_handler(StorageNotFoundError, storage_not_found_handler)
    application.add_exception_handler(RequestValidationError, validation_exception_handler)
    application.add_exception_handler(StarletteHTTPException, http_exception_handler)
    # More specific than the catch-all Exception handler: a DB constraint violation
    # is a 409, not a 500 (Starlette matches by the exception's MRO, so IntegrityError
    # wins over Exception).
    application.add_exception_handler(IntegrityError, integrity_error_handler)
    application.add_exception_handler(Exception, unhandled_exception_handler)

    # Middleware order matters. Starlette wraps the LAST-added middleware OUTERMOST,
    # so we add in reverse of the desired execution order. Desired (outermost →
    # innermost): TrustedHost → CORS → Language → Sentry → RateLimit. This means:
    #   - TrustedHost rejects a bad Host header before anything else runs;
    #   - CORS wraps the rate limiter, so even a 429 carries CORS headers;
    #   - Language sets the locale before RateLimit builds its (localized) 429 envelope.
    from app.core.rate_limit import RateLimitMiddleware

    # innermost
    application.add_middleware(
        RateLimitMiddleware,
        path_prefix="/api/v1/auth",
        max_requests=20,
        window_seconds=60,
        trust_forwarded_for=settings.RATE_LIMIT_TRUST_FORWARDED_FOR,
    )
    if settings.SENTRY_DSN:
        application.add_middleware(SentryMiddleware)
    application.add_middleware(LanguageMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # outermost
    application.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.ALLOWED_HOSTS)

    # NOTE: No tenant middleware — clan isolation is enforced in the
    # application/repository layer (every clan-scoped read takes clan_id).
    # Users select their active clan via the X-Current-Clan-Id header.
    # DB-level RLS is a planned defense-in-depth addition (SP-3C), not yet active.

    # Include API v1 routes
    application.include_router(api_v1_router, prefix="/api/v1")

    # Health check with DB connectivity probe
    @application.get("/health", tags=["health"], response_model=None)
    async def health(db: AsyncSession = Depends(get_db)) -> dict[str, str] | JSONResponse:
        """Liveness + readiness. Deliberately does NOT call the auth provider:
        a Supabase outage must not mark the pod unhealthy (restart loops) — auth
        paths already surface 503 per-request via IdentityUnavailableError."""
        try:
            await db.execute(text("SELECT 1"))
        except Exception:
            return JSONResponse(
                status_code=503,
                content={"status": "degraded", "database": "unreachable"},
            )
        migrations = await migration_status(db)
        if migrations != MIGRATIONS_CURRENT:
            # Schema missing/behind → most endpoints would 500; report degraded so
            # deploys and load balancers get the true signal.
            return JSONResponse(
                status_code=503,
                content={
                    "status": "degraded",
                    "database": "connected",
                    "migrations": migrations,
                },
            )
        return {"status": "ok", "database": "connected", "migrations": migrations}

    return application


app = create_app()
