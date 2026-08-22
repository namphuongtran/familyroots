# Backup & Restore

> **ACTIVE since 2026-07-12.** Nightly off-provider database backups run from
> GitHub Actions (`.github/workflows/db-backup.yml`) into a Supabase Storage
> bucket, separate from the Render database itself. A restore has been drilled
> for real against a local dev dump (see the drill log below, most recently
> 2026-08-22) — this is no longer a "target" runbook, it documents what
> actually ships. **A dump at chain head has now been restored into a cluster
> that did not hold the `familyroots_app` role, and the restored database could
> not serve a request-role session.** The drill printed `DRILL: PASS` and exited
> 0 while that was true. Read
> [the fresh-cluster run](#the-2026-08-22-fresh-cluster-run-a-dump-at-head-into-a-cluster-with-no-familyroots_app-role)
> before you rely on a restore. No production dump has been drilled. Document
> blobs live in Supabase Storage already; the still-deferred items are called
> out honestly at the bottom.

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
  been timed against a production-sized dump yet. **Add the role bootstrap to
  that budget when the target is a new cluster.** The dump carries no
  `familyroots_app` role and no grants, so a restored database rejects every
  request until both are created by hand; measured 2026-08-22, see
  [the fresh-cluster run](#the-2026-08-22-fresh-cluster-run-a-dump-at-head-into-a-cluster-with-no-familyroots_app-role).

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

> **⚠️ `DRILL: PASS` does not mean the application can use the restored
> database.** All three checks connect as the superuser that created the scratch
> database, and a superuser bypasses RLS. The request path drops to the
> non-bypass role `familyroots_app` (`backend/app/core/rls.py:63`), and neither
> script carries that role or its grants. Measured 2026-08-22: a dump at chain
> head restored into a role-free cluster, the drill printed `DRILL: PASS`, and
> `SET LOCAL ROLE familyroots_app` on the restored database then returned
> `ERROR: role "familyroots_app" does not exist`. Until that is repaired, run
> the request-role check by hand after every drill — the exact statement is in
> [the fresh-cluster run](#the-2026-08-22-fresh-cluster-run-a-dump-at-head-into-a-cluster-with-no-familyroots_app-role)
> below.

## Drill log

| Date | Dump | Result | Notes |
|------|------|--------|-------|
| 2026-07-14 | `familyroots-manual-seeded.dump.gz` (local dev, migrated to head + seeded with a 3-person/2-generation tree) | **DRILL: PASS** | All 3 checks OK on their success path: alembic head matched (`016_document_soft_delete`), non-zero row counts for the seeded tables, tree query returned 3 rows. An earlier run against the same dev DB pre-migration/pre-seed exercised the WARN branches (behind-head, no-persons-skip) — both PASS. Failure paths (corrupt dump, unreachable Postgres, missing table, missing function, missing `uv`) were exercised in review, not on this dump — the review fix guarded all capture sites, and a rider repro confirmed a dump missing `persons` yields `DRILL: FAIL` with a full report and no crash. |
| 2026-08-22 | `familyroots-2026-08-22.dump.gz` (14,669 bytes), produced the same day by `scripts/db_backup.sh --dry-run` against the local docker database `family_roots`. **Local dev data, not a production dump.** | **DRILL: PASS** (exit 0) | The alembic check returned a **WARN**, not an OK: `WARN — dump at 016_document_soft_delete, repo head is 033_rls_identity_claims (dump predates head; not a failure)`. The local dev database has not been migrated since the 2026-07-14 drill, so the dump sits 17 revisions behind the chain (`017_notification_sent_on` through `033_rls_identity_claims`). Row counts non-zero for `clans` 1, `persons` 3, `clan_memberships` 3, `parent_child` 2; zero for `marriages`, `events`, `documents`. Tree query OK, 3 rows. Restored into the scratch database `familyroots_restore_drill`; `family_roots` was never touched, and its seven row counts were identical before and after the run. |
| 2026-08-22 (second run that day, into a **fresh cluster**) | `familyroots-2026-08-22.dump.gz` (18,257 bytes), produced the same day by `scripts/db_backup.sh --dry-run` against `familyroots_head_stage` — a database built by running the whole Alembic chain from base to `035_rls_clan_settings` on an empty database, then loading the dev tree data. **Local dev data, not a production dump.** | **DRILL: PASS** (exit 0) — **and the restored database could not serve a request-role session.** | Restored into a **second Postgres container** (port 5433) whose cluster held no `familyroots_app` role. Alembic check `OK — dump at 035_rls_clan_settings, matches repo head` — the first drill here to run at head. Row counts `clans` 1, `persons` 3, `clan_memberships` 3, `parent_child` 2; zero for `marriages`, `events`, `documents`. Tree query OK, 3 rows. Then `SET LOCAL ROLE familyroots_app` on the restored database returned `ERROR:  role "familyroots_app" does not exist`. S-050 predicted exactly this and it is the recorded result, not a setup mistake. Full detail, and three follow-up probes, in the section below. |

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

### What the 2026-08-22 first run proves, and what it does not

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

  **This reasoning was tested on 2026-08-22 and it held.** The next section records the run. The
  chain head has also moved since the paragraph above was written: it read `033_rls_identity_claims`
  and is `035_rls_clan_settings` today, so the RLS block is migrations `026` to `035`.


### The 2026-08-22 fresh-cluster run: a dump at head, into a cluster with no `familyroots_app` role

**Answer first. The restored database cannot serve a request-role session.** The drill printed
`DRILL: PASS` and exited 0. The one check the drill does not make, `SET LOCAL ROLE
familyroots_app`, returned `ERROR:  role "familyroots_app" does not exist`. Nothing was adjusted to
produce either line. This is what a real recovery into a new cluster would meet today.

Recorded by seed S-050, which was opened for exactly this question by S-021. No script was changed.
The repair is its own seed.

#### 1. How the dump at chain head was produced, and from which database

The local dev database `family_roots` is still at `016_document_soft_delete`, and it must not be
migrated or written to. So the dump came from a **new database in the dev cluster**, not from
`family_roots` and not from the integration test database:

```
export PATH="/opt/homebrew/opt/libpq/bin:$PATH"
pg_dump -h localhost -p 5432 -U postgres --format=custom --no-owner --no-privileges family_roots > stage016.dump
psql ... -c "CREATE DATABASE familyroots_head_stage"
cd backend && DATABASE_URL="postgresql://postgres:postgres@localhost:5432/familyroots_head_stage" uv run alembic upgrade head
pg_restore --data-only -l stage016.dump | grep -v alembic_version > data.toc
pg_restore --data-only --disable-triggers --no-owner --no-privileges -L data.toc -d ".../familyroots_head_stage" stage016.dump
BACKUP_TMPDIR=... DATABASE_URL="postgresql://postgres:postgres@localhost:5432/familyroots_head_stage" bash scripts/db_backup.sh --dry-run
```

The chain ran from **base**, not from the restored `016` dump, and the order matters. A first
attempt built the staging database by restoring the `016` dump and then running `017` to `035` on
top. That database ended with **0** table grants to `familyroots_app`, because migration `002` had
granted them in `family_roots` and `pg_restore --no-privileges` had dropped them on the way in.
Dumping that would have overstated the gap. Rebuilding from base gives the faithful picture: **18
tables granted, 72 grant rows, schema `USAGE` true**, which is what a production database migrated
from scratch looks like. `familyroots-2026-08-22.dump.gz` is 18,257 bytes.

`family_roots` was never written to. Its seven row counts were `1, 3, 3, 0, 2, 0, 0` before the
session and `1, 3, 3, 0, 2, 0, 0` after, and its `alembic_version` still reads
`016_document_soft_delete`.

#### 2. How a cluster without the role was obtained, and how absence was confirmed **before** the restore

A Postgres role is cluster-wide, so a second database in the `familyroots-pgdb` container would
have found `familyroots_app` already present — the dev cluster does hold it, checked the same day.
A **separate container** is a separate `initdb`, so it is a separate cluster:

```
docker run -d --name familyroots-s050-fresh -e POSTGRES_PASSWORD=postgres -e POSTGRES_USER=postgres \
  -p 5433:5432 postgres:18-alpine
```

Confirmed before the restore, and the identifiers prove the two are different clusters rather than
two views of one:

```
-- 5432 system identifier --
7656068655264079917
-- 5433 system identifier --
7676696829999001645
=== all non-builtin roles in the fresh cluster (5433), BEFORE the restore ===
postgres
=== familyroots_app present in 5433? (0 = absent) ===
0
=== databases in 5433 ===
postgres
template0
template1
```

#### 3. The drill, verbatim

Exact command, run from the repository root:

```
export PATH="/opt/homebrew/opt/libpq/bin:$PATH"
PGPORT=5433 bash scripts/restore_drill.sh .../s050/head-dump/familyroots-2026-08-22.dump.gz
```

```
==> dropping scratch DB if it exists: familyroots_restore_drill
NOTICE:  database "familyroots_restore_drill" does not exist, skipping
DROP DATABASE
==> creating scratch DB: familyroots_restore_drill
CREATE DATABASE
==> restoring /private/tmp/.../s050/head-dump/familyroots-2026-08-22.dump.gz -> familyroots_restore_drill
==> pg_restore completed
==> checking alembic head
  OK   — dump at 035_rls_clan_settings, matches repo head
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
dump:        /private/tmp/.../s050/head-dump/familyroots-2026-08-22.dump.gz
scratch db:  familyroots_restore_drill @ localhost:5433
alembic:     OK   — dump at 035_rls_clan_settings, matches repo head
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

Exit code: `0`. **The drill was run once**, against this dump, into this cluster. `pg_restore`
emitted no warning: the 17 policies target `PUBLIC`, not the role, so nothing in the dump referred
to `familyroots_app` and nothing failed.

#### 4. The check the drill does not make

```
=== roles in the fresh cluster AFTER the restore ===
postgres

psql -h localhost -p 5433 -U postgres -d familyroots_restore_drill -v ON_ERROR_STOP=1 \
  -c "BEGIN; SET LOCAL ROLE familyroots_app; SELECT current_user; COMMIT;"
BEGIN
ERROR:  role "familyroots_app" does not exist
psql exit: 1
```

`settings.RLS_ENABLED` defaults to `True` (`backend/app/core/config.py:71`), so
`apply_rls_context` issues that exact statement at the start of **every** request transaction
(`backend/app/core/rls.py:63`). A restored database in this state fails every clan-scoped request.

#### 5. What the dump does carry, and what it drops

Counted in both databases the same day. Everything structural survives; only the role and its
privileges do not.

| | source `familyroots_head_stage` @5432 | restored `familyroots_restore_drill` @5433 |
|---|---|---|
| base tables | 18 | 18 |
| indexes | 85 | 85 |
| constraints | 228 | 228 |
| functions | 55 | 55 |
| triggers (non-internal) | 13 | 13 |
| extensions | 4 | 4 |
| tables with RLS enabled | 13 | 13 |
| policies | 17 | 17 |
| **grant rows to `familyroots_app`** | **72** | **0** |
| **`familyroots_app` exists in the cluster** | **yes** | **no** |

So the restored database is **armed but unusable**: RLS is on for 13 tables with 17 policies, and
there is no role to switch to and no grant behind it.

#### 6. Three follow-up probes, run after the recorded drill

These ran **after** the drill result above, on throwaway clusters, to tell the repair seed what the
fix has to cover. They are probes, not drill results.

**Probe B — creating the role is not enough.** On the restored database, after
`CREATE ROLE familyroots_app NOLOGIN`:

```
BEGIN
SET
 set_config: 11111111-1111-1111-1111-111111111111
ERROR:  permission denied for table persons
```

**Probe C — role plus the grants from migrations `002` and `026` does work, and isolation holds.**
After running the seven grant statements those two migrations issue:

```
-- clan that owns the data --
 persons_visible
-----------------
               3
-- a clan that owns nothing --
 persons_visible
-----------------
               0
```

**Probe D — simply dropping `--no-owner --no-privileges` does not fix it; it turns a silent
breakage into a hard failure.** A dump taken **with** privileges, restored into a third fresh
cluster (port 5434) that had only the `postgres` role:

```
pg_restore: error: could not execute query: ERROR:  role "familyroots_app" does not exist
Command was: GRANT USAGE ON SCHEMA public TO familyroots_app;

pg_restore exit: 1
```

Run twice. The first run reported its exit code through zsh's `PIPESTATUS`, which read `0`
incorrectly; the second run used `bash -c 'set -o pipefail; …'` on a second scratch database and
reported `1`. The `pg_restore` error text was identical in both.

**What the three probes establish together.** The target cluster needs the role to exist **before**
the restore, and it needs the grants **as well**. `pg_dump` of one database can supply neither on
its own: a role is cluster-wide, so it belongs to `pg_dumpall --roles-only` or to a documented
bootstrap step. Whether this repository dumps roles at all is a decision, and S-050 put it out of
scope on purpose.

#### 7. What was not done

No script was changed. `scripts/restore_drill.sh` and `scripts/db_backup.sh` are byte-identical to
`main`. The drill was not re-run to obtain a different line, and every run of anything is recorded
above. Nothing was restored over `family_roots`. The two throwaway containers
(`familyroots-s050-fresh`, `familyroots-s050-fresh2`) and the staging database
`familyroots_head_stage` were removed after the measurements.

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
- [ ] **⚠️ After that drill, run the request-role check by hand**, because the
  drill does not: `psql <scratch-dsn> -v ON_ERROR_STOP=1 -c "BEGIN; SET LOCAL
  ROLE familyroots_app; SELECT count(*) FROM persons; COMMIT;"`. On 2026-08-22
  this returned `ERROR:  role "familyroots_app" does not exist` on a restore
  into a new cluster while the drill reported `DRILL: PASS`. Record whichever
  line you get.
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
- **A restore into a new cluster produces a database the application cannot use.** This is no
  longer a suspicion. Measured 2026-08-22, third row of the drill log: a dump at
  `035_rls_clan_settings` restored into a cluster holding no `familyroots_app` role, the drill
  printed `DRILL: PASS`, and `SET LOCAL ROLE familyroots_app` on the restored database returned
  `ERROR:  role "familyroots_app" does not exist`. The schema, the 13 RLS-enabled tables and all 17
  policies restore intact; the role and its 72 grant rows do not. **Recovery into a new cluster
  therefore needs a role-and-grant bootstrap that nothing in this repository performs today**, and
  dropping `--no-privileges` alone makes `pg_restore` fail outright rather than fixing it. The
  repair is a separate seed, because "should this repository dump roles at all" is a decision. Full
  evidence in
  [the fresh-cluster run](#the-2026-08-22-fresh-cluster-run-a-dump-at-head-into-a-cluster-with-no-familyroots_app-role).
- **No drill against a production dump.** All three recorded results ran against local dev data.
  The 2026-07-14 and 2026-08-22 (first) rows also ran against a dump at
  `016_document_soft_delete`, so only the third row exercises the current schema.
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
