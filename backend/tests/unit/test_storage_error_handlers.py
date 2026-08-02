"""Storage errors map to 503/404 envelopes, and the handlers are registered."""

import json

import pytest
from starlette.requests import Request

from app.core.exceptions import (
    storage_bucket_not_configured_handler,
    storage_not_found_handler,
    storage_unavailable_handler,
)
from app.domain.document.repository import (
    StorageBucketNotConfiguredError,
    StorageNotFoundError,
    StorageUnavailableError,
)
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


@pytest.mark.asyncio
async def test_bucket_not_configured_handler_returns_its_own_503_envelope() -> None:
    """A missing public avatar bucket (ADR-036) is 503 under its OWN code — not a
    404 (that would blame the caller for our infrastructure gap) and not a 500."""
    load_translations()
    resp = await storage_bucket_not_configured_handler(
        _req(), StorageBucketNotConfiguredError("bucket 'family-roots-avatars' is missing")
    )
    assert resp.status_code == 503
    body = json.loads(bytes(resp.body))
    assert body["error"]["code"] == "storage_bucket_not_configured"
    assert body["error"]["message"]
    assert body["error"]["message"] != "error.storage_bucket_not_configured"
    # The raw provider/config detail stays in the log, never in the response.
    assert body["error"]["detail"] == {}


def test_handlers_are_registered() -> None:
    app = create_app()
    assert StorageUnavailableError in app.exception_handlers
    assert StorageNotFoundError in app.exception_handlers
    assert StorageBucketNotConfiguredError in app.exception_handlers


def test_bucket_error_is_not_a_subclass_of_the_other_storage_errors() -> None:
    """Starlette resolves handlers by MRO. If StorageBucketNotConfiguredError ever
    subclassed StorageUnavailableError/StorageNotFoundError, registration order would
    decide which envelope a misconfigured bucket produces — pin it flat instead."""
    assert not issubclass(StorageBucketNotConfiguredError, StorageUnavailableError)
    assert not issubclass(StorageBucketNotConfiguredError, StorageNotFoundError)
