"""Custom exception classes and global exception handler with i18n support."""

import logging
from typing import Any

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from starlette.requests import Request

logger = logging.getLogger(__name__)


class AppError(HTTPException):
    """Base application error with machine-readable code."""

    def __init__(self, status_code: int, code: str, detail: dict[str, Any] | None = None):
        super().__init__(
            status_code=status_code,
            detail={"code": code, "detail": detail or {}},
        )


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
