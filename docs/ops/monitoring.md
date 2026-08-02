# Monitoring

## Overview
Error/performance monitoring via Sentry; liveness via the `/health` endpoint;
opt-in Prometheus RED metrics at `/internal/metrics`; request correlation via the
W3C `traceparent` header (ADR-033).

## Sentry (as wired in `app/main.py` + `app/core/config.py`)
- Initialized **only when `SENTRY_DSN` is set** (`main.py` lifespan) — local/test runs
  with no DSN emit nothing.
- `environment = APP_ENV`.
- `traces_sample_rate = 0.1` in production, `1.0` otherwise.
- Uses `sentry-sdk[fastapi]` (see `pyproject.toml`); a `SentryMiddleware` is added when
  the DSN is set. Org/project are in `infra/sentry/sentry.properties`.
- Server-side exceptions are logged via `unhandled_exception_handler` and returned to
  clients as a generic `internal_error` envelope — **tracebacks/messages never leak to
  clients** (asserted by `tests/unit/test_exception_envelope.py`).

## Health check
- `GET /health` runs `SELECT 1` and checks Alembic migration status; the healthy
  payload is `{"status":"ok","database":"connected","migrations":"current"}`.
- Returns a 503 `degraded` response when the DB is unreachable
  (`{"status":"degraded","database":"unreachable"}`) **or** when migrations are
  not at head (the `migrations` field reports the mismatch). Render uses it as
  the `healthCheckPath`.

## Metrics — `GET /internal/metrics` (ADR-033)
Prometheus RED metrics (`http_requests_total`, `http_request_duration_seconds`, …) for
the whole ASGI stack. **Disabled by default**; there is no scraper deployed yet.

- **Enable it** with two envs (`app/core/config.py`, documented in `.env.example`):

  ```bash
  METRICS_ENABLED=true
  METRICS_TOKEN=$(openssl rand -hex 32)   # required when enabled — boot fails if empty
  ```

- **Scrape it** by sending the token in the `X-Metrics-Token` header:

  ```bash
  curl -H "X-Metrics-Token: $METRICS_TOKEN" https://<host>/internal/metrics
  ```

  Any scraper that can attach a static request header works; in Prometheus that is the
  scrape job's `http_headers` (supported from 2.49) with the token read from a file
  rather than inlined:

  ```yaml
  scrape_configs:
    - job_name: familyroots-backend
      metrics_path: /internal/metrics
      scheme: https
      static_configs: [{ targets: ["<host>"] }]
      http_headers:
        X-Metrics-Token:
          secret_file: /etc/prometheus/familyroots-metrics-token
  ```

  On an older Prometheus, put the header on a sidecar/reverse proxy instead. Verify
  the exact key against your Prometheus version's docs before rolling it out — this
  endpoint has no scraper yet, so the snippet above is untested in production.

- **Every failure is a 404, by design** — disabled, no token configured, missing header,
  wrong token, and non-ASCII token all return 404, never 401/403, so an unauthenticated
  scan cannot confirm the endpoint exists (ADR-021). A 404 while scraping therefore means
  "misconfigured *or* switched off"; check `METRICS_ENABLED` and the token before
  suspecting a routing problem.
- The endpoint is **envelope-exempt** (`text/plain` exposition, not `{"data": ...}`) and
  hidden from the OpenAPI schema.
- `/health` and `/internal/metrics` are excluded from the metrics themselves, so
  platform health polling does not dominate the series.

## Correlation — `traceparent`
Every response carries a W3C `traceparent`, continued from the caller's if it sent one,
and CORS exposes it so a browser can show a user the trace id. JSON log lines inside a
request carry `trace_id`/`span_id`, plus `route` (the **raw** request path) and `clan_id`
(the **claimed** `X-Current-Clan-Id`, truncated to 64 chars — not an authorized clan).
Sentry events are tagged with `trace_id`: that is the pivot from a Sentry issue to a log
search. → ADR-033.

## What to watch
- 5xx rate and the `internal_error` code (unhandled exceptions).
- Auth-surface 401/403 spikes (now emitted with stable codes — see the error envelope
  in the contracts docs).
- Migration/deploy failures (the Render pre-deploy migration blocks the release; a
  failed deploy is the signal).
- Scheduler: the anniversary-notification job uses a Postgres advisory lock so only one
  replica runs it; non-winning replicas no-op.

## Gaps / TODO
- `SENTRY_DSN` is not yet wired in `render.yaml` (go-live item) — until then production
  emits no Sentry events.
- RED metrics now **exist** (`/internal/metrics`, opt-in) but nothing scrapes them:
  no Prometheus/Grafana deployment, no dashboards, and no alerting thresholds. Until a
  scraper exists, the endpoint is preparation only and Sentry remains the dashboard.
- `METRICS_ENABLED` / `METRICS_TOKEN` are not wired in `render.yaml`, so production
  currently serves 404 on `/internal/metrics`.
- No minimum-entropy requirement or rate limit on `METRICS_TOKEN` — deferred; treat it
  as a long random secret by convention (`openssl rand -hex 32`).
