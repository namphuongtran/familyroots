"""A transient DB operational failure must surface as a truthful 503, not a 500.

A dropped connection, pool exhaustion, or a DB restart mid-request raises a SQLAlchemy
OperationalError (the infrastructural DBAPI class). Before ADR-032 nothing mapped it, so
it fell to the catch-all -> opaque 500 internal_error -- misleading a retryable client and
inconsistent with /health, which already reports `degraded` on DB failure. It must be a
503 database_unavailable envelope. ProgrammingError/DataError (our bugs) stay loud 500s.
"""

import json

import pytest
from sqlalchemy.exc import OperationalError
from starlette.requests import Request
from starlette.testclient import TestClient

from app.core.exceptions import database_unavailable_handler
from app.main import create_app
from app.services.translator import load_translations


def _req() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/x", "headers": []})


def _op_error() -> OperationalError:
    # (statement, params, orig) — orig is the raw DBAPI error whose text must NOT leak.
    return OperationalError("SELECT 1", {}, Exception("server closed the connection unexpectedly"))


@pytest.mark.asyncio
async def test_handler_returns_503_envelope() -> None:
    load_translations()
    resp = await database_unavailable_handler(_req(), _op_error())
    assert resp.status_code == 503
    body = json.loads(bytes(resp.body))
    assert body["error"]["code"] == "database_unavailable"
    assert body["error"]["message"] and body["error"]["message"] != "error.database_unavailable"
    # The raw DBAPI detail must never reach the client.
    assert "server closed" not in json.dumps(body)


def test_operational_error_handler_is_registered() -> None:
    assert OperationalError in create_app().exception_handlers


def test_operational_error_routes_to_503_end_to_end() -> None:
    """Prove Starlette's MRO matching sends a real OperationalError to the 503 handler
    (over the catch-all Exception -> 500), through the full app."""
    load_translations()
    app = create_app()

    @app.get("/_boom_db")
    async def _boom() -> None:
        raise _op_error()

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/_boom_db")
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "database_unavailable"
    assert "server closed" not in resp.text
