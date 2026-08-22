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
`029_rls_persons` → `030_rls_change_requests` → `031_rls_clan_memberships` →
`032_rls_clan_invitations` → `033_rls_identity_claims` →
`034_rls_audit_notification` → `035_rls_clan_settings` →
`036_rls_user_clan_roles` → `037_drop_allow_public_tree` → `038_drop_privacy_level` →
`039_drop_clan_settings`.

`026_rls_activation_grants` completes the `familyroots_app` role's privileges (EXECUTE on
functions, sequence usage + default privileges) for RLS layer-2 activation (SP-3 Phase 1,
ADR-008); grants only, no table/RLS change, reversible.

> **A migration that changes what `familyroots_app` may do must also change
> `scripts/restore_bootstrap_role.sql`, in the same pull request.** That file replays what
> migrations `002` and `026` grant, so that a restore into a cluster which never held the role
> produces a database the application can open. A dump carries neither the role, which is a cluster
> object, nor the grants, which `--no-privileges` drops. Nothing enforces the two staying equal.
> `scripts/restore_drill.sh` check 4 catches a missing table, function, or sequence grant, because
> it runs a real query as the role; it would not catch a privilege class no query exercises. Added
> 2026-08-22 by seed S-057, [ADR-052](../decisions/052-restore-bootstraps-the-request-role.md).

`027_rls_events_branches` enables the clan-isolation RLS policy on `events` + `branches` (SP-3 Phase 2); reversible (drop policy + disable).

`028_rls_edges` enables the clan-isolation RLS policy on `parent_child` + `marriages` (created_by_clan_id; SP-3 Phase 3); reversible.

`029_rls_persons` enables per-command clan-membership RLS on `persons` (M:N; SP-3 Phase 4); reversible.

`030_rls_change_requests` enables the clan-isolation RLS policy on `change_requests` (SP-3 Phase 5, S-008); reversible (drop policy + disable).

`031_rls_clan_memberships` enables the clan-isolation RLS policy on `clan_memberships`
(SP-3 Phase 6, S-009); reversible (drop policy + disable). `clan_invitations`, the other
table S-009 named, was left uncovered here — the accept-by-token path has no clan
context, so a policy there locked every invitee out; see `data-model.md` and
`backend/tests/integration/test_invitation_accept_no_clan_context.py`. **Migration `032`
below then covered it**, once ADR-048 moved that one route to the privileged session.

`032_rls_clan_invitations` enables the clan-isolation RLS policy on `clan_invitations`
(SP-3 Phase 7, S-043, ADR-048); reversible. Its hard precondition is in the application,
not the migration: `POST /invitations/{token}/accept` runs on its own privileged provider
`get_invitation_accept_handler`, while create, list and revoke keep the RLS request
session.

`033_rls_identity_claims` enables RLS on `identity_claims` with **one deny-all policy**,
`FOR ALL USING (false) WITH CHECK (false)` (SP-3 Phase 8, S-012, ADR-042); reversible. That
is a tripwire for a claims query mis-wired to the request session, **not** clan isolation —
the table has no `clan_id`, and its application layer is its only isolation.

`034_rls_audit_notification` covers two tables with two shapes (SP-3 Phase 9, S-014,
ADR-043); reversible. `notification_log` takes the standard template. `audit_logs` gets
`audit_logs_sel` keyed on the GUC, `audit_logs_ins WITH CHECK (true)`, and **no UPDATE and
no DELETE policy**, which makes the trail append-only for the request role. Ships with
`AuditLog.__mapper_args__ = {"eager_defaults": False}` in the same commit; removing that
line makes `POST /auth/register` answer 500 (ADR-038).

`035_rls_clan_settings` enables the clan-isolation RLS policy on `clan_settings` (SP-3
Phase 10, S-010); reversible (drop policy + disable). `user_clan_roles`, the other table
S-010 named, is deliberately left uncovered and **needs a decision, pre-allocated as
ADR-050**: it is the table the authorization gate reads, and a policy there makes
`POST /auth/login` answer `200` with `clan_id: null` while making `POST /auth/onboard`
raise `InsufficientPrivilege`. See `data-model.md` and
`backend/tests/integration/test_rls_login_two_clans.py`.

