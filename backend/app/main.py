"""FamilyRoots FastAPI application factory."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import (
    AppError,
    app_exception_handler,
    domain_exception_handler,
    unhandled_exception_handler,
)
from app.core.logging import configure_logging
from app.domain.shared.exceptions import DomainError
from app.middleware.language_middleware import LanguageMiddleware
from app.middleware.sentry_middleware import SentryMiddleware
from app.services.notification import init_firebase
from app.services.scheduler import start_scheduler, stop_scheduler
from app.services.translator import load_translations

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan — startup and shutdown logic."""
    configure_logging()

    # Initialize Sentry
    if settings.SENTRY_DSN:
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.APP_ENV,
            traces_sample_rate=0.1 if settings.APP_ENV == "production" else 1.0,
        )

    # Load i18n translation files
    load_translations()

    # Initialize Firebase for push notifications
    init_firebase()

    # Start APScheduler
    start_scheduler()

    yield

    # Shutdown APScheduler
    stop_scheduler()


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

    # Register custom exception handlers
    application.add_exception_handler(AppError, app_exception_handler)
    application.add_exception_handler(DomainError, domain_exception_handler)
    application.add_exception_handler(Exception, unhandled_exception_handler)

    # CORS middleware
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # TrustedHostMiddleware — rejects requests with unexpected Host headers
    application.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.ALLOWED_HOSTS)

    # Language middleware — extract Accept-Language and set locale context
    application.add_middleware(LanguageMiddleware)

    # Sentry middleware
    if settings.SENTRY_DSN:
        application.add_middleware(SentryMiddleware)

    # Rate limiting on auth endpoints (20 req/min per IP)
    from app.core.rate_limit import RateLimitMiddleware

    application.add_middleware(
        RateLimitMiddleware,
        path_prefix="/api/v1/auth",
        max_requests=20,
        window_seconds=60,
        trust_forwarded_for=settings.RATE_LIMIT_TRUST_FORWARDED_FOR,
    )

    # NOTE: No tenant middleware — clan isolation is enforced in the
    # application/repository layer (every clan-scoped read takes clan_id).
    # Users select their active clan via the X-Current-Clan-Id header.
    # DB-level RLS is a planned defense-in-depth addition (SP-3C), not yet active.

    # Include API v1 routes
    application.include_router(api_v1_router, prefix="/api/v1")

    # Health check with DB connectivity probe
    @application.get("/health", tags=["health"], response_model=None)
    async def health(db: AsyncSession = Depends(get_db)) -> dict[str, str] | JSONResponse:
        try:
            await db.execute(text("SELECT 1"))
            return {"status": "ok", "database": "connected"}
        except Exception:
            return JSONResponse(
                status_code=503,
                content={"status": "degraded", "database": "unreachable"},
            )

    return application


app = create_app()
