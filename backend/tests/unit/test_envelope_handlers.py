"""The bare-HTTPException and request-validation handlers emit the standard envelope.

C11: auth/RBAC raised bare HTTPExceptions that returned FastAPI's {detail} shape,
and Pydantic 422s did too. These handlers normalize both into
{error:{code,message,detail}} so clients can parse error.code uniformly.
"""

import json
from typing import Any

import pytest
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request

from app.core.exceptions import http_exception_handler, validation_exception_handler

pytestmark = [pytest.mark.unit]

_REQ = Request({"type": "http", "method": "GET", "path": "/", "headers": []})


def _body(response: JSONResponse) -> dict[str, Any]:
    parsed: dict[str, Any] = json.loads(bytes(response.body))
    return parsed


@pytest.mark.asyncio
async def test_bare_http_exception_is_normalized() -> None:
    resp = await http_exception_handler(
        _REQ, StarletteHTTPException(403, "Insufficient permissions")
    )
    assert resp.status_code == 403
    body = _body(resp)
    assert set(body["error"]) == {"code", "message", "detail"}
    assert body["error"]["code"] == "forbidden"
    # The raw human string is preserved only as a hint, not as the code.
    assert body["error"]["detail"]["hint"] == "Insufficient permissions"


@pytest.mark.asyncio
async def test_unmapped_status_falls_back_to_http_error() -> None:
    resp = await http_exception_handler(_REQ, StarletteHTTPException(418, "teapot"))
    assert resp.status_code == 418
    assert _body(resp)["error"]["code"] == "http_error"


@pytest.mark.asyncio
async def test_request_validation_error_is_normalized() -> None:
    exc = RequestValidationError(
        [{"loc": ("body", "name"), "msg": "field required", "type": "missing"}]
    )
    resp = await validation_exception_handler(_REQ, exc)
    assert resp.status_code == 422
    body = _body(resp)
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["detail"]["fields"] == ["body.name"]
