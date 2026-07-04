"""The global IntegrityError handler maps a DB constraint violation to a 409 envelope.

Backstop for any write that loses a uniqueness race (or otherwise violates a
constraint) without an explicit application guard — it must surface as the stable
conflict envelope, never a raw 500.
"""

import json
from typing import Any

import pytest
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.requests import Request

from app.core.exceptions import integrity_error_handler

pytestmark = [pytest.mark.unit]

_REQ = Request({"type": "http", "method": "POST", "path": "/x", "headers": []})


class _PgError(Exception):
    """Stand-in for the psycopg error under IntegrityError.orig (carries a SQLSTATE)."""

    def __init__(self, sqlstate: str) -> None:
        self.sqlstate = sqlstate
        super().__init__(f"db error {sqlstate}: duplicate key value violates unique constraint")


def _body(response: JSONResponse) -> dict[str, Any]:
    parsed: dict[str, Any] = json.loads(bytes(response.body))
    return parsed


@pytest.mark.asyncio
async def test_unique_violation_becomes_409_conflict() -> None:
    # 23505 = unique_violation — a lost race / duplicate.
    exc = IntegrityError("INSERT INTO user_profiles ...", {}, _PgError("23505"))
    resp = await integrity_error_handler(_REQ, exc)

    assert resp.status_code == 409
    body = _body(resp)
    assert set(body["error"]) == {"code", "message", "detail"}
    assert body["error"]["code"] == "conflict"
    # The raw DB message must not leak to the client.
    assert "duplicate key" not in json.dumps(body)


@pytest.mark.asyncio
async def test_non_unique_integrity_error_stays_a_500() -> None:
    # 23503 = foreign_key_violation — a server-side logic bug, must not be masked as 409.
    exc = IntegrityError("INSERT ...", {}, _PgError("23503"))
    resp = await integrity_error_handler(_REQ, exc)

    assert resp.status_code == 500
    assert _body(resp)["error"]["code"] == "internal_error"
