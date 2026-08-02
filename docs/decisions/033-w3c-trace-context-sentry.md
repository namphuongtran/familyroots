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
- ADR-024 (non-canonical envelope exceptions) — `/internal/metrics` joins that list
- Spec: `docs/superpowers/specs/2026-08-02-web-architecture-observability-design.md`
