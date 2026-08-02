# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Pre-task reading**: consult the map in `../docs/README.md` before starting — API
shape changes need `../docs/contracts/`, schema changes need
`../docs/architecture/data-model.md` + `../docs/ops/migrations.md`, tree/auth work
needs `../docs/architecture/{tree-read-model,auth-flow}.md`, and architectural or
breaking changes need an ADR (`../docs/decisions/README.md`) in the same PR.
Architecture changes or new aggregates → `../docs/architecture/backend-developer-guide.md`.

## Commands

Dependencies are `uv`-managed (Python 3.14+). Only ruff runs via `uvx`; pytest, mypy, lint-imports, and alembic need `uv run` so the project's virtualenv (with the pydantic mypy plugin and app imports) is used — bare `uvx mypy` fails.

```bash
uv sync                                                # install / sync deps
uv run uvicorn app.main:app --reload                   # dev server on :8000
uv run pytest                                          # full test suite
uv run pytest tests/test_persons.py                    # single file
uv run pytest tests/test_persons.py::test_name -xvs    # single test, fail-fast, verbose
uv run pytest -m unit                                  # by marker: unit | integration | slow
uvx ruff check . && uvx ruff format .                  # lint + format (line length 100)
uv run mypy app/ tests/                                # strict typing (see pyproject overrides)
uv run lint-imports                                    # hexagonal-boundary contracts (import-linter)
uv run alembic revision --autogenerate -m "desc"       # new migration
uv run alembic upgrade head                            # apply migrations
```

Full quality gate — run all five before claiming any change done:

```bash
uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports
```

Alembic reads `DATABASE_URL` from `.env` via `app.core.config.settings` and strips `+asyncpg` for the sync migration driver (see `migrations/env.py`).

## Architecture

The backend follows **DDD + CQRS + hexagonal** layering. Layer rules are **machine-enforced** by import-linter contracts in `pyproject.toml` (`uv run lint-imports`); the "ratchet" contracts pin today's known debt via `ignore_imports` lists that may shrink but never grow — don't add entries.

- `app/domain/<aggregate>/` — pure Python aggregates, value objects, repository **ports**, domain events. **No FastAPI / SQLAlchemy / Pydantic imports allowed here.**
- `app/application/<aggregate>/` — command/query handlers (`commands.py`, `handlers.py`). Orchestrates repositories + UoW; depends only on domain.
- `app/infrastructure/` — concrete adapters: `persistence/*_repository.py` (SQLAlchemy implementations of domain ports), `persistence/*_query_port.py` (read-side CQRS projections), `unit_of_work.py`, `event_dispatcher.py`, `storage/`, `supabase_client.py`. `dependencies.py` is the composition root that wires repos + UoW + handlers into FastAPI `Depends(...)` providers.
- `app/api/v1/` — thin route handlers per aggregate, aggregated in `router.py` under `/api/v1`.
- `app/models/` — SQLAlchemy ORM models (write side). `app/schemas/` — Pydantic v2 request/response DTOs.
- `app/services/` — legacy / cross-cutting service-layer code (notifications, scheduler, translator). Newer aggregates go through `application/` + `infrastructure/`, not here. Import-linter fences it (no api/application/domain/models imports). Its background jobs (scheduler, document purge) are **sanctioned out-of-band writers**: they commit their own sessions outside UoW/domain-events — system actions with no actor, deduped/audited by their own mechanisms — and must stay the only such writers.

Aggregates currently modeled: `auth`, `branch`, `clan`, `document`, `event`, `me`, `person` (incl. claims), `platform_admin`, `relationship`, `tree`, plus `shared`.

### Unit of Work + domain events

`SqlAlchemyUnitOfWork` (`app/infrastructure/unit_of_work.py`) wraps an `AsyncSession`. Aggregates are registered via `uow.track(aggregate)`; on `commit()` the UoW flushes, **collects domain events from all tracked aggregates, dispatches them** (audit log handler, notifications, …), and then commits — so handler side-effects (e.g. audit rows) land in the same transaction. All write paths must flow through UoW + domain events; do not commit the session directly from a handler.

