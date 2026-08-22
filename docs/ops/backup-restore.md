# Backup & Restore

> **ACTIVE since 2026-07-12.** Nightly off-provider database backups run from
> GitHub Actions (`.github/workflows/db-backup.yml`) into a Supabase Storage
> bucket, separate from the Render database itself. A restore has been drilled
> for real against a local dev dump (see the drill log below, most recently
> 2026-08-22) — this is no longer a "target" runbook, it documents what
> actually ships. No production dump has been drilled, and no dump carrying the
> RLS migrations has been drilled. Document blobs live in Supabase Storage
> already; the still-deferred items are called out honestly at the bottom.

## What runs

- **Workflow**: `.github/workflows/db-backup.yml`, job `backup`.
- **Schedule**: `cron: "15 17 * * *"` = **00:15 Asia/Ho_Chi_Minh** nightly, plus
  `workflow_dispatch` for on-demand runs (Actions tab → "db-backup" → "Run workflow").
- **Steps**: install `postgresql-client` → `scripts/db_backup.sh` runs
  `pg_dump --format=custom --no-owner --no-privileges "$DATABASE_URL" | gzip` →
  upload to the Supabase Storage `backups` bucket via the Storage REST API →
  rotate.
- **Secret gate**: if `PROD_DATABASE_URL`, `SUPABASE_URL`, or
  `SUPABASE_SERVICE_ROLE_KEY` is absent, the job prints
  `::notice::db-backup secrets not configured — skipping ...` and exits green
  (neutral skip) rather than failing — see the go-live checklist below; this
  keeps forks/CI clean but means a green run is **not** proof a backup
  happened until the secrets are set.

## Storage layout + rotation

```
backups/                       (private Supabase Storage bucket)
  db/daily/familyroots-YYYY-MM-DD.dump.gz    (kept: newest 7)
  db/weekly/familyroots-YYYY-MM-DD.dump.gz   (kept: newest 4, written Sundays only)
```

`scripts/db_backup.sh` uploads to `db/daily/` every run; on Sundays
(`TZ=Asia/Ho_Chi_Minh date +%u` = 7) it additionally copies to `db/weekly/`.
After each upload it lists the relevant prefix and deletes the oldest objects
beyond the keep-count (7 daily / 4 weekly). A dump over 400MB logs a
`::warning::` (Supabase Storage limits); a dump under 1KB is treated as a
failed backup and the job errors out.

## RPO / RTO

- **RPO ≈ 24h** — one nightly dump; worst case you lose up to a day of writes.
- **RTO ≈ 1h (manual)** — no automated restore-to-production path exists;
  recovery means a human runs `scripts/restore_drill.sh` (or a production
  variant of it) and repoints `DATABASE_URL`. Budget roughly an hour for
  download + restore + verification on a database this size; this has not
  been timed against a production-sized dump yet.

## Running a backup on demand

- **From GitHub**: Actions tab → "db-backup" workflow → "Run workflow" (uses
  the same secrets as the nightly cron).
- **Locally**:
  ```bash
  export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/family_roots
  export SUPABASE_URL=...
  export SUPABASE_SERVICE_ROLE_KEY=...
  bash scripts/db_backup.sh            # real upload
  bash scripts/db_backup.sh --dry-run  # dumps + sizes, skips the upload/rotation (no Supabase secrets needed)
  ```

## Restore procedure — `scripts/restore_drill.sh`

**Prerequisite: `psql`, `pg_dump`, and `pg_restore` must be on `PATH`.** On the maintainer's
machine, checked 2026-08-22, Homebrew's `libpq` 18.4 is keg-only, so all three report "command not
found" until you run `export PATH="/opt/homebrew/opt/libpq/bin:$PATH"`. Without it the drill's
first `psql` call fails and the script blames the wrong thing. Reproduced 2026-08-22 with the same
`if ! psql …` construct the script uses at `scripts/restore_drill.sh:102-106`: bash prints
`bash: psql: command not found`, then the script's own branch prints `::error::cannot reach
Postgres at … — is pgdb up?` and `DRILL: FAIL`. Postgres was up the whole time.

Never restores over production — it always targets a scratch database
(`familyroots_restore_drill`) on `PGHOST:PGPORT` (default
`localhost:5432`, `postgres`/`postgres`), dropping and recreating it first, so
it's safe to re-run.

```bash
scripts/restore_drill.sh <dump.gz>     # restore a local gzip'd pg_dump custom-format archive
scripts/restore_drill.sh --latest      # download the newest backups/db/daily/ object first
                                        # (needs SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
