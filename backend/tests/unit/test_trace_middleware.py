"""Every response carries a traceparent, and a caller's trace id survives.

Uses /health because it is the only route that needs no auth; it does touch the
DB, so a 200 or a 503 are both acceptable — the assertion is about headers, not
the body.
"""

import io
import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager

from fastapi.testclient import TestClient

from app.core.logging import JsonFormatter
from app.core.trace_context import parse_traceparent
from app.main import create_app

CALLER = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"


def _client() -> TestClient:
    # raise_server_exceptions=False so a handled 5xx still returns a response we
    # can inspect headers on, instead of re-raising into the test.
    return TestClient(create_app(), raise_server_exceptions=False)


def test_response_carries_a_valid_traceparent():
    response = _client().get("/health")
    parsed = parse_traceparent(response.headers.get("traceparent"))
    assert parsed is not None


def test_callers_trace_id_is_continued_with_a_new_span():
    response = _client().get("/health", headers={"traceparent": CALLER})
    parsed = parse_traceparent(response.headers["traceparent"])
    assert parsed is not None
    trace_id, span_id, _sampled = parsed
    assert trace_id == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert span_id != "00f067aa0ba902b7"


def test_malformed_caller_header_still_yields_a_fresh_valid_trace():
    response = _client().get("/health", headers={"traceparent": "not-a-traceparent"})
    parsed = parse_traceparent(response.headers["traceparent"])
    assert parsed is not None
    assert parsed[0] != "4bf92f3577b34da6a3ce929d0e0e4736"


def test_error_responses_are_traced_too():
    """A 404 must be diagnosable — this is exactly when the id matters."""
    response = _client().get("/no-such-route")
    assert response.status_code == 404
    assert parse_traceparent(response.headers.get("traceparent")) is not None


def test_two_requests_get_different_traces():
    client = _client()
    first = client.get("/health").headers["traceparent"]
    second = client.get("/health").headers["traceparent"]
    assert first != second


def _crashing_client() -> TestClient:
    """An app with one route that raises, so the catch-all 500 handler runs."""
    application = create_app()

    @application.get("/__boom__")
    async def boom() -> None:
        raise RuntimeError("boom")

    return TestClient(application, raise_server_exceptions=False)


@contextmanager
def _captured_json_logs(logger_name: str) -> Iterator[list[dict[str, str]]]:
    """Attach a JsonFormatter handler; the yielded list is filled with the parsed
    records on exit. Asserting on the real formatter's output is the point: the
    trace fields come from the ContextVar it reads, not from the record itself."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger(logger_name)
    logger.addHandler(handler)
    previous_level, previous_disabled = logger.level, logger.disabled
    logger.setLevel(logging.ERROR)
    # Alembic's fileConfig() disables every logger it does not name; integration
    # tests run it in-process, so this logger may arrive here already disabled.
    logger.disabled = False
    records: list[dict[str, str]] = []
    try:
        yield records
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
        logger.disabled = previous_disabled
        records.extend(json.loads(line) for line in stream.getvalue().splitlines() if line)


def test_unhandled_500_still_carries_a_traceparent():
    """Starlette hoists the catch-all Exception handler into ServerErrorMiddleware,
    outside TraceContextMiddleware — so the ContextVar is already reset when it runs.
    The scope-state fallback must keep the 500 (the one response that most needs a
    trace id) correlatable."""
    response = _crashing_client().get("/__boom__")
    assert response.status_code == 500
    assert parse_traceparent(response.headers.get("traceparent")) is not None


def test_unhandled_500_log_line_carries_the_same_trace_id():
    with _captured_json_logs("app.core.exceptions") as records:
        response = _crashing_client().get("/__boom__", headers={"traceparent": CALLER})

    assert response.headers["traceparent"].startswith("00-4bf92f3577b34da6a3ce929d0e0e4736-")
    logged = [r for r in records if r["message"].startswith("Unhandled exception")]
    assert logged, records
    assert logged[0]["trace_id"] == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert logged[0]["route"] == "/__boom__"


def test_claimed_clan_id_is_truncated_before_it_reaches_the_logs():
    """X-Current-Clan-Id is attacker-controlled and unbounded, and lands verbatim in
    every log line of the request. Nothing authorizes off it, but it must not be a
    log-volume amplifier."""
    with _captured_json_logs("app.core.exceptions") as records:
        _crashing_client().get("/__boom__", headers={"X-Current-Clan-Id": "A" * 500})

    logged = [r for r in records if r["message"].startswith("Unhandled exception")]
    assert logged, records
    assert logged[0]["clan_id"] == "A" * 64


def test_cors_exposes_traceparent_to_browsers():
    """Without this the header exists but JS cannot read it, so the web client
    could never show the user a trace id."""
    response = _client().get("/health", headers={"Origin": "http://localhost:3000"})
    exposed = response.headers.get("access-control-expose-headers", "")
    assert "traceparent" in exposed.lower()
