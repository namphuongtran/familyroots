# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Dependencies are `uv`-managed (Python 3.14+). Lint/format/typecheck are run via `uvx`; the test runner needs `uv run` so the project's virtualenv is used.

```bash
uv sync                                                # install / sync deps
uv run uvicorn app.main:app --reload                   # dev server on :8000
uv run pytest                                          # full test suite
uv run pytest tests/test_persons.py                    # single file
uv run pytest tests/test_persons.py::test_name -xvs    # single test, fail-fast, verbose
uv run pytest -m unit                                  # by marker: unit | integration | slow
uvx ruff check . && uvx ruff format .                  # lint + format (line length 100)
uvx mypy app/                                          # strict typing (see pyproject overrides)
uvx alembic revision --autogenerate -m "desc"          # new migration
uvx alembic upgrade head                               # apply migrations
```

Alembic reads `DATABASE_URL` from `.env` via `app.core.config.settings` and strips `+asyncpg` for the sync migration driver (see `migrations/env.py`).

## Architecture

The backend follows **DDD + CQRS + hexagonal** layering. Layer rules are enforced by convention (and reinforced in the repo-root `CLAUDE.md`):

- `app/domain/<aggregate>/` — pure Python aggregates, value objects, repository **ports**, domain events. **No FastAPI / SQLAlchemy / Pydantic imports allowed here.**
- `app/application/<aggregate>/` — command/query handlers (`commands.py`, `handlers.py`). Orchestrates repositories + UoW; depends only on domain.
- `app/infrastructure/` — concrete adapters: `persistence/*_repository.py` (SQLAlchemy implementations of domain ports), `persistence/*_query_port.py` (read-side CQRS projections), `unit_of_work.py`, `event_dispatcher.py`, `storage/`, `supabase_client.py`. `dependencies.py` is the composition root that wires repos + UoW + handlers into FastAPI `Depends(...)` providers.
- `app/api/v1/` — thin route handlers per aggregate, aggregated in `router.py` under `/api/v1`.
- `app/models/` — SQLAlchemy ORM models (write side). `app/schemas/` — Pydantic v2 request/response DTOs.
- `app/services/` — legacy / cross-cutting service-layer code (notifications, scheduler, translator). Newer aggregates go through `application/` + `infrastructure/`, not here.

Aggregates currently modeled: `auth`, `branch`, `clan`, `document`, `event`, `me`, `person` (incl. claims), `platform_admin`, `relationship`, `tree`, plus `shared`.

### Unit of Work + domain events

`SqlAlchemyUnitOfWork` (`app/infrastructure/unit_of_work.py`) wraps an `AsyncSession`. Aggregates are registered via `uow.track(aggregate)`; on `commit()` the UoW flushes, **collects domain events from all tracked aggregates, dispatches them** (audit log handler, notifications, …), and then commits — so handler side-effects (e.g. audit rows) land in the same transaction. All write paths must flow through UoW + domain events; do not commit the session directly from a handler.

The dispatcher is currently the in-process `InMemoryEventDispatcher` — treat in-process events as **not** durable integration events (see repo-root "Never Do").

### Clan isolation and auth

There is intentionally **no tenant middleware**. Clan scoping comes from two layers:

1. `get_current_clan_id` dependency (`app/core/security.py`) reads the `X-Current-Clan-Id` header; users select their active clan client-side.
2. Clan isolation is enforced in the **application/repository layer**: every clan-scoped read takes `clan_id` as an explicit filter. Supabase RLS is a planned defense-in-depth addition (SP-3) and is **not yet active**.

Auth is Supabase JWT validated against the project's JWKS (cached 1h, asyncio-Lock guarded). RBAC uses `ClanRole` (`viewer < editor < admin`) via `require_role(ClanRole.EDITOR)` for hierarchical checks or `RequireClanRole(["admin","editor"])` for explicit sets — both in `app/core/permissions.py`. Roles are read from `user_clan_role` and require `is_approved=True`.

Never bypass these checks for convenience.

### App startup

`app/main.py::create_app` wires: custom exception handlers (`AppError`, `DomainError` → structured envelopes via `app/core/exceptions.py`), CORS, `LanguageMiddleware` (Accept-Language → locale context for i18n), optional `SentryMiddleware`, and a `RateLimitMiddleware` scoped to `/api/v1/auth` (20 req/min/IP). Lifespan initializes Sentry, loads translations, inits Firebase Admin, and starts APScheduler (used for anniversary notification jobs — see `NOTIFICATION_CRON_HOUR` / `NOTIFICATION_DAYS_BEFORE` in `Settings`).

Docs (`/docs`, `/redoc`) are only mounted when `APP_DEBUG=true`.

### Migrations

Single-schema Alembic. `migrations/env.py` imports the full `app.models` package so autogenerate sees every table. The script_location is `migrations` (not the default `alembic/`).

### Testing

`pytest-asyncio` in `auto` mode with function-scoped loops. Markers `unit`, `integration`, `slow` are registered in `pyproject.toml`. `tests/conftest.py` provides factories for mock DB rows (`make_person_row`, etc.) used by tree-builder unit tests. Layout mirrors the app: `tests/unit/{api,domain,infrastructure}/` plus top-level integration-style `test_*.py`.

### mypy specifics

Strict mode is on globally, but `pyproject.toml` relaxes it for `app.services.*`, several handler/persistence modules, and tests. When touching those modules, don't reintroduce strict-mode failures *elsewhere* to "fix" them locally — check the per-module overrides first.

## Configuration

All settings live in `app/core/config.py` (`pydantic-settings`, reads `.env`). Required envs are in `.env.example`; the storage layout is path-based isolation within a single Supabase bucket: `family-roots-files/clans/{clan_id}/...`.
