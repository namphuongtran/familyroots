"""The generic exception handler returns the standard envelope, no traceback."""

import json

import pytest
from starlette.requests import Request

from app.core.exceptions import unhandled_exception_handler


def _request() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "headers": []})


@pytest.mark.asyncio
async def test_unhandled_exception_returns_envelope_without_traceback():
    exc = RuntimeError("super secret internal detail")
    resp = await unhandled_exception_handler(_request(), exc)
    assert resp.status_code == 500
    body = json.loads(resp.body)
    assert body["error"]["code"] == "internal_error"
    assert "detail" in body["error"]
    # The internal exception text must NOT leak into the response.
    assert "super secret internal detail" not in resp.body.decode()
