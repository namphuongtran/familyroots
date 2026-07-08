"""Storage errors map to 503/404 envelopes, and the handlers are registered."""

import json

import pytest
from starlette.requests import Request

from app.core.exceptions import storage_not_found_handler, storage_unavailable_handler
from app.domain.document.repository import StorageNotFoundError, StorageUnavailableError
from app.main import create_app
from app.services.translator import load_translations


def _req() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/x", "headers": []})


@pytest.mark.asyncio
async def test_unavailable_handler_returns_503_envelope() -> None:
    load_translations()
    resp = await storage_unavailable_handler(_req(), StorageUnavailableError("down"))
    assert resp.status_code == 503
    body = json.loads(bytes(resp.body))
    assert body["error"]["code"] == "storage_unavailable"
    assert body["error"]["message"] and body["error"]["message"] != "error.storage_unavailable"


@pytest.mark.asyncio
async def test_not_found_handler_returns_404_envelope() -> None:
    load_translations()
    resp = await storage_not_found_handler(_req(), StorageNotFoundError("missing"))
    assert resp.status_code == 404
    body = json.loads(bytes(resp.body))
    assert body["error"]["code"] == "storage_not_found"
    assert body["error"]["message"] and body["error"]["message"] != "error.storage_not_found"


def test_handlers_are_registered() -> None:
    app = create_app()
    assert StorageUnavailableError in app.exception_handlers
    assert StorageNotFoundError in app.exception_handlers
