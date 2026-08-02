# Backend Trace Context + Metrics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every API request a W3C trace id that appears in its JSON logs, on the response, and as a Sentry tag — plus an opt-in Prometheus endpoint — so a user-reported problem can be traced from the browser to the exact backend log line.

**Architecture:** A new `TraceContextMiddleware` continues the caller's `traceparent` header or starts a fresh trace, stores it in a `ContextVar` (the same pattern `app/core/request_meta.py` already uses for audit data), and echoes it on the response. `JsonFormatter` reads that ContextVar so no call site has to pass a trace id around. Sentry keeps its own native distributed tracing via the FastAPI integration; we only tag its events with our trace id so you can pivot from a Sentry issue to logs. Metrics come from `prometheus-fastapi-instrumentator` writing into an app-owned registry, served behind a token-guarded route that 404s when disabled.

**Tech Stack:** Python 3.14, FastAPI, Starlette `BaseHTTPMiddleware`, `contextvars`, `sentry-sdk[fastapi]`, `prometheus-fastapi-instrumentator`, pytest, uv.

## Global Constraints

- Python `>=3.14`; ruff `line-length = 100`, target `py314`, rules `A,E,W,F,I,B,C4,UP,SIM,PTH,RUF`.
- mypy runs in `strict` mode over `app/` and `tests/`. Every function in `app/` needs full annotations. `tests.*` is exempt from `disallow_untyped_defs`.
- Domain layer stays framework-agnostic — none of this work touches `app/domain/`.
- Public API response envelope must not change: every 2xx JSON body stays `{"data": ...}` and every non-2xx stays `{"error": {"code", "message", "detail"}}`. Trace ids travel in a **response header only**.
- The full gate must pass before any task is considered done:
  `cd backend && uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports`
- Verify lint with plain `ruff check` — the output must read `All checks passed!`. `ruff check --fix` printing "No fixes available" is **not** a pass.
- Middleware execution order (outermost → innermost) must end up:
  `TrustedHost → CORS → TraceContext → Language → RequestMeta → Sentry → RateLimit`.
  Starlette wraps the **last-added middleware outermost**, so `add_middleware` calls appear in reverse of that order in `create_app()`.
- Commit messages end with:
  ```
  Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01U2cTqEcXrcJYo3qkKSUheT
  ```

---

## File Structure

| File | Responsibility |
|---|---|
| `backend/app/core/trace_context.py` (create) | `TraceContext` dataclass, `traceparent` parsing/generation, ContextVar accessors. Pure — no FastAPI import |
| `backend/app/middleware/trace_middleware.py` (create) | Starlette middleware: populate the ContextVar per request, echo `traceparent` on the response |
| `backend/app/core/logging.py` (modify) | `JsonFormatter` adds `trace_id` / `span_id` / `route` / `clan_id` when a trace context exists |
| `backend/app/middleware/sentry_middleware.py` (modify) | Tag Sentry scope with `trace_id` |
| `backend/app/core/config.py` (modify) | `METRICS_ENABLED`, `METRICS_TOKEN` + validation |
| `backend/app/main.py` (modify) | Register the middleware, expose `traceparent` through CORS, instrument metrics, mount `/internal/metrics` |
| `backend/pyproject.toml` (modify) | Add `prometheus-fastapi-instrumentator` |
| `backend/tests/unit/test_trace_context.py` (create) | Parsing, generation, ContextVar |
| `backend/tests/unit/test_logging_formatter.py` (modify) | Trace fields present / absent |
| `backend/tests/unit/test_trace_middleware.py` (create) | Header continuation, echo, malformed input, error responses |
| `backend/tests/unit/test_sentry_trace_tag.py` (create) | Sentry scope tagging |
| `backend/tests/unit/test_metrics_endpoint.py` (create) | 404 when disabled/unauthenticated, 200 with the token |
| `backend/tests/unit/test_config_validation.py` (modify) | Metrics token required when metrics are enabled |
| `docs/decisions/033-w3c-trace-context-sentry.md` (create) | ADR |
| `docs/decisions/README.md`, `docs/contracts/README.md`, `docs/sad/08-crosscutting-concepts.md`, `backend/CLAUDE.md` (modify) | Doc sync |

