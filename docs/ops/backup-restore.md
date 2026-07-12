# Backup & Restore

> ⚠️ **CURRENT STATE (2026-07-12): NO backup automation exists in this repo.**
> Nothing in `infra/render/render.yaml`, `docker-compose.yml`, or the GitHub
> workflows takes, verifies, or ships a backup. **No restore has ever been
> drilled.** The Render `starter` database plan's snapshot/PITR capabilities are
> **UNVERIFIED** — do not assume the provider is covering us. This runbook defines
> the REQUIRED target; treat closing it as a **production gate**: genealogy data is
> irreplaceable family history, and a clan's decades of records must not depend on
> one provider's default retention.

## Target policy (to implement before go-live)

RPO/RTO are **still to be decided** by the owner; the working assumption is RPO ≤ 24h,
RTO ≤ 4h. The target stack, in order of preference:

1. **Provider-managed daily snapshots + PITR** on the Render Postgres — verify what
   the `starter` plan actually includes (retention window, PITR granularity) and
   upgrade the plan if it doesn't meet the RPO.
2. **Periodic `pg_dump` to owner-controlled, off-provider storage** (e.g. a scheduled
   GitHub Action or cron writing `pg_dump -Fc` to an S3/B2 bucket the *owner* holds
   keys to). Heritage data must have a copy that survives losing the Render account
   itself.
3. **Supabase Storage bucket backup** for document blobs: the DB rows reference
   `family-roots-files/clans/{clan_id}/...` objects; a DB-only backup restores
   metadata pointing at nothing. Mirror the bucket (Supabase CLI / rclone against the
   S3-compatible endpoint) on the same cadence.

## Restore drill procedure (run quarterly, and before declaring go-live)

Never restore over production first. Drill into a scratch database:

1. Create a scratch DB and restore the latest dump into it:
   `pg_restore --clean --if-exists -d <scratch-dsn> <dump-file>`.
2. Point a checkout at it and confirm the schema is at head:
   `cd backend && DATABASE_URL=<scratch-dsn> uv run alembic current`
   — must print the same head as `uv run alembic heads`.
3. Smoke queries — verify row counts against known production values:
   `SELECT count(*) FROM clans;` — likewise `persons`, `clan_memberships`,
   `parent_child`, `marriages`, `documents`, `events`, `user_clan_roles`, `audit_log`.
4. Spot-check one clan's tree end-to-end (boot the API against the scratch DB, call
   `GET /api/v1/tree` with that clan) and one document presigned URL (proves blob
   backup, not just DB).
5. Record duration (= measured RTO) and dump age (= achieved RPO). Only then promote:
   restore into the real instance / repoint `DATABASE_URL`.

## Local dev backup/restore (docker `pgdb`)

```bash
# Backup (custom format, compressed) from the compose Postgres
docker exec familyroots-pgdb pg_dump -U postgres -Fc -d family_roots \
  > familyroots-$(date +%Y%m%d).dump

# Restore into a scratch DB inside the same container
docker exec familyroots-pgdb createdb -U postgres family_roots_restore
docker exec -i familyroots-pgdb pg_restore -U postgres -d family_roots_restore \
  --clean --if-exists --no-owner < familyroots-20260712.dump

# Full reset instead: drop the volume and re-migrate
docker compose down -v && docker compose up -d pgdb && \
  cd backend && uv run alembic upgrade head
```

(Compose defaults: user `postgres`, db `family_roots` — see `docker-compose.yml`.)

## Related data-safety gaps

- **Clan data export**: planned (ADR-005, tree PDF/export pipeline) but **not
  implemented** — users currently have no self-service copy of their own data.
- **Document deletion is a hard delete** with permanent blob removal and no trash or
  versioning; the orphan-blob sweep mentioned in code comments does not exist. A
  mistaken admin delete is only recoverable from these backups — which is another
  reason this runbook is a gate. See
  [../architecture/storage.md](../architecture/storage.md).
- **Admin succession**: no runbook exists for a clan whose only admin dies or leaves
  — TBD, related to the same "family data must outlive individuals" principle.

## Related

- [configuration.md](configuration.md) — `DATABASE_URL` handling and prod fail-fasts
- [migrations.md](migrations.md) — Alembic chain the drill validates
- [incident-response.md](incident-response.md) — when a restore becomes an incident