The dispatcher is currently the in-process `InMemoryEventDispatcher` — treat in-process events as **not** durable integration events (see repo-root "Never Do").

### Clan isolation and auth

There is intentionally **no tenant middleware**. Clan scoping comes from two layers:

1. `get_current_clan_id` dependency (`app/core/security.py`) reads the `X-Current-Clan-Id` header; users select their active clan client-side.
2. Clan isolation is enforced in the **application/repository layer**: every clan-scoped read takes `clan_id` as an explicit filter (the PRIMARY guarantee). RLS layer-2 (SP-3, ADR-008) is **Phase-1 active for `documents`**: request sessions drop to the non-bypass `familyroots_app` role + set the `app.clan_id` GUC per transaction (`app/core/rls.py`); system sessions bypass. Gated by `RLS_ENABLED`. Other tables roll out table-by-table.

Auth is Supabase JWT validated against the project's JWKS (cached 1h, asyncio-Lock guarded). RBAC uses `ClanRole` (`viewer < editor < admin`) via `require_role(ClanRole.EDITOR)` for hierarchical checks or `RequireClanRole(["admin","editor"])` for explicit sets — both in `app/core/permissions.py`. Roles are read from `user_clan_role` and require `is_approved=True`.

Never bypass these checks for convenience.

### API response contracts (frozen — the frontend binds these; `docs/contracts/` is the spec)

- **Success envelope**: every 2xx body is `{"data": ...}`; list endpoints add `"meta": {"cursor", "has_more", "limit"}` (single cursor-pagination scheme, opaque cursors, `(created_at, id)` ASC — the one exception is the super-admin `GET /audit-log`, which is DESC/newest-first via `paginate_query(descending=True)` per ADR-030); 204 has no body; `/health` is exempt. Adjunct info goes in `meta` (e.g. `meta.errors`, `meta.warning`), never beside `data`.
- **HistoricalDate**: every date field in responses (persons birth/death, events event_date, marriages marriage/divorce, all tree nodes) is `{"date": ISO|null, "precision": "exact|year|month|circa|unknown", "display": str|null, "lunar": str|null}` — built by `app/schemas/historical_date.py`. Clients render `date` when precision is `exact`, else `display`. Write DTOs accept `*_precision`/`*_display`. Storage has matching `*_precision`/`*_display` columns; the old `*_approx` booleans are gone.
- **đời (generation)**: always computed by the single đời authority (con theo đời cha — ADR-027): thủy tổ = 1, đời = canonical parent's đời + 1, on every tree endpoint; `clan_memberships.generation` is deprecated as a display source. Child tree nodes carry derived `mother_id`/`mother_spouse_order` for đa thê grouping, plus `pedigree_collapse_ref` (bool) marking a stub under a non-canonical in-tree parent.
- Kinship age-based terms (`relationship_descriptor.py`) are only emitted when **both** birth dates have `precision == "exact"`.

### App startup

`app/main.py::create_app` wires: custom exception handlers (`AppError`, `DomainError` → structured envelopes via `app/core/exceptions.py`), CORS, `LanguageMiddleware` (Accept-Language → locale context for i18n), optional `SentryMiddleware`, `RequestMetaMiddleware` (captures client IP/User-Agent into a ContextVar for audit-log enrichment — see `app/core/request_meta.py`), `TraceContextMiddleware` (W3C `traceparent` correlation — see below), and a `RateLimitMiddleware` scoped to `/api/v1/auth` and `/api/v1/invitations` (20 req/min/IP, same bucket; ADR-021). Lifespan initializes Sentry, loads translations, inits Firebase Admin, starts APScheduler (used for anniversary notification jobs — see `NOTIFICATION_CRON_HOUR` in `Settings`), and disposes the async engine on shutdown.