---

### Task 1: Trace context module

**Files:**
- Create: `backend/app/core/trace_context.py`
- Test: `backend/tests/unit/test_trace_context.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `TraceContext(trace_id: str, span_id: str, parent_span_id: str | None, sampled: bool, route: str | None = None, clan_id: str | None = None)`, frozen dataclass, method `to_traceparent() -> str`
  - `parse_traceparent(header: str | None) -> tuple[str, str, bool] | None` → `(trace_id, parent_span_id, sampled)`
  - `new_trace_context(header: str | None, *, route: str | None = None, clan_id: str | None = None) -> TraceContext`
  - `set_trace_context(ctx: TraceContext) -> object`, `get_trace_context() -> TraceContext | None`, `reset_trace_context(token: object) -> None`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_trace_context.py`:

```python
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
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `cd backend && uv run pytest tests/unit/test_trace_context.py -q`
Expected: collection error — `ModuleNotFoundError: No module named 'app.core.trace_context'`

- [ ] **Step 3: Write the implementation**

Create `backend/app/core/trace_context.py`:

```python
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
```

- [ ] **Step 4: Run the test and confirm it passes**

Run: `cd backend && uv run pytest tests/unit/test_trace_context.py -q`
Expected: 13 passed

- [ ] **Step 5: Run the gate**

Run: `cd backend && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/`
Expected: `All checks passed!`, format check clean, mypy `Success`

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/trace_context.py backend/tests/unit/test_trace_context.py
git commit -m "$(cat <<'EOF'
feat(obs): add W3C trace-context module

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01U2cTqEcXrcJYo3qkKSUheT
EOF
)"
```

---

### Task 2: Trace fields in JSON logs

**Files:**
- Modify: `backend/app/core/logging.py:10-23` (`JsonFormatter.format`)
- Test: `backend/tests/unit/test_logging_formatter.py` (append)

**Interfaces:**
- Consumes: `get_trace_context()` from Task 1
- Produces: log lines gain optional keys `trace_id`, `span_id`, `route`, `clan_id`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/unit/test_logging_formatter.py`:

```python
from app.core.trace_context import (
    TraceContext,
    reset_trace_context,
    set_trace_context,
)


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
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `cd backend && uv run pytest tests/unit/test_logging_formatter.py -q`
Expected: FAIL — `KeyError: 'trace_id'`

- [ ] **Step 3: Write the implementation**

In `backend/app/core/logging.py`, add the import below the existing `from app.core.config import settings`:

```python
from app.core.trace_context import get_trace_context
```

Replace the body of `JsonFormatter.format` with:

```python
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Correlation fields, present only inside a request. Absent (not null) for
        # scheduler/purge work so a log query for trace_id never matches system jobs.
        ctx = get_trace_context()
        if ctx is not None:
            payload["trace_id"] = ctx.trace_id
            payload["span_id"] = ctx.span_id
            if ctx.route is not None:
                payload["route"] = ctx.route
            if ctx.clan_id is not None:
                payload["clan_id"] = ctx.clan_id
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)
```

- [ ] **Step 4: Run the test and confirm it passes**

Run: `cd backend && uv run pytest tests/unit/test_logging_formatter.py -q`
Expected: 4 passed

- [ ] **Step 5: Run the gate**

