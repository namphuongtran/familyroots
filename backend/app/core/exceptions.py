"""Custom exception classes and global exception handler with i18n support."""

import logging
from typing import Any

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request

from app.core.trace_context import TraceContext, reset_trace_context, set_trace_context

logger = logging.getLogger(__name__)


class AppError(HTTPException):
    """Base application error with machine-readable code."""

    def __init__(self, status_code: int, code: str, detail: dict[str, Any] | None = None):
        super().__init__(
            status_code=status_code,
            detail={"code": code, "detail": detail or {}},
        )


class AuthenticationError(AppError):
    def __init__(self, code: str = "authentication_error", detail: dict[str, Any] | None = None):
        super().__init__(401, code, detail)


class NotFoundError(AppError):
    def __init__(self, code: str = "not_found", detail: dict[str, Any] | None = None):
        super().__init__(404, code, detail)


class ForbiddenError(AppError):
    def __init__(self, code: str = "forbidden", detail: dict[str, Any] | None = None):
        super().__init__(403, code, detail)


class ConflictError(AppError):
    def __init__(self, code: str = "conflict", detail: dict[str, Any] | None = None):
        super().__init__(409, code, detail)


class ValidationError(AppError):
    def __init__(self, code: str = "validation_error", detail: dict[str, Any] | None = None):
        super().__init__(422, code, detail)


async def app_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Global handler that converts AppError into the standard error envelope."""
    from app.services.translator import t

    assert isinstance(exc, AppError)
    detail = exc.detail
    assert isinstance(detail, dict)
    code = detail["code"]
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": code,
                "message": t(f"error.{code}"),
                "detail": detail.get("detail", {}),
            }
        },
    )


# ── Domain-to-HTTP exception mapper ──────────────────────────────


async def domain_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Map framework-agnostic domain exceptions to the standard HTTP error envelope.

    Registered alongside ``app_exception_handler`` in ``main.py`` so that
    domain code never needs to import FastAPI exception types.
    """
    from app.domain.shared.exceptions import (
        AuthenticationError as DomainAuthError,
    )
    from app.domain.shared.exceptions import (
        BusinessRuleViolation,
        DomainError,
        EntityNotFoundError,
    )
    from app.domain.shared.exceptions import (
        ConflictError as DomainConflictError,
    )
    from app.domain.shared.exceptions import (
        ForbiddenError as DomainForbiddenError,
    )
    from app.domain.shared.exceptions import (
        ValidationError as DomainValidationError,
    )
    from app.services.translator import t

    assert isinstance(exc, DomainError)

    status_map: dict[type[DomainError], int] = {
        EntityNotFoundError: 404,
        DomainForbiddenError: 403,
        DomainConflictError: 409,
        DomainAuthError: 401,
        BusinessRuleViolation: 422,
        DomainValidationError: 422,
    }
    status_code = status_map.get(type(exc), 400)

    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": exc.code,
                "message": t(f"error.{exc.code}"),
                "detail": exc.detail,
            }
        },
    )


async def identity_unavailable_handler(request: Request, exc: Exception) -> JSONResponse:
    """Surface identity-provider outages/misconfiguration as 503, in one place.

    Any auth path (login/register/refresh/onboard) that hits a DNS failure,
    provider 5xx, or rejected API key gets a truthful 503 envelope instead of a
    misleading 401 "invalid credentials" or an opaque 500."""
    from app.services.translator import t

    logger.error("Identity provider unavailable: %s", exc)
    code = "auth_provider_unavailable"
    return JSONResponse(
        status_code=503,
        content={
            "error": {
                "code": code,
                "message": t(f"error.{code}"),
                "detail": {},
            }
        },
    )


async def identity_email_not_verified_handler(request: Request, exc: Exception) -> JSONResponse:
    """Surface an unverified-email login as 403 in one place (never 401)."""
    from app.services.translator import t

    code = "email_not_verified"
    return JSONResponse(
        status_code=403,
        content={"error": {"code": code, "message": t(f"error.{code}"), "detail": {}}},
    )


