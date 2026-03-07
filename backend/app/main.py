"""FamilyRoots FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.middleware.language_middleware import LanguageMiddleware
from app.services.translator import load_translations


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan — startup and shutdown logic."""

    # Initialize Sentry
    if settings.SENTRY_DSN:
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.APP_ENV,
            traces_sample_rate=0.1 if settings.APP_ENV == "production" else 1.0,
        )

    # Load i18n translation files
    load_translations()

    # TODO: implement in Prompt 2 — initialize database engine
    # TODO: implement in Prompt 2 — start APScheduler

    yield

    # TODO: implement in Prompt 2 — shutdown database engine
    # TODO: implement in Prompt 2 — shutdown APScheduler


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

    # CORS middleware
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.APP_DEBUG else [],  # TODO: configure for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Language middleware — extract Accept-Language and set locale context
    application.add_middleware(LanguageMiddleware)

    # NOTE: No tenant middleware — clan_id isolation is handled by
    # Supabase RLS at the DB level + get_current_clan_id() dependency.
    # Users select their active clan via X-Current-Clan-Id header.

    # TODO: implement in Prompt 2 — add Sentry middleware

    # Include API v1 routes
    application.include_router(api_v1_router, prefix="/api/v1")

    return application


app = create_app()
