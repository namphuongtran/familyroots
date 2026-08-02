"""Log records must serialize to valid JSON even with quotes/newlines."""

import json
import logging

from app.core.logging import JsonFormatter
from app.core.trace_context import (
    TraceContext,
    reset_trace_context,
    set_trace_context,
)


def _record(msg: str) -> logging.LogRecord:
    return logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=(),
        exc_info=None,
    )


def test_message_with_quotes_is_valid_json():
    out = JsonFormatter().format(_record('he said "hi"\nthen left'))
    parsed = json.loads(out)  # must not raise
    assert parsed["message"] == 'he said "hi"\nthen left'
    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "test.logger"
    assert "time" in parsed


def test_no_trace_fields_outside_a_request():
    """Scheduler and purge jobs have no trace — the keys must be absent, not null."""
    parsed = json.loads(JsonFormatter().format(_record("scheduled job ran")))
    assert "trace_id" not in parsed
    assert "span_id" not in parsed


def test_trace_fields_are_added_inside_a_request():
    ctx = TraceContext(
        trace_id="4bf92f3577b34da6a3ce929d0e0e4736",
        span_id="00f067aa0ba902b7",
        parent_span_id=None,
        sampled=True,
        route="/api/v1/persons",
        clan_id="clan-1",
    )
    token = set_trace_context(ctx)
    try:
        parsed = json.loads(JsonFormatter().format(_record("listing persons")))
    finally:
        reset_trace_context(token)

    assert parsed["trace_id"] == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert parsed["span_id"] == "00f067aa0ba902b7"
    assert parsed["route"] == "/api/v1/persons"
    assert parsed["clan_id"] == "clan-1"


def test_optional_route_and_clan_are_omitted_when_unknown():
    ctx = TraceContext(
        trace_id="4bf92f3577b34da6a3ce929d0e0e4736",
        span_id="00f067aa0ba902b7",
        parent_span_id=None,
        sampled=True,
    )
    token = set_trace_context(ctx)
    try:
        parsed = json.loads(JsonFormatter().format(_record("no clan selected")))
    finally:
        reset_trace_context(token)

    assert parsed["trace_id"] == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert "route" not in parsed
    assert "clan_id" not in parsed