```

It restores the dump, then runs three checks and prints a report:

1. **Alembic head** — compares the restored `alembic_version` against
   `cd backend && uv run alembic heads`. A dump older than the repo head
   **warns**, it does not fail (an old dump is still a valid backup).
2. **Row-count smoke report** — `clans`, `persons`, `clan_memberships`,
   `marriages`, `parent_child`, `events`, `documents`. Zero counts are fine; a
   query error (e.g. a missing table) fails the check.
3. **Tree query** — picks a non-deleted person with a clan and calls
   `get_family_tree_flat(...)`; if the restored DB has no such person the
   check **warns and skips** rather than failing.

Final line is `DRILL: PASS` (exit 0) or `DRILL: FAIL (N check(s) failed)`
(exit 1). Run it **quarterly** against the latest backup, and always
immediately after the go-live checklist's first real prod dump.

## Drill log

| Date | Dump | Result | Notes |
|------|------|--------|-------|
| 2026-07-14 | `familyroots-manual-seeded.dump.gz` (local dev, migrated to head + seeded with a 3-person/2-generation tree) | **DRILL: PASS** | All 3 checks OK on their success path: alembic head matched (`016_document_soft_delete`), non-zero row counts for the seeded tables, tree query returned 3 rows. An earlier run against the same dev DB pre-migration/pre-seed exercised the WARN branches (behind-head, no-persons-skip) — both PASS. Failure paths (corrupt dump, unreachable Postgres, missing table, missing function, missing `uv`) were exercised in review, not on this dump — the review fix guarded all capture sites, and a rider repro confirmed a dump missing `persons` yields `DRILL: FAIL` with a full report and no crash. |
| 2026-08-22 | `familyroots-2026-08-22.dump.gz` (14,669 bytes), produced the same day by `scripts/db_backup.sh --dry-run` against the local docker database `family_roots`. **Local dev data, not a production dump.** | **DRILL: PASS** (exit 0) | The alembic check returned a **WARN**, not an OK: `WARN — dump at 016_document_soft_delete, repo head is 033_rls_identity_claims (dump predates head; not a failure)`. The local dev database has not been migrated since the 2026-07-14 drill, so the dump sits 17 revisions behind the chain (`017_notification_sent_on` through `033_rls_identity_claims`). Row counts non-zero for `clans` 1, `persons` 3, `clan_memberships` 3, `parent_child` 2; zero for `marriages`, `events`, `documents`. Tree query OK, 3 rows. Restored into the scratch database `familyroots_restore_drill`; `family_roots` was never touched, and its seven row counts were identical before and after the run. |

Verbatim output of the 2026-07-14 run ("run 2", the success-path run its row refers to):

<details>
<summary>Drill run 2 — migrated + seeded (click to expand)</summary>

```
$ bash scripts/restore_drill.sh /tmp/fr-drill/familyroots-manual-seeded.dump.gz
==> dropping scratch DB if it exists: familyroots_restore_drill
DROP DATABASE
==> creating scratch DB: familyroots_restore_drill
CREATE DATABASE
==> restoring /tmp/fr-drill/familyroots-manual-seeded.dump.gz -> familyroots_restore_drill
==> pg_restore completed
==> checking alembic head
  OK   — dump at 016_document_soft_delete, matches repo head
==> row-count smoke report
  clans                1
  persons              3
  clan_memberships     3
  marriages            0
  parent_child         2
  events               0
  documents            0