async def storage_unavailable_handler(request: Request, exc: Exception) -> JSONResponse:
    """Surface storage-backend outages/misconfiguration as 503, in one place."""
    from app.services.translator import t

    logger.error("Storage unavailable on %s %s: %s", request.method, request.url.path, exc)
    code = "storage_unavailable"
    return JSONResponse(
        status_code=503,
        content={"error": {"code": code, "message": t(f"error.{code}"), "detail": {}}},
    )


async def storage_not_found_handler(request: Request, exc: Exception) -> JSONResponse:
    """A referenced storage object does not exist — surface as 404, not 500."""
    from app.services.translator import t

    code = "storage_not_found"
    return JSONResponse(
        status_code=404,
        content={"error": {"code": code, "message": t(f"error.{code}"), "detail": {}}},
    )


async def database_unavailable_handler(request: Request, exc: Exception) -> JSONResponse:
    """Surface a transient DB operational failure as 503, in one place (ADR-032).

    A dropped connection, pool exhaustion, DB restart/shutdown, or resource
    exhaustion mid-request raises a SQLAlchemy ``OperationalError`` (the DBAPI class
    for failures not under the programmer's control) — a "try again", not a bug. It
    must be a truthful ``503 database_unavailable`` rather than an opaque 500, matching
    ``/health``'s ``degraded`` and the storage/identity 503 handlers. Only
    ``OperationalError`` routes here; ``ProgrammingError``/``DataError`` (our bugs) stay
    loud 500s via the catch-all. The raw DBAPI message is logged, never returned."""
    from app.services.translator import t

    logger.error("Database unavailable on %s %s: %s", request.method, request.url.path, exc)
    code = "database_unavailable"
    return JSONResponse(
        status_code=503,
        content={"error": {"code": code, "message": t(f"error.{code}"), "detail": {}}},
    )


_STATUS_CODE_TO_ERROR_CODE = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "validation_error",
    429: "rate_limited",
}


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Normalize bare Starlette/FastAPI HTTPExceptions into the standard envelope.

    AppError subclasses are routed to ``app_exception_handler`` (more specific), so
    this only catches plain HTTPExceptions — framework-raised ones (404 route,
    405 method) and any remaining bare ``raise HTTPException`` — and gives them the
    stable ``{error:{code,message,detail}}`` shape instead of FastAPI's ``{detail}``.
    """
    from app.services.translator import t

    assert isinstance(exc, StarletteHTTPException)
    code = _STATUS_CODE_TO_ERROR_CODE.get(exc.status_code, "http_error")
    # exc.detail is a human string here (AppError, which uses a dict, is handled
    # elsewhere); surface the localized message for the code and keep the raw
    # string as a hint in detail.
    message = t(f"error.{code}")
    detail = {"hint": exc.detail} if isinstance(exc.detail, str) else {}
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": code, "message": message, "detail": detail}},
    )


async def validation_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Map FastAPI request-validation (422) errors to the standard envelope."""
    from app.services.translator import t

    assert isinstance(exc, RequestValidationError)
    fields = [".".join(str(p) for p in err.get("loc", [])) for err in exc.errors()]
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": t("error.validation_error"),
                "detail": {"fields": fields},
            }
        },
    )


