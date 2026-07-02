"""Custom exception classes and global exception handler with i18n support."""

import logging
from typing import Any

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request

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
    from app.services.translator import t

    assert isinstance(exc, DomainError)

    status_map: dict[type[DomainError], int] = {
        EntityNotFoundError: 404,
        DomainForbiddenError: 403,
        DomainConflictError: 409,
        DomainAuthError: 401,
        BusinessRuleViolation: 422,
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


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all: log the real error server-side, return the standard envelope.

    Never leaks the exception message or traceback to the client.
    """
    from app.services.translator import t

    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": t("error.internal_error"),
                "detail": {},
            }
        },
    )
