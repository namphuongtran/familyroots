# ADR-033: W3C Trace Context for Correlation, Exported Through Sentry

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
  `route` is the **raw request path** including ids (`/api/v1/persons/<uuid>`), not a
  route template — the field name is kept for continuity, but do not group on it as if
  it were low-cardinality. `clan_id` records the **claimed** `X-Current-Clan-Id` header,
  not an authorized clan: it is unvalidated at this layer (authorization happens later,
  in the repository/permission layer), so treat it as a caller-supplied hint and expect
  values that the caller had no right to. It is truncated to 64 characters so an
  oversized header cannot amplify log volume across every line of a request.
- An unhandled 500 is a special case: Starlette hoists the catch-all `Exception`
  handler into `ServerErrorMiddleware`, outside all user middleware and therefore
  outside the ContextVar's lifetime. The middleware also stashes the context on the
  request scope's `state`, and `unhandled_exception_handler` reads it back so the 500
  still logs a `trace_id` and still returns a `traceparent`.
- The response echoes `traceparent`, and CORS exposes it so the browser can show the
  user a trace id to quote to an admin — **except on an unhandled 500**: Starlette's
  `ServerErrorMiddleware` sits outside `CORSMiddleware` (see above), so the response it
  sends bypasses CORS's header-injecting wrapper entirely. The `traceparent` header is
  still present on that response (`unhandled_exception_handler` sets it from the
  stashed context), but with no `access-control-expose-headers`, so a browser cannot
  read it via JS. This is pre-existing Starlette structure, not something this ADR's
  implementation changed. In that case the trace id still reaches the backend log line
  and the tagged Sentry event, which is how a 500 gets correlated in practice — the
  browser-readable path is for handled error responses, not this one.
- Sentry continues to do its own distributed tracing via the FastAPI integration and
  the `sentry-trace` / `baggage` headers the web SDK sends. We additionally tag Sentry
  events with `trace_id`, which is the pivot from a Sentry issue to log search.
- RED metrics are exposed at `GET /internal/metrics`, disabled by default and guarded
  by `X-Metrics-Token`; failures return 404 per ADR-021. The endpoint is
  envelope-exempt — Prometheus `text/plain` exposition, not `{"data": ...}` — like
  `GET /health` and `GET /exports/clan` (`docs/contracts/README.md`).

## Consequences
- A user-visible error can be traced to an exact log line without reproducing it.
- No new infrastructure to operate; trace storage is Sentry's problem.
- Because the id on the wire is the W3C standard, moving to an OpenTelemetry collector
  later is an exporter change, not a code change.
- Trace ids appear in logs only. The response envelope is unchanged, so this is not a
  breaking contract change.
- `/internal/metrics` has no scraper yet. It is preparation; dashboards remain in
  Sentry until one exists.
- **Cost: this ADR forced a major-version bump of the ASGI layer.**
  `prometheus-fastapi-instrumentator` 8.1.0 (added for the RED metrics above)
  requires `starlette>=1.0.0,<2.0.0`, moving starlette from 0.52.1 to 1.3.1 — a major
  version, pulled in by a metrics library, not chosen directly. FastAPI 0.135.1
  declares only `starlette>=0.46.0` with no upper bound, so nothing prevented it.
  Accepted rather than pinned back: the product is pre-release, so this is the
  cheapest point in its life to absorb a major ASGI bump. `starlette>=1.3.1,<2` is
  now an explicit direct dependency in `pyproject.toml` so the major line is a
  visible decision in a diff, not a transitive accident buried in `uv.lock`.
- **Open follow-up:** starlette 1.x emits
  `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated;
  install httpx2 instead` on every `TestClient` use, so the test suite's output is no
  longer warning-free. Not fixed here — triaged separately.

## Related
- ADR-021 (non-enumerating auth surfaces) — why the metrics endpoint 404s
- Spec: `docs/superpowers/specs/2026-08-02-web-architecture-observability-design.md`
