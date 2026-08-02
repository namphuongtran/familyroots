"""Every response carries a traceparent, and a caller's trace id survives.

Uses /health because it is the only route that needs no auth; it does touch the
DB, so a 200 or a 503 are both acceptable — the assertion is about headers, not
the body.
"""

from fastapi.testclient import TestClient

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


def test_cors_exposes_traceparent_to_browsers():
    """Without this the header exists but JS cannot read it, so the web client
    could never show the user a trace id."""
    response = _client().get("/health", headers={"Origin": "http://localhost:3000"})
    exposed = response.headers.get("access-control-expose-headers", "")
    assert "traceparent" in exposed.lower()