async def integrity_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Map a DB *unique* violation to a clean 409; keep every other IntegrityError loud.

    Safety net for the one constraint failure that is a legitimate client outcome — a
    write that loses a uniqueness race (SQLSTATE 23505) — which surfaces as the stable
    conflict envelope instead of a raw 500. Any OTHER integrity error (FK, NOT NULL,
    CHECK) is almost always a server-side logic bug, so it is logged with a full
    traceback (for logs/Sentry) and returned as 500 — never silently downgraded to a
    409. Hot paths that can race (e.g. identity-claim linking) still take row locks to
    fail earlier and more precisely; this only catches what they miss.
    """
    from app.services.translator import t

    orig = getattr(exc, "orig", None)
    sqlstate = getattr(orig, "sqlstate", None)
    constraint = getattr(getattr(orig, "diag", None), "constraint_name", None)

    if sqlstate == "23505":  # unique_violation
        logger.warning("Unique violation on %s %s: %s", request.method, request.url.path, exc)
        # A named partial-unique index whose race IS a specific client outcome maps to its
        # own code (so the loser of e.g. two fresh concurrent invites sees the same code
        # the app pre-check would raise); everything else is the stable generic conflict.
        unique_codes = {
            "uq_clan_invitations_pending": "invitation.pending_exists",
            "uq_marriages_spouse_order": "relationship.duplicate_spouse_order",
            # A concurrent clan-create race that loses the slug uniqueness (the app
            # pre-checks get_clan_by_slug, but that is a TOCTOU) surfaces the SAME code
            # the pre-check raises, not the generic conflict.
            "uq_clans_slug": "auth.clan_slug_taken",
        }
        code = unique_codes.get(constraint or "", "conflict")
        return JSONResponse(
            status_code=409,
            content={"error": {"code": code, "message": t(f"error.{code}"), "detail": {}}},
        )

    # check_violation (23514) has two shapes:
    #  (a) a real named CHECK constraint the app pre-check normally shadows (e.g. a
    #      divorce-before-marriage or self-edge write that slipped the pre-check) — map to
    #      its specific client code instead of a raw 500; and
    #  (b) an ADR-023 trigger RAISE with NO constraint name but a known slug in the message
    #      (a lost bio-parent/cycle race) — map by slug.
    # Any OTHER check_violation is a genuine server bug → falls through to the loud 500.
    if sqlstate == "23514":
        # Real DB names carry the SQLAlchemy naming-convention prefix (base.py:
        # ``ck_%(table_name)s_%(constraint_name)s``), doubled here because the migration's
        # own ``name=`` already included the table — pinned by test_integrity_constraint_names.
        check_constraints = {
            "ck_marriages_marriages_divorce_after_marriage": (
                422,
                "relationship.divorce_before_marriage",
            ),
            "ck_marriages_marriages_no_self": (422, "self_marriage_not_allowed"),
            "ck_parent_child_parent_child_no_self": (422, "self_parent_not_allowed"),
        }
        if constraint in check_constraints:
            status_code, code = check_constraints[constraint]
            logger.warning(
                "CHECK-constraint rejection (%s) on %s %s: %s",
                constraint,
                request.method,
                request.url.path,
                exc,
            )
            return JSONResponse(
                status_code=status_code,
                content={"error": {"code": code, "message": t(f"error.{code}"), "detail": {}}},
            )

        message = str(getattr(exc, "orig", exc))
        # Trigger slug -> the SAME error code the app validator uses, so a
        # client sees one code whether the pre-check or the backstop rejected.
        trigger_codes = {
            "too_many_biological_parents": "relationship.too_many_biological_parents",
            "relationship_cycle": "relationship.creates_cycle",
        }
        for slug, code in trigger_codes.items():
            if slug in message:
                logger.warning(
                    "Integrity-trigger rejection on %s %s: %s",
                    request.method,
                    request.url.path,
                    exc,
                )
                return JSONResponse(
                    status_code=409,
                    content={"error": {"code": code, "message": t(f"error.{code}"), "detail": {}}},
                )

    logger.error(
        "Unexpected IntegrityError on %s %s", request.method, request.url.path, exc_info=exc
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": {"code": "internal_error", "message": t("error.internal_error"), "detail": {}}
        },
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all: log the real error server-side, return the standard envelope.

    Never leaks the exception message or traceback to the client.

    Trace correlation needs re-establishing here, and only here. Starlette hoists any
    ``Exception``/500 handler out of ``ExceptionMiddleware`` into
    ``ServerErrorMiddleware``, which sits outside every user middleware — so
    ``TraceContextMiddleware`` has already run its ``finally`` and cleared the
    ContextVar by the time we are called. Without this, the one case correlation
    exists for (an unexplained 500) would be the one case with no ``trace_id`` in the
    log and no ``traceparent`` on the response. The middleware also stashes the
    context on the request scope's ``state``, which survives; we restore it around the
    log call and echo it on the response. Every other handler keys on a specific
    exception type, stays inside ``ExceptionMiddleware``, and needs none of this.
    """
    from app.services.translator import t

    # Absent when the exception was raised above TraceContextMiddleware.
    ctx: TraceContext | None = getattr(request.state, "trace_context", None)
    token = set_trace_context(ctx) if ctx is not None else None
    try:
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    finally:
        if token is not None:
            reset_trace_context(token)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": t("error.internal_error"),
                "detail": {},
            }
        },
        headers={"traceparent": ctx.to_traceparent()} if ctx is not None else None,
    )