==> tree query check (get_family_tree_flat)
  OK   — get_family_tree_flat returned 3 row(s) for person 22222222-2222-2222-2222-222222222221

===== Restore Drill Report =====
dump:        /tmp/fr-drill/familyroots-manual-seeded.dump.gz
scratch db:  familyroots_restore_drill @ localhost:5432
alembic:     OK   — dump at 016_document_soft_delete, matches repo head
row counts:
  clans                1
  persons              3
  clan_memberships     3
  marriages            0
  parent_child         2
  events               0
  documents            0
tree query:  OK   — get_family_tree_flat returned 3 row(s) for person 22222222-2222-2222-2222-222222222221
=================================
DRILL: PASS
```
Exit code: `0`.

</details>

Verbatim output of the 2026-08-22 run:

<details>
<summary>Drill run, 2026-08-22 — local dev dump taken the same day (click to expand)</summary>

Exact command, run from the repository root with the keg-only libpq client on `PATH`:

```
export PATH="/opt/homebrew/opt/libpq/bin:$PATH"
bash scripts/restore_drill.sh /private/tmp/claude-501/-Volumes-Macext01-HD-playground-familyroots/80bc46c2-0552-41bf-a551-adbbc0c39289/scratchpad/fr-drill/familyroots-2026-08-22.dump.gz
```

```
==> dropping scratch DB if it exists: familyroots_restore_drill
DROP DATABASE
==> creating scratch DB: familyroots_restore_drill
CREATE DATABASE
==> restoring /private/tmp/claude-501/-Volumes-Macext01-HD-playground-familyroots/80bc46c2-0552-41bf-a551-adbbc0c39289/scratchpad/fr-drill/familyroots-2026-08-22.dump.gz -> familyroots_restore_drill
==> pg_restore completed
==> checking alembic head
  WARN — dump at 016_document_soft_delete, repo head is 033_rls_identity_claims (dump predates head; not a failure)
==> row-count smoke report
  clans                1
  persons              3
  clan_memberships     3
  marriages            0
  parent_child         2
  events               0
  documents            0
==> tree query check (get_family_tree_flat)
  OK   — get_family_tree_flat returned 3 row(s) for person 22222222-2222-2222-2222-222222222221

===== Restore Drill Report =====
dump:        /private/tmp/claude-501/-Volumes-Macext01-HD-playground-familyroots/80bc46c2-0552-41bf-a551-adbbc0c39289/scratchpad/fr-drill/familyroots-2026-08-22.dump.gz
scratch db:  familyroots_restore_drill @ localhost:5432
alembic:     WARN — dump at 016_document_soft_delete, repo head is 033_rls_identity_claims (dump predates head; not a failure)
row counts:
  clans                1
  persons              3
  clan_memberships     3
  marriages            0
  parent_child         2
  events               0
  documents            0
tree query:  OK   — get_family_tree_flat returned 3 row(s) for person 22222222-2222-2222-2222-222222222221
=================================
DRILL: PASS
```
Exit code: `0`. The drill was run **once**. The dump it read was produced the same day by
`BACKUP_TMPDIR=… DATABASE_URL=postgresql://postgres:postgres@localhost:5432/family_roots bash scripts/db_backup.sh --dry-run`,
which runs the real `pg_dump | gzip` path and stops before the Supabase upload, so no Supabase
credential was needed and nothing was uploaded.

</details>

### What the 2026-08-22 run proves, and what it does not

- **It proves the restore path works end to end today**: a dump written by `scripts/db_backup.sh`
  restores into a fresh database with `pg_restore --exit-on-error`, and the restored database
  answers both the row-count queries and `get_family_tree_flat()`.
- **It does not prove anything about production.** The dump holds local dev data. No production
  dump has ever been drilled here. That item is still open in the go-live checklist above.
