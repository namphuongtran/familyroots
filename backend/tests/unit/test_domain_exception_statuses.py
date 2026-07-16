"""Every domain exception maps to the same HTTP status its core twin used.

The application layer is migrating off core.exceptions (which subclasses
HTTPException — a framework leak into use-cases) onto the framework-agnostic
domain hierarchy. That migration is wire-neutral ONLY if the domain mapper
assigns identical statuses; ValidationError was missing from the status map
and would have silently fallen from 422 to the 400 default.
"""

from __future__ import annotations

import json

import pytest
from starlette.requests import Request

from app.core.exceptions import domain_exception_handler
from app.domain.shared.exceptions import (
    AuthenticationError,
    BusinessRuleViolation,
    ConflictError,
    DomainError,
    EntityNotFoundError,
    ForbiddenError,
    ValidationError,
)

pytestmark = pytest.mark.asyncio

_REQ = Request({"type": "http", "method": "GET", "path": "/x", "headers": []})

_EXPECTED: list[tuple[DomainError, int]] = [
    (EntityNotFoundError("not_found"), 404),
    (ForbiddenError("forbidden"), 403),
    (ConflictError("conflict"), 409),
    (AuthenticationError("authentication_error"), 401),
    (BusinessRuleViolation("business_rule_violation"), 422),
    (ValidationError("validation_error"), 422),
]


@pytest.mark.parametrize(("exc", "status"), _EXPECTED, ids=[type(e).__name__ for e, _ in _EXPECTED])
async def test_domain_exception_status(exc: DomainError, status: int) -> None:
    resp = await domain_exception_handler(_REQ, exc)
    assert resp.status_code == status
    body = json.loads(bytes(resp.body))
    assert body["error"]["code"] == exc.code
    assert set(body["error"]) == {"code", "message", "detail"}
