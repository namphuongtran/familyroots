"""Domain-level exceptions.

These are framework-agnostic (no FastAPI imports). The HTTP adapter layer
maps them to appropriate HTTP status codes via the exception mapper in
``app.core.exceptions``.
"""

from __future__ import annotations

from typing import Any


class DomainError(Exception):
    """Base exception for all domain errors."""

    def __init__(self, code: str = "domain_error", detail: dict[str, Any] | None = None) -> None:
        self.code = code
        self.detail = detail or {}
        super().__init__(code)


class EntityNotFoundError(DomainError):
    """Raised when a requested entity does not exist."""

    def __init__(self, code: str = "not_found", detail: dict[str, Any] | None = None) -> None:
        super().__init__(code, detail)


class BusinessRuleViolation(DomainError):
    """Raised when a business invariant is violated."""

    def __init__(
        self, code: str = "business_rule_violation", detail: dict[str, Any] | None = None
    ) -> None:
        super().__init__(code, detail)


class ConflictError(DomainError):
    """Raised on duplicate or conflicting state."""

    def __init__(self, code: str = "conflict", detail: dict[str, Any] | None = None) -> None:
        super().__init__(code, detail)


class ForbiddenError(DomainError):
    """Raised when the actor lacks permission."""

    def __init__(self, code: str = "forbidden", detail: dict[str, Any] | None = None) -> None:
        super().__init__(code, detail)


class AuthenticationError(DomainError):
    """Raised on authentication failures (invalid credentials, expired tokens)."""

    def __init__(
        self, code: str = "authentication_error", detail: dict[str, Any] | None = None
    ) -> None:
        super().__init__(code, detail)


class ValidationError(DomainError):
    """Raised on input validation failures (invalid format, out-of-range values)."""

    def __init__(
        self, code: str = "validation_error", detail: dict[str, Any] | None = None
    ) -> None:
        super().__init__(code, detail)
