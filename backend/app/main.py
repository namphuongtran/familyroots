"""FamilyRoots FastAPI application factory."""

import logging
import secrets
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.v1.router import api_v1_router
from app.core.config import metrics_token_weakness, settings
from app.core.database import AsyncRequestSessionLocal, AsyncSessionLocal, get_db
from app.core.exceptions import (
    AppError,
    app_exception_handler,
    database_unavailable_handler,
    domain_exception_handler,
    http_exception_handler,
    identity_email_not_verified_handler,
    identity_unavailable_handler,
    integrity_error_handler,
    storage_bucket_not_configured_handler,
    storage_not_found_handler,
    storage_unavailable_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.core.logging import configure_logging
from app.core.metrics_guard import MetricsFailureThrottle
from app.core.readiness import MIGRATIONS_CURRENT, migration_status
from app.domain.auth.identity_provider import (
    IdentityEmailNotVerifiedError,
    IdentityUnavailableError,
)
from app.domain.document.repository import (
    StorageBucketNotConfiguredError,
    StorageNotFoundError,
    StorageUnavailableError,
)
from app.domain.shared.exceptions import DomainError
from app.middleware.language_middleware import LanguageMiddleware
from app.middleware.request_meta_middleware import RequestMetaMiddleware
from app.middleware.sentry_middleware import SentryMiddleware
from app.middleware.trace_middleware import TraceContextMiddleware
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

    # RLS layer-2 readiness (SP-3, ADR-008): if RLS is enabled, prove the request path
    # genuinely drops to the non-bypass role. Otherwise RLS is silently inert (false
    # security), or the role/grant is misconfigured and every request would 500 on the
    # first SET LOCAL ROLE — catch it at boot, not per-request. Prod: refuse to boot;
    # dev: warn. RLS_ENABLED=false is the deliberate app-layer-only fallback.
    if settings.RLS_ENABLED:
        try:
            async with AsyncRequestSessionLocal() as session:
                who = await session.scalar(text("SELECT current_user"))
                bypass = await session.scalar(
                    text("SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user")
                )
            rls_ok = who == settings.RLS_APP_ROLE and bypass is False
            rls_detail = f"current_user={who}, bypassrls={bypass}"
        except Exception as exc:
            rls_ok = False
            rls_detail = f"{type(exc).__name__}: {exc}"
        if not rls_ok:
            rls_message = (
                f"RLS is enabled but the request role did not engage ({rls_detail}). Ensure "
                f"the app DB user can SET ROLE {settings.RLS_APP_ROLE} (a NOBYPASSRLS role) "
                "and migrations are applied, or set RLS_ENABLED=false for app-layer-only."
            )
            if settings.APP_ENV == "production":
                raise RuntimeError(rls_message)
            logger.error(rls_message)

    try:
        yield
    finally:
        _safe("scheduler-stop", stop_scheduler)
        try:
            from app.core.database import engine

            await engine.dispose()
        except Exception:
            logger.exception("teardown step failed: engine-dispose")


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
    application.add_exception_handler(
        IdentityEmailNotVerifiedError, identity_email_not_verified_handler
    )
    application.add_exception_handler(StorageUnavailableError, storage_unavailable_handler)
    application.add_exception_handler(StorageNotFoundError, storage_not_found_handler)
    application.add_exception_handler(
        StorageBucketNotConfiguredError, storage_bucket_not_configured_handler
    )
    application.add_exception_handler(RequestValidationError, validation_exception_handler)
    application.add_exception_handler(StarletteHTTPException, http_exception_handler)
    # More specific than the catch-all Exception handler: a DB constraint violation
    # is a 409, not a 500 (Starlette matches by the exception's MRO, so IntegrityError
    # wins over Exception).
    application.add_exception_handler(IntegrityError, integrity_error_handler)
    # A transient DB operational failure (dropped connection, pool exhaustion, restart)
    # is a 503, not a 500 (ADR-032). OperationalError is a sibling of IntegrityError
    # under DBAPIError, so this never shadows the 409 path; ProgrammingError/DataError
    # (our bugs) have no handler and stay 500 via the catch-all below.
    application.add_exception_handler(OperationalError, database_unavailable_handler)
    application.add_exception_handler(Exception, unhandled_exception_handler)

    # Middleware order matters. Starlette wraps the LAST-added middleware OUTERMOST,
    # so we add in reverse of the desired execution order.
    #
    #   Desired, outermost → innermost:
    #     Prometheus → TrustedHost → CORS → TraceContext
    #       → Language → RequestMeta → Sentry → RateLimit
    #
    # Every add_middleware call belongs in this block — including the one hidden
    # inside Instrumentator.instrument() at the end — or the real order silently
    # diverges from the documented one. This means:
    #   - Prometheus is truly outermost, so RED latency measures the whole stack;
    #     the trade-off is that TrustedHost rejections are counted too;
    #   - TrustedHost rejects a bad Host header before any of our middleware runs;
    #   - CORS wraps the rate limiter, so even a 429 carries CORS headers;
    #   - TraceContext sits directly inside CORS so every log line emitted during the
    #     request — including the rate limiter's localized 429 — carries the trace id;
    #   - Language sets the locale before RateLimit builds its (localized) 429 envelope;
    #   - RequestMeta populates the ip/user-agent ContextVar for every request so
    #     AuditLogHandler can enrich audit rows regardless of path.
    from app.core.rate_limit import RateLimitMiddleware

    # innermost
    application.add_middleware(
        RateLimitMiddleware,
        path_prefixes=("/api/v1/auth", "/api/v1/invitations"),
        max_requests=20,
        window_seconds=60,
        trust_forwarded_for=settings.trust_forwarded_for,
    )
    if settings.SENTRY_DSN:
        application.add_middleware(SentryMiddleware)
    application.add_middleware(
        RequestMetaMiddleware, trust_forwarded_for=settings.trust_forwarded_for
    )
    application.add_middleware(LanguageMiddleware)
    application.add_middleware(TraceContextMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        # Browsers hide non-safelisted response headers from JS unless named here.
        expose_headers=["traceparent"],
    )
    application.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.ALLOWED_HOSTS)
    # RED metrics into an app-owned registry (not the process-global default) so
    # building several apps in one test session cannot raise Duplicated timeseries.
    # instrument() is itself an add_middleware call, so it lives here, last:
    # truly outermost — metrics time the whole stack, including TrustedHost rejections.
    # excluded_handlers are re.search patterns against the route template (or, when
    # unmatched, the raw path), so anchor them — a bare "/health" would also swallow
    # something like /healthz-probe.
    metrics_registry = CollectorRegistry()
    application.state.metrics_registry = metrics_registry
    # Per-app so building several apps in one test session keeps separate budgets,
    # and so the throttle dies with the app rather than leaking across them.
    application.state.metrics_guard = MetricsFailureThrottle(
        trust_forwarded_for=settings.trust_forwarded_for
    )
    Instrumentator(
        registry=metrics_registry,
        excluded_handlers=["^/health$", "^/internal/metrics$"],
    ).instrument(application)
    # outermost

    # NOTE: No tenant middleware — clan isolation is enforced in the
    # application/repository layer (every clan-scoped read takes clan_id).
    # Users select their active clan via the X-Current-Clan-Id header.
    # DB-level RLS layer-2 (SP-3, ADR-008) is defense-in-depth behind that: Phase 1 is
    # active for `documents` via the request-role seam (app/core/rls.py).

    # Include API v1 routes
    application.include_router(api_v1_router, prefix="/api/v1")

    @application.get("/internal/metrics", include_in_schema=False)
    async def internal_metrics(request: Request) -> Response:
        """Prometheus exposition. 404 — never 401 — on every failure path so an
        unauthenticated scan cannot confirm the endpoint exists (ADR-021).

        Envelope-exempt like /health: the body is text/plain exposition format.

        Every rejection below raises the *same* bare 404, which is byte-identical
        to the framework's 404 for a path that does not exist (both become
        `StarletteHTTPException(404, "Not Found")` through the one exception
        handler). That is the ADR-021 property, and the failure throttle added in
        ADR-040 deliberately does not get a status code of its own: a 429 here
        would tell an unauthenticated scanner both that the path exists and that
        it is worth guarding. The attacker's guesses simply stop being evaluated.
        """
        guard: MetricsFailureThrottle = request.app.state.metrics_guard
        not_found = StarletteHTTPException(status_code=404)

        # Switched off: nothing exists to guess, so answer exactly like an unknown
        # path and record nothing. Internet background noise on this path must not
        # be able to grow the throttle's table while the feature is disabled --
        # which is its default state.
        if not settings.METRICS_ENABLED:
            raise not_found

        # Enabled, but the configured token is empty or below the ADR-040 floor.
        # Settings validation rejects that at boot, so getting here means the gate
        # was bypassed (a test monkeypatch, a directly-constructed Settings, some
        # future config path). Fail closed: a skipped validation must never be the
        # reason a guessable endpoint starts serving. Reported once per app, at
        # error level, because a silent 404 is indistinguishable from "switched
        # off" to whoever is debugging the scrape.
        if metrics_token_weakness(settings.METRICS_TOKEN):
            if not guard.weak_token_reported:
                guard.weak_token_reported = True
                logger.error(
                    "METRICS_ENABLED is true but METRICS_TOKEN does not meet the minimum "
                    "length; /internal/metrics is serving 404 to every request. Set a "
                    "token from `openssl rand -hex 32`."
                )
            raise not_found

        # Budget check BEFORE the comparison. Evaluating the guess and merely
        # withholding the body would leave the guessing itself unthrottled, which
        # is the thing being throttled. Successful scrapes never consume budget,
        # so a scraper holding the right token can never be locked out by this.
        client_ip = guard.client_ip(
            request.headers.get, request.client.host if request.client else None
        )
        if guard.is_exhausted(client_ip):
            raise not_found

        token = request.headers.get("X-Metrics-Token")
        # Compare BYTES, not str, on both sides -- and reconstruct the *exact* wire
        # bytes on each, not a re-encoding of the decoded str.
        #
        # Header side: Starlette decodes header bytes as latin-1, so every byte
        # 0x00-0xFF round-trips losslessly through str <-> latin-1. token.encode
        # ("latin-1") is therefore always defined and reproduces the raw bytes the
        # client sent. (Re-encoding as UTF-8 -- the previous approach -- cannot
        # raise either, since latin-1-decoded code points are always <= U+00FF, but
        # it silently compares mojibake instead of the wire bytes, so a non-ASCII
        # token could never match.)
        #
        # Configured side: METRICS_TOKEN is read from os.environ, which decodes
        # with surrogateescape (PEP 383) -- a value holding bytes that are not
        # valid UTF-8 becomes a str containing surrogate code points. Re-encoding
        # that with plain .encode("utf-8") raises UnicodeEncodeError, which is an
        # unauthenticated 500 that distinguishes this endpoint from a nonexistent
        # path -- the same ADR-021 existence oracle this comparison exists to
        # close, just operator-triggered instead of attacker-triggered.
        # .encode("utf-8", "surrogateescape") mirrors os.environ's own decoding
        # step, so it round-trips the exact configured bytes and cannot raise --
        # and, as a side effect, a non-ASCII METRICS_TOKEN can now actually
        # authenticate (see .env.example for the byte-exactness caveat that still
        # applies to how it's typed into the environment).
        if token is None or not secrets.compare_digest(
            token.encode("latin-1"),
            settings.METRICS_TOKEN.encode("utf-8", "surrogateescape"),
        ):
            # The trace §3.1 was missing: a failed attempt used to be a silent 404,
            # so a brute-force campaign left no record anywhere. Log volume is
            # bounded by construction -- the exhaustion check above returns before
            # this line -- to at most max_failures lines per IP per window, so the
            # logging cannot itself be amplified into a cost attack. The attempted
            # token is deliberately NOT logged: a near-miss in a log file is a
            # credential leak.
            attempts = guard.record_failure(client_ip)
            logger.warning(
                "Rejected /internal/metrics token (%d/%d failed attempts in %ds) from %s",
                attempts,
                guard.max_failures,
                guard.window_seconds,
                client_ip,
            )
            raise not_found
        return Response(
            generate_latest(request.app.state.metrics_registry),
            media_type=CONTENT_TYPE_LATEST,
        )

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
