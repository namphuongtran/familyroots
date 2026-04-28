# Alembic + Postgres Driver Unification (psycopg v3)

**Date:** 2026-04-29
**Status:** Design approved — ready for implementation plan
**Owner:** trphuongnam@gmail.com

## Problem

`docker compose exec api alembic upgrade head` fails with `ModuleNotFoundError: No module named 'psycopg2'`.

Root cause is architectural, not a missing wheel:

- `psycopg2-binary` lives in `[dependency-groups.dev]` in `backend/pyproject.toml`, so the runtime image (built with `uv sync --no-dev`) does not ship it.
- `migrations/env.py` strips `+asyncpg` from the URL on line 29, requiring a sync driver (psycopg2) that the runtime image lacks.
- The runtime Dockerfile *does* COPY `alembic.ini` + `migrations/` into the image, implying migrations should be runnable in-container — but they aren't.
- `infra/render/render.yaml` has no `preDeployCommand`. Production migrations are not wired into deploy at all today.

The current "run alembic from the host" workaround papers over a deeper gap: there is no production migration story, and the same driver mismatch will block whatever production runner we add.

## Goals

1. `docker compose exec api alembic upgrade head` works locally without host-side tooling.
2. Render runs migrations automatically on every deploy via `preDeployCommand`.
3. Single Postgres driver across the runtime image (no parallel async + sync native libs).
4. Minimal blast radius — no schema change, no data migration, no test-suite rewrites.

## Non-goals

- Changing the schema or any model.
- Reworking SQLAlchemy session management.
- Introducing a separate Render job service for migrations.
- Backwards-compatibility shims beyond URL normalization.

## Decisions (locked in)

| Axis | Choice | Rationale |
|---|---|---|
| Scope | Local + production | Same root cause blocks both; fix once. |
| Driver strategy | Replace asyncpg entirely with `psycopg[binary]` v3 | Single package handles async + sync. Eliminates the mismatch by construction. |
| Driver scope | C1 — full replacement (not hybrid) | Hybrid keeps two native libs in the image; user accepts the larger one-shot diff for a cleaner end state. |
| Production migration runner | Render `preDeployCommand: alembic upgrade head` | Native to Render blueprint, blocks deploy on failure, runtime image already ships migration files. |

## Architecture

**Today:**
- App runtime: `asyncpg` (async).
- Alembic: `psycopg2-binary` (sync, host venv only).
- Two native PG drivers, one of them missing in the runtime image.

**After:**
- App runtime: `psycopg[binary]` v3, async dialect (`postgresql+psycopg://`).
- Alembic: `psycopg[binary]` v3, sync dialect (same package, same URL).
- One native driver, available everywhere alembic and the app run.

A `field_validator` on `Settings.DATABASE_URL` normalizes any incoming URL to `postgresql+psycopg://…`. This handles:
- Bare `postgresql://…` (Render injects this via `fromDatabase.connectionString`).
- Stale `postgresql+asyncpg://…` from existing developer `.env` files.
- Already-correct `postgresql+psycopg://…` (no-op).

## File-level changes

| File | Change |
|---|---|
| `backend/pyproject.toml` | Remove `asyncpg` from `[project].dependencies`. Add `psycopg[binary]>=3.2`. Remove `psycopg2-binary` from `[dependency-groups.dev]`. |
| `backend/uv.lock` | Re-lock via `uv lock`. |
| `backend/app/core/config.py` | Default `DATABASE_URL` → `postgresql+psycopg://…`. Add `field_validator` that rewrites any driver suffix (or absence thereof) to `+psycopg`. |
| `backend/app/core/database.py` | No code change. `create_async_engine` works with the psycopg async dialect once the URL says `+psycopg`. |
| `backend/migrations/env.py` | Drop the `.replace("+asyncpg", "")` hack. Use `settings.DATABASE_URL` as-is — psycopg v3's sync dialect handles the same URL. |
| `docker-compose.yml` | `+asyncpg` → `+psycopg` on the `api.environment.DATABASE_URL` line. |
| `.env.example` | Add a documented `DATABASE_URL=postgresql+psycopg://…` line (currently missing). |
| `infra/render/render.yaml` | Add `preDeployCommand: alembic upgrade head` under the `api` service. |
| `Makefile` | No change. `migrate` target keeps working since psycopg v3 is now a runtime dep. |
| `backend/Dockerfile` | No change. Already COPYs `alembic.ini` + `migrations/`. |
| `backend/tests/conftest.py` | No change. Doesn't reference `asyncpg` directly — consumes `settings.DATABASE_URL`. |

## Migration runner — local + production

**Local:**
```bash
docker compose up -d pgdb api
docker compose exec api alembic upgrade head
```

**Production (Render):**
```yaml
services:
  - type: web
    name: familyroots-api
    # ...
    preDeployCommand: alembic upgrade head
```
Render runs `preDeployCommand` against the new image before traffic switches. A failed migration aborts the deploy and the old image keeps serving — no half-migrated state, no manual rollback step.

## Cutover

Single PR, ordered:

1. Update `pyproject.toml` and `uv lock`.
2. Patch `config.py` (validator + default), `migrations/env.py`, `docker-compose.yml`, `.env.example`, `infra/render/render.yaml`.
3. `docker compose build api`.
4. Verify locally: `docker compose down -v && docker compose up -d pgdb api && docker compose exec api alembic upgrade head && curl /health`.
5. `make backend-test`.
6. Smoke a real write endpoint (e.g. `POST /api/v1/auth/register`).

## Testing

- **Validator unit test** — covers bare `postgresql://`, stale `+asyncpg`, correct `+psycopg`. Asserts all three normalize to `+psycopg`.
- **Existing pytest suite** — `make backend-test` runs unchanged. URL change flows through `settings`.
- **In-container alembic** — `docker compose exec api alembic upgrade head` from a clean DB volume succeeds.
- **In-container alembic current** — confirms sync engine reads the version table.
- **`/health`** — confirms async engine and DB connectivity post-cutover.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| psycopg v3 async pool semantics differ from asyncpg (prepared statements, statement caching) | Keep current `pool_size`/`max_overflow`. Run full pytest suite before merge. Smoke a write endpoint. |
| Render's bare `connectionString` slips through and crashes `preDeployCommand` on first deploy | Validator unit test covering the bare-URL case is mandatory before merge. |
| Stale developer `.env` with `+asyncpg` URL stops working | Validator rewrites any non-`+psycopg` driver suffix, so existing `.env` files keep working without manual edits. |
| Subtle SQL behaviour difference (e.g. server-side cursors, COPY) | None of the current app code uses these; verify via test suite. |

## Rollback

Revert the PR. Schema is unchanged. No data migration.

## Out of scope (deferred)

- Reviewing or hardening other parts of the production deploy pipeline.
- Adding migration observability (e.g. emitting a Sentry event on `preDeployCommand` failure).
- Splitting `infra/render/render.yaml` into per-environment files.
