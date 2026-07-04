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


def _body(response: JSONResponse) -> dict[str, Any]:
    parsed: dict[str, Any] = json.loads(bytes(response.body))
    return parsed


@pytest.mark.asyncio
async def test_integrity_error_becomes_409_conflict() -> None:
    exc = IntegrityError(
        "INSERT INTO user_profiles ...",
        {},
        Exception("duplicate key value violates unique constraint"),
    )
    resp = await integrity_error_handler(_REQ, exc)

    assert resp.status_code == 409
    body = _body(resp)
    assert set(body["error"]) == {"code", "message", "detail"}
    assert body["error"]["code"] == "conflict"
    # The raw DB message must not leak to the client.
    assert "duplicate key" not in json.dumps(body)
