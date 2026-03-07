"""Custom exception classes and global exception handler with i18n support."""

from typing import Any

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from starlette.requests import Request


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