Run: `cd backend && uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/`
Expected: all green

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/logging.py backend/tests/unit/test_logging_formatter.py
git commit -m "$(cat <<'EOF'
feat(obs): emit trace_id/span_id/route/clan_id in JSON logs

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01U2cTqEcXrcJYo3qkKSUheT
EOF
)"
```

---

### Task 3: Trace-context middleware, wired and exposed

**Files:**
- Create: `backend/app/middleware/trace_middleware.py`
- Modify: `backend/app/main.py` (import block; `create_app()` middleware section around lines 200-218)
- Test: `backend/tests/unit/test_trace_middleware.py`

**Interfaces:**
- Consumes: `new_trace_context`, `set_trace_context`, `reset_trace_context` (Task 1)
- Produces: `TraceContextMiddleware` (Starlette `BaseHTTPMiddleware` subclass, no constructor args); every response carries a `traceparent` header; CORS exposes it to browsers

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_trace_middleware.py`:

```python
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
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `cd backend && uv run pytest tests/unit/test_trace_middleware.py -q`
Expected: FAIL — `KeyError: 'traceparent'` / `assert None is not None`

- [ ] **Step 3: Write the middleware**

Create `backend/app/middleware/trace_middleware.py`:

```python
"""Trace-context middleware — one correlation id per request, shared with clients.

Registered outside LanguageMiddleware (and therefore outside RequestMeta, Sentry
and RateLimit) so that every log line produced while handling a request carries
the trace id — including the localized 429 the rate limiter builds.
"""

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.trace_context import (
    new_trace_context,
    reset_trace_context,
    set_trace_context,
)


class TraceContextMiddleware(BaseHTTPMiddleware):
    """Continue the caller's W3C trace or start a new one; echo it on the response."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        ctx = new_trace_context(
            request.headers.get("traceparent"),
            route=request.url.path,
            clan_id=request.headers.get("X-Current-Clan-Id"),
        )
        token = set_trace_context(ctx)
        try:
            response = await call_next(request)
            response.headers["traceparent"] = ctx.to_traceparent()
            return response
        finally:
            reset_trace_context(token)
```

- [ ] **Step 4: Wire it into the app**

In `backend/app/main.py`, add to the import block next to the other middleware imports:

```python
from app.middleware.trace_middleware import TraceContextMiddleware
```

In `create_app()`, update the ordering comment and insert the registration. The block currently reads `...LanguageMiddleware) / add_middleware(CORSMiddleware, ...)`; change the desired-order comment line to:

```python
    #   - TrustedHost rejects a bad Host header before anything else runs;
    #   - CORS wraps the rate limiter, so even a 429 carries CORS headers;
    #   - TraceContext sits directly inside CORS so every log line emitted during the
    #     request — including the rate limiter's localized 429 — carries the trace id;
    #   - Language sets the locale before RateLimit builds its (localized) 429 envelope;
```

and change the desired execution order sentence in that same comment to:

```python
    # innermost). Desired (outermost → innermost): TrustedHost → CORS → TraceContext →
    # Language → RequestMeta → Sentry → RateLimit. This means:
```

Then add the middleware between `LanguageMiddleware` and `CORSMiddleware`, and expose the header:

```python
    application.add_middleware(LanguageMiddleware)
    application.add_middleware(TraceContextMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        # Browsers hide non-safelisted response headers from JS unless named here.
        expose_headers=["traceparent"],
    )
```

- [ ] **Step 5: Run the test and confirm it passes**

Run: `cd backend && uv run pytest tests/unit/test_trace_middleware.py -q`
Expected: 6 passed

- [ ] **Step 6: Run the gate**

Run: `cd backend && uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports`
Expected: all green

- [ ] **Step 7: Commit**

```bash
git add backend/app/middleware/trace_middleware.py backend/app/main.py backend/tests/unit/test_trace_middleware.py
git commit -m "$(cat <<'EOF'
feat(obs): trace-context middleware, echo traceparent, expose via CORS

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01U2cTqEcXrcJYo3qkKSUheT
EOF
)"
```

---

### Task 4: Tag Sentry events with the trace id

Sentry keeps doing its own distributed tracing through the FastAPI integration and the `sentry-trace` / `baggage` headers the web SDK sends. This task only adds the pivot: a Sentry issue shows the W3C `trace_id`, which you paste into a log query.

**Files:**
- Modify: `backend/app/middleware/sentry_middleware.py`
- Test: `backend/tests/unit/test_sentry_trace_tag.py`

**Interfaces:**
- Consumes: `get_trace_context()` (Task 1); `TraceContextMiddleware` must be registered outside `SentryMiddleware` (Task 3) so the ContextVar is populated
- Produces: Sentry scope tag `trace_id`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_sentry_trace_tag.py`:

```python
"""SentryMiddleware tags events with the W3C trace id.