- **It does not prove the current schema restores.** The dump reports
  `016_document_soft_delete`, and the repo chain head is `033_rls_identity_claims`. Both recorded
  drills, 2026-07-14 and 2026-08-22, ran against a dump at `016`. **Nothing in this repository has
  restored a dump carrying the RLS migrations `026` to `033`,** and the drill would not report the
  gap this opens. The reasoning below is read from the scripts and the migrations. It was **not**
  tested on 2026-08-22, because the dev database is at `016` and has no RLS to carry:
  - `scripts/db_backup.sh` runs `pg_dump --format=custom --no-owner --no-privileges`, and
    `scripts/restore_drill.sh` runs `pg_restore --no-owner --no-privileges`. Neither dumps cluster
    roles, and `--no-privileges` drops the `GRANT` statements.
  - Migration `002` creates the non-bypass role `familyroots_app`
    (`CREATE ROLE familyroots_app NOLOGIN` at
    `backend/migrations/versions/002_rls_documents_pilot.py:38`) and migration `026` extends its
    grants (`026_rls_activation_grants.py:30-36`). A role is cluster-wide, not database-wide,
    so a drill restoring into the **same** cluster finds the role already there and sees nothing
    wrong. A real recovery restores into a **new** cluster, where the role and its grants are
    absent, and `SET LOCAL ROLE familyroots_app` (`backend/app/core/rls.py:63`) would then fail.
    That is the case the drill does not cover.
  - The drill's three checks would still pass, because they connect as the superuser that created
    the scratch database, and that role bypasses RLS. See "Still deferred" below.

### Two corrections to earlier records

- **The claim that no dated drill result existed was wrong when it was written.** `docs/SEEDS.md`
  carries a `Not verified` row reading "No dated restore-drill result exists. Searched 2026-08-13,
  nothing under `docs/ops/` records a run of `scripts/restore_drill.sh` with a date and a `DRILL:`
  line." The drill-log table above, with a `DRILL: PASS` row and its verbatim output, was added by
  commit `a533d75`, committed 2026-07-14, and `git merge-base --is-ancestor a533d75 HEAD` confirms
  it has been an ancestor ever since. (Its row read `2026-07-12` at that commit and reads
  `2026-07-14` today.) What was actually missing on 2026-08-13 was not a dated result. It was a
  **current** one: the newest result was five weeks old and 17 revisions behind the chain.
- **The Postgres client tools are installed on this machine but are not on `PATH`.** Homebrew's
  `libpq` 18.4 is keg-only at `/opt/homebrew/opt/libpq/bin`, so `psql`, `pg_dump`, and `pg_restore`
  all report "command not found" until that directory is prepended. The drill's own error branch
  reads `cannot reach Postgres … — is pgdb up?`, which points at the wrong cause for this failure.
  Prepend the path before running either script.

## Local dev backup/restore (docker `pgdb`)

```bash
# Backup (custom format, compressed) from the compose Postgres
docker exec familyroots-pgdb pg_dump -U postgres -Fc -d family_roots \
  > familyroots-$(date +%Y%m%d).dump

# Restore via the drill script (recommended — runs the 3 verification checks)
gzip familyroots-$(date +%Y%m%d).dump
scripts/restore_drill.sh familyroots-$(date +%Y%m%d).dump.gz

# Full reset instead: drop the volume and re-migrate
docker compose down -v && docker compose up -d pgdb && \
  cd backend && uv run alembic upgrade head
```

(Compose defaults: user `postgres`, db `family_roots` — see `docker-compose.yml`.)

## Go-live checklist

- [ ] Create a **private** Supabase Storage bucket named `backups` (production project).
- [ ] Add three GitHub Actions secrets (repo settings): `PROD_DATABASE_URL`,
  `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` — see
  [secrets.md](secrets.md) for what each one is and where it comes from.
- [ ] **⚠️ `SUPABASE_SERVICE_ROLE_KEY` is a project-wide admin credential, not
  a bucket-scoped one** — it bypasses RLS on every table and grants full
  access to every Storage bucket (including the live `documents` bucket) plus
  the auth admin API. Putting it in this GitHub Actions workflow means a CI
  leak compromises the *entire* Supabase project, not just backups, and would
  require rotating all Supabase project keys. Prefer provisioning a scoped
  Storage-only credential (Supabase S3 access keys, restricted to the
  `backups` bucket) for the backup job when available, and keep the
  service-role key out of CI. See [secrets.md](secrets.md) for details.
