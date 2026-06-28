# Migrations

## Overview
Single-schema Alembic migrations under `backend/migrations/` (script_location is
`migrations`, not the default `alembic/`). `migrations/env.py` imports the full
`app.models` package so autogenerate sees every table.

## Driver (psycopg v3, unified)
There is **one** DB driver. `Settings.DATABASE_URL` normalizes any form
(`postgres://`, `postgresql://`, `+asyncpg`, `+psycopg2`) to
`postgresql+psycopg://`; the async app and sync Alembic share the same URL
(`env.py` reuses `settings.DATABASE_URL`). Do not reintroduce asyncpg/psycopg2.

## How migrations run in production (critical)
`infra/render/render.yaml` sets `preDeployCommand: alembic upgrade head`. This runs
**before each deploy goes live and BLOCKS the deploy if it fails**. Consequences:
- A bad migration fails the release instead of shipping a schema-mismatched app.
- **Always test a migration against a prod-like DB before merging to `main`** (merge
  to `main` = production deploy + migration).
- Keep migrations forward-compatible with the currently-running app during the
  pre-deploy window where possible.

## Authoring
```bash
cd backend
uv run alembic revision --autogenerate -m "describe change"   # generate
uv run alembic upgrade head                                   # apply locally
uv run alembic downgrade -1                                   # test the downgrade
uv run pytest tests/integration/test_schema_baseline.py       # round-trip + no-drift gate
```
- Migrations must round-trip: `test_migration_round_trip` downgrades to base then
  upgrades to head; `test_autogenerate_has_no_table_or_column_diff` fails CI if the
  ORM models and migrations diverge. Add an ORM model for any new table so
  autogenerate stays clean.
- SQL functions / RLS objects that autogenerate can't model are created via explicit
  `op.execute(...)` migrations (e.g. `003_tree_functions`, `005_tree_functions_clan_scoped`,
  `002_rls_documents_pilot`).

## Current chain
`001_initial` → `002_rls_documents_pilot` → `003_tree_functions` →
`004_fcm_tokens` → `005_tree_functions_clan_scoped`.

## Known risks
- A parallel hand-written SQL set exists under `infra/supabase/migrations/`; the
  Alembic chain is the source of truth for the deployed schema — keep new DB objects
  in Alembic, not only in the Supabase SQL files (historically they drifted).
