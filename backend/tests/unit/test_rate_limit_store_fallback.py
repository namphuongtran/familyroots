"""A failing shared store hands the decision to the in-memory bucket (ADR-072, #257).

Sign-in must never fail because the rate limit's store is down. So when the Upstash call
errors, times out, or answers something unreadable, the request is decided by this
instance's in-memory bucket, and Sentry gets a warning, at most once a window.

Each case builds the real app on the production adapter, ``UpstashRateLimitStore``, with
the network replaced by one failure, and sends 21 ``POST /api/v1/auth/login`` with body
``{}``. That route is counted, and that body answers 422 before the handler runs. The
reading is twenty 422 and then one 429: no 5xx, and still a limit. A fallback that
admitted everything would read 422 for the 21st; one that let the failure through would
read 500.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Callable

import httpx2
import pytest
import sentry_sdk
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient

import app.main as main_module
from app.core.config import Settings
from app.core.database import get_db
from app.infrastructure.upstash_rate_limit_store import UpstashRateLimitStore
from app.main import create_app

pytestmark = pytest.mark.unit


async def _no_db() -> AsyncIterator[None]:
    yield None


def _refuse_connection(request: httpx2.Request) -> httpx2.Response:
    raise httpx2.ConnectError("connection refused", request=request)


def _wrong_token(request: httpx2.Request) -> httpx2.Response:
    return httpx2.Response(401, json={"error": "Invalid token"})


def _script_error(request: httpx2.Request) -> httpx2.Response:
    return httpx2.Response(400, json={"error": "ERR Error running script"})


def _not_json(request: httpx2.Request) -> httpx2.Response:
    return httpx2.Response(200, text="<html>gateway error</html>")


def _another_shape(request: httpx2.Request) -> httpx2.Response:
    return httpx2.Response(200, json={"result": None})


_FAILURES: dict[str, Callable[[httpx2.Request], httpx2.Response]] = {
    "connection refused": _refuse_connection,
    "wrong token": _wrong_token,
    "script error": _script_error,
    "not JSON": _not_json,
    "another shape": _another_shape,
}


class _SentryMessages:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def __call__(self, message: str, level: str) -> None:
        self.calls.append((message, level))


@pytest.fixture()
def sentry_messages(monkeypatch: pytest.MonkeyPatch) -> _SentryMessages:
    messages = _SentryMessages()
    # The middleware looks the function up on the module at each call, so this reaches it.
    monkeypatch.setattr(sentry_sdk, "capture_message", messages)
    return messages


def _app(monkeypatch: pytest.MonkeyPatch, store: UpstashRateLimitStore) -> FastAPI:
    monkeypatch.delenv("RATE_LIMIT_AUTH_MAX_REQUESTS", raising=False)
    monkeypatch.setattr(main_module, "settings", Settings(_env_file=None))
    application = create_app(rate_limit_store=store)
    application.dependency_overrides[get_db] = _no_db
    return application


async def _logins(application: FastAPI, count: int) -> list[int]:
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        return [
            (await client.post("/api/v1/auth/login", json={})).status_code for _ in range(count)
        ]


async def test_a_url_the_client_cannot_parse_falls_back_too(
    monkeypatch: pytest.MonkeyPatch, sentry_messages: _SentryMessages
) -> None:
    """A malformed ``KV_REST_API_URL`` raises ``InvalidURL``, which is not an ``HTTPError``.
    Settings check only that the pair is present, so this reaches the adapter at request time."""
    store = UpstashRateLimitStore(url="http://[::1", token="t", key_prefix="test:")

    statuses = await _logins(_app(monkeypatch, store), 21)

    assert statuses == [422] * 20 + [429], statuses
    assert len(sentry_messages.calls) == 1, sentry_messages.calls
    assert "InvalidURL" in sentry_messages.calls[0][0]


@pytest.mark.parametrize("failure", list(_FAILURES), ids=list(_FAILURES))
async def test_a_failing_store_falls_back_to_the_in_memory_bucket(
    monkeypatch: pytest.MonkeyPatch, sentry_messages: _SentryMessages, failure: str
) -> None:
    store = UpstashRateLimitStore(
        url="https://store.invalid",
        token="t",
        key_prefix="test:",
        transport=httpx2.MockTransport(_FAILURES[failure]),
    )

    statuses = await _logins(_app(monkeypatch, store), 21)

    assert statuses == [422] * 20 + [429], statuses
    # One warning for 21 failures: the outage is one fact, not one per request.
    assert len(sentry_messages.calls) == 1, sentry_messages.calls
    message, level = sentry_messages.calls[0]
    assert level == "warning"
    assert "Rate limit store unavailable" in message


async def test_a_store_that_never_answers_is_abandoned_at_the_timeout(
    monkeypatch: pytest.MonkeyPatch, sentry_messages: _SentryMessages
) -> None:
    """A real socket that accepts and never answers, so the deadline is the real one."""
    held: list[asyncio.StreamWriter] = []

    async def _silent(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        held.append(writer)

    server = await asyncio.start_server(_silent, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    store = UpstashRateLimitStore(
        url=f"http://127.0.0.1:{port}", token="t", key_prefix="test:", timeout_seconds=0.2
    )
    try:
        started = time.monotonic()
        # Without the adapter's deadline the first request would wait forever, so bound the
        # whole reading here and let that fail the test instead of hanging the suite.
        async with asyncio.timeout(10):
            statuses = await _logins(_app(monkeypatch, store), 3)
        elapsed = time.monotonic() - started
    finally:
        for writer in held:
            writer.close()
        server.close()
        await server.wait_closed()

    assert statuses == [422] * 3, statuses
    # Three requests at a 0.2-second deadline each.
    assert elapsed < 2, elapsed
    assert len(sentry_messages.calls) == 1, sentry_messages.calls
    assert "no answer within 0.2 seconds" in sentry_messages.calls[0][0]
