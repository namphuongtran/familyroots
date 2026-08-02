"""W3C Trace Context (https://www.w3.org/TR/trace-context/) for log correlation.

Every request carries a trace id shared with the client that started it, so one
user action can be followed from the browser through Sentry into the API's JSON
logs. Deliberately separate from ``app/core/request_meta.py``: that one captures
transport metadata destined for audit *rows*, this one is diagnostic and lives
only in logs and headers.

Outside a request (scheduler, purge jobs) the ContextVar is None and log lines
simply carry no trace fields — the correct semantics for system-initiated work.
"""

from __future__ import annotations

import re
import secrets
from contextvars import ContextVar
from dataclasses import dataclass

_TRACEPARENT_RE = re.compile(r"^00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$")
_INVALID_TRACE_ID = "0" * 32
_INVALID_SPAN_ID = "0" * 16
_SAMPLED_FLAG = 0x01


@dataclass(frozen=True)
class TraceContext:
    """One server-side span within a (possibly client-initiated) trace."""

    trace_id: str
    span_id: str
    parent_span_id: str | None
    sampled: bool
    route: str | None = None
    clan_id: str | None = None

    def to_traceparent(self) -> str:
        return f"00-{self.trace_id}-{self.span_id}-{'01' if self.sampled else '00'}"


def parse_traceparent(header: str | None) -> tuple[str, str, bool] | None:
    """Return ``(trace_id, parent_span_id, sampled)``, or None when absent/malformed.

    Malformed input is treated as absent rather than rejected: a broken header
    from a client must not be able to fail the request.
    """
    if not header:
        return None
    match = _TRACEPARENT_RE.match(header.strip().lower())
    if match is None:
        return None
    trace_id, parent_span_id, flags = match.groups()
    if trace_id == _INVALID_TRACE_ID or parent_span_id == _INVALID_SPAN_ID:
        return None
    return trace_id, parent_span_id, bool(int(flags, 16) & _SAMPLED_FLAG)


def new_trace_context(
    header: str | None,
    *,
    route: str | None = None,
    clan_id: str | None = None,
) -> TraceContext:
    """Continue the caller's trace when the header is usable, else start a new one."""
    parsed = parse_traceparent(header)
    if parsed is None:
        return TraceContext(
            trace_id=secrets.token_hex(16),
            span_id=secrets.token_hex(8),
            parent_span_id=None,
            sampled=True,
            route=route,
            clan_id=clan_id,
        )
    trace_id, parent_span_id, sampled = parsed
    return TraceContext(
        trace_id=trace_id,
        span_id=secrets.token_hex(8),
        parent_span_id=parent_span_id,
        sampled=sampled,
        route=route,
        clan_id=clan_id,
    )


_trace_context: ContextVar[TraceContext | None] = ContextVar("trace_context", default=None)


def set_trace_context(ctx: TraceContext) -> object:
    return _trace_context.set(ctx)


def get_trace_context() -> TraceContext | None:
    return _trace_context.get()


def reset_trace_context(token: object) -> None:
    _trace_context.reset(token)  # type: ignore[arg-type]