- [ ] Run `workflow_dispatch` once by hand and confirm the job goes green with
  an actual upload (not the `::notice::` skip line) and an object appears
  under `backups/db/daily/`.
- [ ] Run `scripts/restore_drill.sh --latest` against that first real prod
  dump and confirm `DRILL: PASS`; record the result in the drill log above.
- [ ] Wait 8 days (past the first Sunday) and confirm rotation: exactly 7
  objects under `db/daily/`, and a `db/weekly/` object created on Sunday.
- [ ] **⚠️ Until the three secrets are set, the nightly run SKIPS GREEN** with
  only a `::notice::` in the log — a green checkmark in Actions does **not**
  mean a backup happened. Someone must check the Actions log (not just the
  status) after go-live to confirm real uploads are occurring — this is a
  silent no-backup risk if skipped.
- [ ] Confirm the workflow's pg_dump major version ≥ the production Postgres
  major (currently 18 — the workflow pins `postgresql-client-18`; re-pin when
  the DB upgrades).

## Still deferred (honest gaps)

- **Render-plan PITR verification**: whether the Render Postgres `starter`
  plan provides point-in-time recovery, and its actual retention window, has
  not been verified with Render. The GitHub-Actions backup above is the
  primary, verified recovery path; provider-side PITR would be a
  defense-in-depth addition, not a replacement.
- **Document-blob bucket mirroring**: document files already live in Supabase
  Storage (same provider as the DB backups), so a DB-only restore repoints at
  live blobs today — but there is no independent backup/mirror of the
  documents bucket itself onto a second provider. A Supabase-wide outage or
  account loss would take blobs down with no off-provider copy.
- **Admin-succession runbook**: no runbook exists for a clan whose only admin
  dies or leaves — unrelated to backups mechanically, but the same "family
  data must outlive individuals" principle; still TBD.
- **No drill against a dump at the chain head, and none against an RLS-carrying dump**: both
  recorded results, 2026-07-14 and 2026-08-22, restored a dump reporting
  `016_document_soft_delete`, while the chain head on 2026-08-22 is `033_rls_identity_claims`. So
  the restore path is proven for the pre-RLS schema only. Restoring a post-`026` dump also needs
  the `familyroots_app` role and its grants in the target cluster, which the dump does not carry;
  see the 2026-08-22 note above.
- **Backup-freshness monitoring**: GitHub silently drops/auto-disables
  scheduled workflows after 60 days of repository inactivity, with no alert
  when this happens. A dead-man's-switch alert ("no `db/daily` object newer
  than 48h") is a tracked follow-up; until then a green Actions history is
  **not** proof of fresh backups.

## Related data-safety context

- **Clan data export**: shipped — clan admins can self-serve a lossless JSON
  archive + GEDCOM via `GET /api/v1/exports/clan` (ADR-020,
  [rest-exports-api.md](../contracts/rest-exports-api.md)); this is a
  clan-initiated export, distinct from the operator-run DB backup documented
  above. The PDF gia phả book (ADR-005) remains deferred.
- **Document deletion is soft** (ADR-019): the blob survives a delete and
  admins can restore for `DOCUMENT_RETENTION_DAYS` (30) before the purge job
  permanently removes blob + row. Nightly DB backups above are the only
  recovery path AFTER purge; orphan-blob reconciliation (blobs with no row,
  from old compensation paths) is still deferred. See
  [../architecture/storage.md](../architecture/storage.md).

## Related

- [configuration.md](configuration.md) — `DATABASE_URL` handling and prod fail-fasts
- [migrations.md](migrations.md) — Alembic chain the drill validates
- [secrets.md](secrets.md) — the 3 backup secrets and where each lives
- [deployment.md](deployment.md) — workflow table, includes db-backup.yml
- [incident-response.md](incident-response.md) — when a restore becomes an incident
