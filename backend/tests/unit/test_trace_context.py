"""W3C trace-context parsing and generation.

A malformed inbound header must never fail a request — it is treated as absent
and a fresh trace starts, because a buggy client must not be able to 400 itself
out of the API.
"""

from app.core.trace_context import (
    TraceContext,
    get_trace_context,
    new_trace_context,
    parse_traceparent,
    reset_trace_context,
    set_trace_context,
)

VALID = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"


def test_parses_a_well_formed_header():
    assert parse_traceparent(VALID) == (
        "4bf92f3577b34da6a3ce929d0e0e4736",
        "00f067aa0ba902b7",
        True,
    )


def test_unsampled_flag_is_reported():
    header = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-00"
    assert parse_traceparent(header) == (
        "4bf92f3577b34da6a3ce929d0e0e4736",
        "00f067aa0ba902b7",
        False,
    )


def test_uppercase_and_surrounding_whitespace_are_tolerated():
    assert parse_traceparent(f"  {VALID.upper()}  ") is not None


def test_missing_or_malformed_headers_are_treated_as_absent():
    for header in (
        None,
        "",
        "garbage",
        "01-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",  # unsupported version
        "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7",  # too few fields
        "00-tooshort-00f067aa0ba902b7-01",
        "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01-extra",
    ):
        assert parse_traceparent(header) is None, header


def test_all_zero_ids_are_invalid_per_spec():
    assert parse_traceparent("00-" + "0" * 32 + "-00f067aa0ba902b7-01") is None
    assert parse_traceparent("00-4bf92f3577b34da6a3ce929d0e0e4736-" + "0" * 16 + "-01") is None


def test_new_context_without_a_header_starts_a_fresh_trace():
    ctx = new_trace_context(None)
    assert len(ctx.trace_id) == 32
    assert len(ctx.span_id) == 16
    assert ctx.parent_span_id is None
    assert ctx.sampled is True


def test_new_context_continues_the_callers_trace_with_its_own_span():
    ctx = new_trace_context(VALID)
    assert ctx.trace_id == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert ctx.parent_span_id == "00f067aa0ba902b7"
    assert ctx.span_id != "00f067aa0ba902b7"


def test_two_fresh_contexts_do_not_share_ids():
    assert new_trace_context(None).trace_id != new_trace_context(None).trace_id


def test_route_and_clan_are_carried():
    ctx = new_trace_context(None, route="/api/v1/persons", clan_id="clan-1")
    assert ctx.route == "/api/v1/persons"
    assert ctx.clan_id == "clan-1"


def test_to_traceparent_round_trips():
    ctx = new_trace_context(VALID)
    assert parse_traceparent(ctx.to_traceparent()) == (ctx.trace_id, ctx.span_id, True)


def test_unsampled_context_serializes_with_00_flags():
    ctx = TraceContext(
        trace_id="4bf92f3577b34da6a3ce929d0e0e4736",
        span_id="00f067aa0ba902b7",
        parent_span_id=None,
        sampled=False,
    )
    assert ctx.to_traceparent().endswith("-00")


def test_context_var_is_empty_by_default():
    assert get_trace_context() is None


def test_context_var_sets_and_resets():
    ctx = new_trace_context(None)
    token = set_trace_context(ctx)
    try:
        assert get_trace_context() is ctx
    finally:
        reset_trace_context(token)
    assert get_trace_context() is None