sentry_sdk.push_scope is monkeypatched with a recorder so the test asserts on
tags without needing a DSN, a transport, or network access.
"""

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware import sentry_middleware as sentry_module
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

    monkeypatch.setattr(sentry_module.sentry_sdk, "push_scope", _fake_push_scope)
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
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `cd backend && uv run pytest tests/unit/test_sentry_trace_tag.py -q`
Expected: FAIL — `KeyError: 'trace_id'`

- [ ] **Step 3: Write the implementation**

In `backend/app/middleware/sentry_middleware.py`, add the import:

```python
from app.core.trace_context import get_trace_context
```

and inside `dispatch`, immediately after `scope.set_tag("method", request.method)`:

```python
            # Pivot from a Sentry issue to the JSON log lines for the same request.
            # Populated by TraceContextMiddleware, which is registered outside this one.
            trace = get_trace_context()
            if trace is not None:
                scope.set_tag("trace_id", trace.trace_id)
```

- [ ] **Step 4: Run the test and confirm it passes**

Run: `cd backend && uv run pytest tests/unit/test_sentry_trace_tag.py -q`
Expected: 2 passed

- [ ] **Step 5: Run the gate**

Run: `cd backend && uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/`
Expected: all green

- [ ] **Step 6: Commit**

```bash
git add backend/app/middleware/sentry_middleware.py backend/tests/unit/test_sentry_trace_tag.py
git commit -m "$(cat <<'EOF'
feat(obs): tag Sentry events with the W3C trace id

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01U2cTqEcXrcJYo3qkKSUheT
EOF
)"
```

---

### Task 5: Opt-in Prometheus metrics endpoint

**Files:**
- Modify: `backend/pyproject.toml` (dependencies)
- Modify: `backend/app/core/config.py` (settings + validator)
- Modify: `backend/app/main.py` (`create_app()`)
- Test: `backend/tests/unit/test_metrics_endpoint.py`
- Test: `backend/tests/unit/test_config_validation.py` (append)

**Interfaces:**
- Consumes: nothing from earlier tasks
- Produces: `settings.METRICS_ENABLED: bool`, `settings.METRICS_TOKEN: str`; route `GET /internal/metrics`; `application.state.metrics_registry: CollectorRegistry`

**Design note:** the endpoint 404s — rather than 401s — when disabled or when the token is wrong. That matches ADR-021 (non-enumerating auth surfaces): an unauthenticated scan must not learn that a metrics endpoint exists here. Its 200 body is `text/plain` Prometheus exposition, so it joins `/health` and `GET /exports/clan` on the envelope-exempt list (documented in Task 6). Each app instance owns its own `CollectorRegistry` rather than the process-global default, so building several apps in one pytest session cannot raise `Duplicated timeseries`.

- [ ] **Step 1: Add the dependency**

In `backend/pyproject.toml`, add to `[project].dependencies` after the `sentry-sdk` entry:

```toml
    "prometheus-fastapi-instrumentator>=7.1.0",
```

Then run: `cd backend && uv sync`

- [ ] **Step 2: Write the failing test**

Create `backend/tests/unit/test_metrics_endpoint.py`:

```python
"""/internal/metrics is invisible unless explicitly enabled AND correctly tokened.

