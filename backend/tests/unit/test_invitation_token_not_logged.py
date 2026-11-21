"""An invitation token reaches neither a JSON log line nor a Sentry event (#317).

Drives ``POST /api/v1/invitations/<token>/accept`` through the real trace and Sentry
middlewares, reads the formatted JSON log line, and reads the event a real Sentry client
hands to a stub transport, with the hooks ``create_app`` installs.
"""

import json
import logging
from collections.abc import Iterator
from typing import Any

import pytest
import sentry_sdk
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sentry_sdk.transport import Transport

from app.core.logging import JsonFormatter
from app.core.path_redaction import scrub_sentry_event
from app.middleware.sentry_middleware import SentryMiddleware
from app.middleware.trace_middleware import TraceContextMiddleware

TOKEN = "tok_SECRET_9f8e7d6c5b4a"
PERSON = "7b0f2a3e-1111-4222-8333-444455556666"
_log = logging.getLogger("test.accept")


class _Capture(Transport):
    def __init__(self) -> None:
        super().__init__()
        self.payloads: list[Any] = []

    def capture_envelope(self, envelope: Any) -> None:
        for item in envelope.items:
            self.payloads.append(item.payload.json)


def _app() -> FastAPI:
    app = FastAPI()

    @app.post("/api/v1/invitations/{token}/accept")
    async def accept(token: str) -> dict[str, str]:
        _log.warning("accepting")
        raise RuntimeError("boom")

    @app.get("/api/v1/persons/{person_id}")
    async def person(person_id: str) -> dict[str, str]:
        _log.warning("reading")
        return {}

    app.add_middleware(SentryMiddleware)
    app.add_middleware(TraceContextMiddleware)
    return app


class _Lines(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.setFormatter(JsonFormatter())
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(self.format(record))


@pytest.fixture
def lines() -> Iterator[list[str]]:
    handler = _Lines()
    _log.addHandler(handler)
    yield handler.lines
    _log.removeHandler(handler)


@pytest.fixture
def transport() -> Iterator[_Capture]:
    stub = _Capture()
    sentry_sdk.init(
        dsn="http://key@localhost/1",
        transport=stub,
        traces_sample_rate=1.0,
        release="test",
        before_send=scrub_sentry_event,
        before_send_transaction=scrub_sentry_event,
        before_breadcrumb=scrub_sentry_event,
    )
    yield stub
    sentry_sdk.get_client().close()
    sentry_sdk.init()


def test_accept_token_is_in_no_log_line_and_no_sentry_event(
    lines: list[str], transport: _Capture
) -> None:
    client = TestClient(_app(), raise_server_exceptions=False)
    response = client.post(f"/api/v1/invitations/{TOKEN}/accept")
    assert response.status_code == 500
    sentry_sdk.flush()

    assert lines, "the route logged nothing, so the log reading is vacuous"
    assert json.loads(lines[0])["route"] == "/api/v1/invitations/{token}/accept"
    assert all(TOKEN not in line for line in lines)

    assert transport.payloads, "no Sentry event reached the transport"
    dumps = [json.dumps(p) for p in transport.payloads]
    leaks = [d[max(0, d.find(TOKEN) - 80) :][:200] for d in dumps if TOKEN in d]
    assert not leaks, leaks


def test_person_paths_stay_distinct(lines: list[str]) -> None:
    TestClient(_app()).get(f"/api/v1/persons/{PERSON}")
    assert json.loads(lines[0])["route"] == f"/api/v1/persons/{PERSON}"
