# Monitoring

## Overview
Error/performance monitoring via Sentry; liveness via the `/health` endpoint.

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
- `GET /health` runs `SELECT 1`; returns `{"status":"ok","database":"connected"}` or
  503 `{"status":"degraded","database":"unreachable"}`. Render uses it as the
  `healthCheckPath`.

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
- No metrics/APM dashboard or alerting thresholds defined yet.