404 (not 401) on every failure path, per ADR-021: a scanner must not learn the
endpoint exists.
"""

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(), raise_server_exceptions=False)


def test_disabled_by_default(client: TestClient) -> None:
    assert client.get("/internal/metrics").status_code == 404


def test_enabled_without_a_token_header_is_404(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "METRICS_ENABLED", True)
    monkeypatch.setattr(settings, "METRICS_TOKEN", "s3cret")
    assert client.get("/internal/metrics").status_code == 404


def test_wrong_token_is_404(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "METRICS_ENABLED", True)
    monkeypatch.setattr(settings, "METRICS_TOKEN", "s3cret")
    response = client.get("/internal/metrics", headers={"X-Metrics-Token": "wrong"})
    assert response.status_code == 404


def test_correct_token_returns_prometheus_exposition(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "METRICS_ENABLED", True)
    monkeypatch.setattr(settings, "METRICS_TOKEN", "s3cret")
    client.get("/health")  # generate at least one sample
    response = client.get("/internal/metrics", headers={"X-Metrics-Token": "s3cret"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "http_request" in response.text


def test_metrics_route_is_hidden_from_openapi(client: TestClient) -> None:
    """The public schema is the client contract; an ops endpoint does not belong in it."""
    assert "/internal/metrics" not in client.get("/openapi.json").json()["paths"]
```

Append to `backend/tests/unit/test_config_validation.py`:

```python
def test_metrics_enabled_without_a_token_is_rejected():
    """Enabled-but-unprotected would publish request volumes and route names to
    anyone — reject it in every environment, not just production."""
    with pytest.raises(ValidationError):
        _build(APP_ENV="development", METRICS_ENABLED=True, METRICS_TOKEN="")


def test_metrics_enabled_with_a_token_is_accepted():
    s = _build(APP_ENV="development", METRICS_ENABLED=True, METRICS_TOKEN="s3cret")
    assert s.METRICS_ENABLED is True
```

- [ ] **Step 3: Run the tests and confirm they fail**

Run: `cd backend && uv run pytest tests/unit/test_metrics_endpoint.py tests/unit/test_config_validation.py -q`
Expected: FAIL — metrics route returns 404 for the token case too, and `Settings` rejects the unknown `METRICS_ENABLED` field

- [ ] **Step 4: Add the settings**

In `backend/app/core/config.py`, after the `SENTRY_DSN` line:

```python
    # Metrics — opt-in RED metrics for a Prometheus scraper. Off by default because
    # nothing scrapes it yet; the token keeps route names and request volumes from
    # being readable by anyone who finds the path.
    METRICS_ENABLED: bool = False
    METRICS_TOKEN: str = ""
```

Inside `_enforce_production_safety`, **before** the `if self.APP_ENV == "production":` block (this rule applies in every environment):

```python
        if self.METRICS_ENABLED and not self.METRICS_TOKEN:
            raise ValueError("METRICS_TOKEN must be set when METRICS_ENABLED is true")
```

- [ ] **Step 5: Instrument the app and mount the route**

In `backend/app/main.py`, **extend the existing import lines** rather than adding duplicates — ruff's `I` rules fail on a second import from the same module:

- change `from fastapi import Depends, FastAPI` to `from fastapi import Depends, FastAPI, Request`
- change `from fastapi.responses import JSONResponse` to `from fastapi.responses import JSONResponse, Response`

then add these new imports:

```python
import secrets as _secrets

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest
from prometheus_fastapi_instrumentator import Instrumentator
```

`prometheus_fastapi_instrumentator` ships no type stubs, so mypy strict will fail on the import. Add it to the existing `ignore_missing_imports` override in `backend/pyproject.toml` — the block whose `module` list already holds `"sentry_sdk"`, `"firebase_admin.*"`, `"supabase.*"`, `"jose.*"`, `"apscheduler.*"`:

```toml
    "prometheus_fastapi_instrumentator",
```

In `create_app()`, directly after `application.include_router(api_v1_router, prefix="/api/v1")`:

```python
    # RED metrics into an app-owned registry (not the process-global default) so
    # building several apps in one test session cannot raise Duplicated timeseries.
    metrics_registry = CollectorRegistry()
    application.state.metrics_registry = metrics_registry
    Instrumentator(
        registry=metrics_registry,
        excluded_handlers=["/health", "/internal/metrics"],
    ).instrument(application)

    @application.get("/internal/metrics", include_in_schema=False)
    async def internal_metrics(request: Request) -> Response:
        """Prometheus exposition. 404 — never 401 — on every failure path so an
        unauthenticated scan cannot confirm the endpoint exists (ADR-021).

        Envelope-exempt like /health: the body is text/plain exposition format.
        """
        token = request.headers.get("X-Metrics-Token")
        if (
            not settings.METRICS_ENABLED
            or not settings.METRICS_TOKEN
            or token is None
            or not _secrets.compare_digest(token, settings.METRICS_TOKEN)
        ):
            raise StarletteHTTPException(status_code=404)
        return Response(
            generate_latest(request.app.state.metrics_registry),
            media_type=CONTENT_TYPE_LATEST,
        )
```

- [ ] **Step 6: Run the tests and confirm they pass**

Run: `cd backend && uv run pytest tests/unit/test_metrics_endpoint.py tests/unit/test_config_validation.py -q`
Expected: all passed

- [ ] **Step 7: Run the gate**

Run: `cd backend && uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports`
Expected: all green

- [ ] **Step 8: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock backend/app/core/config.py backend/app/main.py backend/tests/unit/test_metrics_endpoint.py backend/tests/unit/test_config_validation.py
git commit -m "$(cat <<'EOF'
feat(obs): opt-in token-guarded Prometheus metrics at /internal/metrics

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01U2cTqEcXrcJYo3qkKSUheT
EOF
)"
```

---

### Task 6: ADR and documentation sync

**Files:**
- Create: `docs/decisions/033-w3c-trace-context-sentry.md`
- Modify: `docs/decisions/README.md` (ADR index)
- Modify: `docs/contracts/README.md` (envelope-exemption list)
- Modify: `docs/sad/08-crosscutting-concepts.md` (observability)
- Modify: `backend/CLAUDE.md` (commands/architecture notes)

**Interfaces:**
- Consumes: everything from Tasks 1-5
- Produces: no code

- [ ] **Step 1: Write the ADR**

Create `docs/decisions/033-w3c-trace-context-sentry.md`:

```markdown
# ADR-033: W3C trace context for correlation, exported through Sentry

## Status
Accepted — 2026-08-02

## Context
Backend logs were structured JSON but carried no request identity, so a member's
report ("it failed when I opened the tree") could not be tied to a log line. The
web client had no logging, error tracking or tracing at all. Debugging depended
on reproducing the problem.

Three options were considered:
1. A bare `X-Request-Id` — cheapest, but yields no timing breakdown inside a request
   and is a non-standard id that no tooling understands.
2. Full OpenTelemetry with a self-hosted collector (Tempo/Jaeger) plus Prometheus and
   Grafana — the most capable and vendor-neutral, but it means running and paying for
   trace storage, which this team does not have capacity for.
3. Standard W3C trace context on the wire, exported through Sentry, which is already
   a dependency on backend and mobile.

## Decision
Adopt **W3C Trace Context** (`traceparent`) as the correlation identifier.

- `TraceContextMiddleware` continues an inbound `traceparent` or starts a new trace,
  and stores it in a ContextVar (`app/core/trace_context.py`).
- Every JSON log line inside a request carries `trace_id`, `span_id`, and where known
  `route` and `clan_id`. Outside a request (scheduler, purge) those keys are absent.
- The response echoes `traceparent`, and CORS exposes it so the browser can show the
  user a trace id to quote to an admin.
- Sentry continues to do its own distributed tracing via the FastAPI integration and
  the `sentry-trace` / `baggage` headers the web SDK sends. We additionally tag Sentry
  events with `trace_id`, which is the pivot from a Sentry issue to log search.
- RED metrics are exposed at `GET /internal/metrics`, disabled by default and guarded
  by `X-Metrics-Token`; failures return 404 per ADR-021.

## Consequences
- A user-visible error can be traced to an exact log line without reproducing it.
- No new infrastructure to operate; trace storage is Sentry's problem.
- Because the id on the wire is the W3C standard, moving to an OpenTelemetry collector
  later is an exporter change, not a code change.
- Trace ids appear in logs only. The response envelope is unchanged, so this is not a
  breaking contract change.
- `/internal/metrics` has no scraper yet. It is preparation; dashboards remain in
  Sentry until one exists.

## Related
- ADR-021 (non-enumerating auth surfaces) — why the metrics endpoint 404s
- ADR-024 (non-canonical envelope exceptions) — `/internal/metrics` joins that list
- Spec: `docs/superpowers/specs/2026-08-02-web-architecture-observability-design.md`
```

- [ ] **Step 2: Add the ADR to the index**

In `docs/decisions/README.md`, append a row to the ADR table matching the existing format, referencing `033-w3c-trace-context-sentry.md` with the title "W3C trace context for correlation, exported through Sentry" and status Accepted.

- [ ] **Step 3: Record the envelope exemption**

In `docs/contracts/README.md`, in the bullet list that already exempts `GET /health` and `GET /exports/clan`, add:

```markdown
- **`GET /internal/metrics` is exempt** — Prometheus exposition (`text/plain`), not a
  data endpoint. Disabled by default; returns 404 unless enabled and correctly
  tokened (ADR-033).
```

- [ ] **Step 4: Document the crosscutting concern**

In `docs/sad/08-crosscutting-concepts.md`, add an "Observability" section stating: correlation id is W3C `traceparent`, continued or generated by `TraceContextMiddleware`; log fields `trace_id`/`span_id`/`route`/`clan_id`; `traceparent` echoed on responses and exposed via CORS; Sentry tagged with `trace_id`; metrics at `/internal/metrics`, opt-in and token-guarded. Reference ADR-033.

- [ ] **Step 5: Update backend/CLAUDE.md**

Add to `backend/CLAUDE.md`, in the section describing middleware/crosscutting concerns: the new middleware, its position in the ordering chain (`TrustedHost → CORS → TraceContext → Language → RequestMeta → Sentry → RateLimit`), the new `METRICS_ENABLED` / `METRICS_TOKEN` env vars, and a note that log lines gain trace fields only inside a request.

- [ ] **Step 6: Verify the docs match the code**

Run: `cd backend && uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports`
Expected: all green

Then re-read the ordering comment in `app/main.py:190-210` and confirm it says the same thing as the ADR and `backend/CLAUDE.md`. Where code and docs disagree, the code wins — fix the doc.

- [ ] **Step 7: Commit**

```bash
git add docs/decisions/033-w3c-trace-context-sentry.md docs/decisions/README.md docs/contracts/README.md docs/sad/08-crosscutting-concepts.md backend/CLAUDE.md
git commit -m "$(cat <<'EOF'
docs(obs): ADR-033 W3C trace context, envelope exemption, SAD sync

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01U2cTqEcXrcJYo3qkKSUheT
EOF
)"
```

---

## Done when

- `GET /health` returns a `traceparent` header; sending one in continues its trace id.
- A log line emitted during a request contains `trace_id`; one emitted by the scheduler does not.
- A Sentry event carries a `trace_id` tag matching the response header.
- `/internal/metrics` returns 404 by default and Prometheus exposition with the right token.
- ADR-033 exists, is indexed, and `docs/contracts/README.md` lists the new envelope exemption.
- Full gate green: `uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports`
