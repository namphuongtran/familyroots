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
Single linear chain:
`001_initial` → `002_rls_documents_pilot` → `003_tree_functions` →
`004_fcm_tokens` → `005_tree_functions_clan_scoped` →
`006_softdelete_unique_indexes` → `007_clan_scoped_edge_unique` →
`008_drop_change_req_trigger` → `009_person_birthname_index` →
`010_clan_fk_restrict` → `011_path_tiebreak` →
`012_historical_date_precision` → `013_tree_date_precision` →
`014_drop_date_approx` → `015_data_integrity` → `016_document_soft_delete` →
`017_notification_sent_on` → `018_query_support_indexes` →
`019_path_bfs_visited` → `020_event_soft_delete_occ` →
`021_parent_child_guard` → `022_edge_write_serialization` →
`023_one_founder_per_clan` → `024_kinship_exclude_divorced` →
`025_audit_logs_created_at_index` → `026_rls_activation_grants` →
`027_rls_events_branches` → `028_rls_edges` →
`029_rls_persons`.

`026_rls_activation_grants` completes the `familyroots_app` role's privileges (EXECUTE on
functions, sequence usage + default privileges) for RLS layer-2 activation (SP-3 Phase 1,
ADR-008); grants only, no table/RLS change, reversible.

`027_rls_events_branches` enables the clan-isolation RLS policy on `events` + `branches` (SP-3 Phase 2); reversible (drop policy + disable).

`028_rls_edges` enables the clan-isolation RLS policy on `parent_child` + `marriages` (created_by_clan_id; SP-3 Phase 3); reversible.

`029_rls_persons` enables per-command clan-membership RLS on `persons` (M:N; SP-3 Phase 4); reversible.

`024_kinship_exclude_divorced` replaces the `find_relationship_path` function so its
spouse edge skips `status = 'divorced'` marriages (M8); no schema change, reversible
(downgrade re-installs migration 019's unfiltered body verbatim).

`025_audit_logs_created_at_index` adds `idx_audit_logs_created_at (created_at DESC,
id DESC)` for the platform-wide newest-first audit scan (M14); index-only, reversible.

Head = `029_rls_persons`; verify with `cd backend && uv run alembic history`.

New-revision convention: revision ids ≤32 chars, named `NNN_short_slug`.

## Boot-time migration gate
`backend/app/main.py` checks migration status in the lifespan handler — in
production the app **refuses to boot** if the DB is not at head. `/health`
reports a `migrations` field and degrades on mismatch. As a dev bootstrap, the
docker-compose `api` service runs `python -m alembic upgrade head` before
starting uvicorn.

## Known risks
- A parallel hand-written SQL set exists under `infra/supabase/migrations/`; the
  Alembic chain is the source of truth for the deployed schema — keep new DB objects
  in Alembic, not only in the Supabase SQL files (historically they drifted).
