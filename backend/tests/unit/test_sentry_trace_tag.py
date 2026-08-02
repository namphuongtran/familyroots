"""SentryMiddleware tags events with the W3C trace id.

sentry_sdk.push_scope is monkeypatched with a recorder so the test asserts on
tags without needing a DSN, a transport, or network access.
"""

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
import sentry_sdk
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware.sentry_middleware import SentryMiddleware
from app.middleware.trace_middleware import TraceContextMiddleware


class _RecordingScope:
    def __init__(self) -> None:
        self.tags: dict[str, str] = {}

    def set_tag(self, key: str, value: str) -> None:
        self.tags[key] = value


@pytest.fixture
def recorded_tags(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    scope = _RecordingScope()

    @contextmanager
    def _fake_push_scope() -> Iterator[_RecordingScope]:
        yield scope

    monkeypatch.setattr(sentry_sdk, "push_scope", _fake_push_scope)
    return scope.tags


def _app() -> FastAPI:
    app = FastAPI()

    @app.get("/ping")
    async def ping() -> dict[str, str]:
        return {"ok": "yes"}

    # Added last = outermost, so TraceContext runs before Sentry, exactly as in main.py.
    app.add_middleware(SentryMiddleware)
    app.add_middleware(TraceContextMiddleware)
    return app


def test_trace_id_is_tagged_and_matches_the_response_header(
    recorded_tags: dict[str, str],
) -> None:
    response = TestClient(_app()).get("/ping")
    assert response.status_code == 200
    assert recorded_tags["trace_id"] in response.headers["traceparent"]


def test_existing_tags_are_still_set(recorded_tags: dict[str, str]) -> None:
    TestClient(_app()).get("/ping", headers={"X-Current-Clan-Id": "clan-1"})
    assert recorded_tags["path"] == "/ping"
    assert recorded_tags["method"] == "GET"
    assert recorded_tags["clan_id"] == "clan-1"