`036_rls_user_clan_roles` gives `user_clan_roles` **four per-command policies** (SP-3
Phase 11, S-052, ADR-050); reversible. It is not the 027 template: `SELECT USING (true)`
and `INSERT WITH CHECK (true)` are permissive **by decision**, because four request-session
readers run before any clan is selected, starting with `get_current_clan_id` itself; the
`UPDATE` and `DELETE` halves are clan-keyed, and they are what the migration is for. See
the migration docstring and `backend/tests/integration/test_rls_login_two_clans.py`.

`037_drop_allow_public_tree` drops `clan_settings.allow_public_tree` (S-017, ADR-044 § 1);
reversible, and exactly so. The table has no rows — nothing constructs a `ClanSettings` and
no trigger creates one — so there is no per-row value to reconstruct, and `downgrade()`
re-adds the column with the same `NOT NULL` and the same `server_default false` that
`001_initial.py:600` gave it. No API shape changes: no contract ever documented the column.
**The column does not come back**; the concept returns as `privacy_level` alone, if at all.

`038_drop_privacy_level` drops `clan_settings.privacy_level` (S-018, ADR-044 § 2);
reversible, and exactly so, for the same reason `037` is — the table has no rows, so there
is no per-row value to reconstruct, and `downgrade()` re-adds the column with the same
`NOT NULL` and the same `server_default 'clan_members'` that `001_initial.py:603` gave it.
No API shape changes: no contract ever documented the column. **This is not a decision
against per-clan privacy.** It refuses a control that restricts nothing, which is the most
dangerous kind — a `riêng tư` switch that changes no read leaves the operator believing the
tree is private when it is not. The concept may return, on the four terms ADR-044 § 2 names,
in one change. `data-model.md` was corrected in the same commit: it held the column's value
domain (`private`, `clan_members`, `public`) in two places, the ER diagram and the column
table, and the domain was unenforced — no `CHECK`, no enum, no validator.

`039_drop_clan_settings` drops the whole `clan_settings` table (S-065, ADR-054); reversible.
It is the end of the sequence `037` and `038` started: those took two columns, this takes what
was left, which was five unread columns, zero rows, and an RLS policy guarding a reader that
never arrived. **`DROP TABLE` is not a column drop** — it silently takes the `035` policy, the
`trg_clan_settings_updated_at` trigger, the `RESTRICT` foreign key that migration `010` gave
it, the unique constraint, and the `familyroots_app` grants. `downgrade()` rebuilds all five
explicitly and restores the table as `038` had it, not as `001` created it.

**The round trip is exact except for `attnum`, and in the tidier direction.** At `038` the
live columns are `1,2,3,4,5,7,9,10,11`: the gaps at 6 and 8 are the tombstones `037` and `038`
left, and Postgres never reuses a dropped `attnum`. A `CREATE TABLE` cannot reproduce a gap,
so `downgrade` returns `1..9` contiguous. Everything that carries meaning — names, types,
`NOT NULL`, defaults, order, PK, unique, FK and its `RESTRICT`, the trigger, the RLS flags,
both policy predicates, and the grants — comes back identical, proved by `cmp` against a
database that never carried `039`. This is the mirror of what S-018 recorded for `038`, where
`ADD COLUMN` could not restore ordinal position either.

**`upgrade()` refuses to run if the table holds a row.** ADR-054 rests on the table being
empty, which is measured rather than assumed, so the migration re-checks it at run time and
raises instead of deleting data. No API shape changes: no endpoint ever read or wrote the
table and no contract ever documented it.

`024_kinship_exclude_divorced` replaces the `find_relationship_path` function so its
spouse edge skips `status = 'divorced'` marriages (M8); no schema change, reversible
(downgrade re-installs migration 019's unfiltered body verbatim).

`025_audit_logs_created_at_index` adds `idx_audit_logs_created_at (created_at DESC,
id DESC)` for the platform-wide newest-first audit scan (M14); index-only, reversible.

Head = `039_drop_clan_settings`; verify with `cd backend && uv run alembic heads`.

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