Middleware order matters — Starlette wraps the **last-added** middleware **outermost**,
so `create_app` registers in reverse of the desired execution order. Actual order
(outermost → innermost): `Prometheus → TrustedHost → CORS → TraceContext → Language →
RequestMeta → Sentry → RateLimit` (asserted by
`tests/unit/test_metrics_endpoint.py::test_documented_middleware_order_matches_reality`).
`Prometheus` is added by `Instrumentator(...).instrument(application)` — a *hidden*
`add_middleware` call — and is deliberately outermost so RED latency measures the whole
stack, at the cost of counting `TrustedHost` rejections too; keep it inside the ordering
block or the real order silently drifts from this one. `TraceContext` sits just inside
`CORS` so every log line for the request — including the rate limiter's localized 429 —
carries the trace id.

**Observability (ADR-033):** `TraceContextMiddleware` continues an inbound
`traceparent` header or starts a new W3C trace, storing it in a ContextVar
(`app/core/trace_context.py`); the response echoes `traceparent`, and CORS
`expose_headers` it so browsers can surface it to a user — except on an unhandled
500, where `ServerErrorMiddleware` (Starlette's true outermost layer, ahead of
`Prometheus`) sends the response outside `CORSMiddleware`'s wrapper: `traceparent`
is still on that response but not CORS-exposed, so a browser can't read it; the log
line and tagged Sentry event are the correlation path for that case. `JsonFormatter`
(`app/core/logging.py`) adds `trace_id`/`span_id` to every log line emitted inside a
request, plus `route`/`clan_id` where known — outside a request (scheduler, purge)
these keys are absent entirely, not null. `SentryMiddleware` additionally tags
Sentry events with `trace_id` for the pivot from an issue to log search. RED metrics
are exposed at `GET /internal/metrics` (Prometheus exposition, envelope-exempt),
gated by `METRICS_ENABLED` + `METRICS_TOKEN` (`app/core/config.py`) and the request's
`X-Metrics-Token` header; every failure path 404s (never 401/403) per ADR-021.

Docs (`/docs`, `/redoc`) are only mounted when `APP_DEBUG=true`.

### Migrations

Single-schema Alembic, one linear chain (no branches). `migrations/env.py` imports the full `app.models` package so autogenerate sees every table. The script_location is `migrations` (not the default `alembic/`). Keep revision ids ≤32 characters (the `alembic_version` column limit) — the convention is `NNN_short_slug` matching the filename.

### Testing

`pytest-asyncio` in `auto` mode with function-scoped loops. Markers `unit`, `integration`, `slow` are registered in `pyproject.toml`. `tests/conftest.py` provides factories for mock DB rows (`make_person_row`, etc.) used by tree-builder unit tests. Layout mirrors the app: `tests/unit/{api,domain,infrastructure}/` plus top-level integration-style `test_*.py`.

`tests/integration/` runs against a **real Postgres**: `tests/integration/conftest.py` drops/creates a throwaway `family_roots_schema_test` database and applies the full Alembic chain (session-scoped `migrated_db_url` fixture). It needs `docker compose up -d pgdb` running; override the admin DSN with `TEST_PG_ADMIN_URL` if your local Postgres differs. Prefer these real-DB tests for anything touching migrations, SQL functions, or clan isolation — and test isolation **two-sided** (clan A sees its rows; clan B does not).

### mypy specifics

Strict mode is on globally, but `pyproject.toml` relaxes it for `app.services.*`, several handler/persistence modules, and tests. When touching those modules, don't reintroduce strict-mode failures *elsewhere* to "fix" them locally — check the per-module overrides first.

## Configuration

All settings live in `app/core/config.py` (`pydantic-settings`, reads `.env`). Required envs are in `.env.example`; the storage layout is path-based isolation within a single Supabase bucket: `family-roots-files/clans/{clan_id}/...`.
