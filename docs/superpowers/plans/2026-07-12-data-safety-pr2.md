# Data Safety PR2 Implementation Plan — Automated DB Backup + Tested Restore

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A nightly, off-provider database backup (GitHub Actions → Supabase Storage) with rotation, plus a restore-drill script executed for real and a runbook that documents actuals instead of targets.

**Architecture:** Spec = `docs/superpowers/specs/2026-07-12-data-safety-design.md` (PR2 section). Backup logic lives in a testable `scripts/db_backup.sh` (pg_dump -Fc → gzip → Supabase Storage REST upload → rotation 7 daily + 4 weekly); a thin `.github/workflows/db-backup.yml` runs it nightly (00:15 VN) + on demand, exiting neutrally when secrets are absent. `scripts/restore_drill.sh` restores a dump into a scratch DB on local pgdb and smoke-verifies; it is RUN FOR REAL once in this PR and the result logged in the rewritten `docs/ops/backup-restore.md`.

**Tech Stack:** bash + curl + pg_dump/pg_restore (postgres client), GitHub Actions, Supabase Storage REST API. No backend code changes.

## Global Constraints

- Backend code untouched — but still run the full gate once at the end (regression proof): `cd backend && uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports`.
- Both scripts must pass shellcheck: `uvx --from shellcheck-py shellcheck scripts/db_backup.sh scripts/restore_drill.sh` (if `uvx --from` fails, `brew install shellcheck` is acceptable — record which was used).
- Scripts are `set -euo pipefail`, executable (`chmod +x`), with `--help`.
- Secrets (documented, added by owner at go-live): `PROD_DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`. The workflow MUST exit 0 with a clear `::notice::` when they are absent (forks/CI stay green).
- Storage layout: bucket `backups` (private), objects `db/daily/familyroots-YYYY-MM-DD.dump.gz` and `db/weekly/familyroots-YYYY-MM-DD.dump.gz`; retention: newest 7 daily, newest 4 weekly (weekly = Sundays, VN time).
- Local Postgres for the drill: `docker compose up -d pgdb` (user/pass `postgres`/`postgres`, db `family_roots`, port 5432 — compose defaults).
- Never `git add -A`.

---

### Task 1: `scripts/db_backup.sh` + `.github/workflows/db-backup.yml`

**Files:**
- Create: `scripts/db_backup.sh`
- Create: `.github/workflows/db-backup.yml`
- Test: manual + shellcheck (Step 4) — no pytest surface.

**Interfaces:**
- Produces: `db_backup.sh` env-driven: requires `DATABASE_URL`; `SUPABASE_URL`+`SUPABASE_SERVICE_ROLE_KEY` required unless `--dry-run`. Flags: `--dry-run` (dump+gzip to `$BACKUP_TMPDIR` or mktemp, print what WOULD upload/rotate, no network to Supabase), `--help`. Exit non-zero on any failure (workflow surfaces red).

- [ ] **Step 1: Write `scripts/db_backup.sh`**

```bash
#!/usr/bin/env bash
# Nightly off-provider DB backup: pg_dump -Fc | gzip -> Supabase Storage `backups`
# bucket, with rotation (keep newest 7 daily; Sundays also copy to weekly, keep 4).
# Runs from GitHub Actions (see .github/workflows/db-backup.yml) or locally.
#
# Required env: DATABASE_URL; and (unless --dry-run) SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY.
# Layout: backups/db/daily/familyroots-YYYY-MM-DD.dump.gz (+ db/weekly/ on Sundays).
set -euo pipefail

DRY_RUN=false
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    --help)
      grep '^#' "$0" | sed 's/^# \{0,1\}//' ; exit 0 ;;
    *) echo "unknown arg: $arg" >&2; exit 2 ;;
  esac
done

: "${DATABASE_URL:?DATABASE_URL is required}"
if [ "$DRY_RUN" = false ]; then
  : "${SUPABASE_URL:?SUPABASE_URL is required}"
  : "${SUPABASE_SERVICE_ROLE_KEY:?SUPABASE_SERVICE_ROLE_KEY is required}"
fi

BUCKET="backups"
TODAY="$(TZ=Asia/Ho_Chi_Minh date +%F)"
DOW="$(TZ=Asia/Ho_Chi_Minh date +%u)"   # 7 = Sunday
NAME="familyroots-${TODAY}.dump.gz"
TMPDIR_LOCAL="${BACKUP_TMPDIR:-$(mktemp -d)}"
DUMP_PATH="${TMPDIR_LOCAL}/${NAME}"

echo "==> pg_dump (custom format) -> ${DUMP_PATH}"
# Strip a SQLAlchemy-style +psycopg driver suffix if present; pg_dump wants plain postgresql://
CLEAN_URL="${DATABASE_URL/postgresql+psycopg:\/\//postgresql:\/\/}"
pg_dump --format=custom --no-owner --no-privileges "$CLEAN_URL" | gzip > "$DUMP_PATH"
SIZE_BYTES=$(wc -c < "$DUMP_PATH" | tr -d ' ')
echo "==> dump size: ${SIZE_BYTES} bytes"
if [ "$SIZE_BYTES" -gt 419430400 ]; then
  echo "::warning::backup exceeds 400MB — review Supabase Storage limits/plan"
fi
if [ "$SIZE_BYTES" -lt 1024 ]; then
  echo "::error::dump suspiciously small (<1KB) — treating as failure"; exit 1
fi

storage_upload() {  # $1 = object path (e.g. db/daily/NAME)
  curl -sSf -X POST \
    -H "Authorization: Bearer ${SUPABASE_SERVICE_ROLE_KEY}" \
    -H "apikey: ${SUPABASE_SERVICE_ROLE_KEY}" \
    -H "Content-Type: application/gzip" \
    -H "x-upsert: true" \
    --data-binary @"${DUMP_PATH}" \
    "${SUPABASE_URL}/storage/v1/object/${BUCKET}/$1" > /dev/null
  echo "==> uploaded ${BUCKET}/$1"
}

storage_list_names() {  # $1 = prefix (db/daily). Prints one object name per line, oldest first.
  curl -sSf -X POST \
    -H "Authorization: Bearer ${SUPABASE_SERVICE_ROLE_KEY}" \
    -H "apikey: ${SUPABASE_SERVICE_ROLE_KEY}" \
    -H "Content-Type: application/json" \
    -d "{\"prefix\":\"$1\",\"limit\":1000,\"sortBy\":{\"column\":\"name\",\"order\":\"asc\"}}" \
    "${SUPABASE_URL}/storage/v1/object/list/${BUCKET}" \
    | python3 -c 'import json,sys; [print(o["name"]) for o in json.load(sys.stdin) if o.get("name")]'
}

storage_delete() {  # $1 = object path
  curl -sSf -X DELETE \
    -H "Authorization: Bearer ${SUPABASE_SERVICE_ROLE_KEY}" \
    -H "apikey: ${SUPABASE_SERVICE_ROLE_KEY}" \
    "${SUPABASE_URL}/storage/v1/object/${BUCKET}/$1" > /dev/null
  echo "==> pruned ${BUCKET}/$1"
}

rotate() {  # $1 = prefix (db/daily) ; $2 = keep count
  local names count_to_delete
  names="$(storage_list_names "$1")"
  count_to_delete=$(( $(echo "$names" | grep -c . || true) - $2 ))
  if [ "$count_to_delete" -gt 0 ]; then
    echo "$names" | head -n "$count_to_delete" | while read -r n; do
      storage_delete "$1/$n"
    done
  fi
}

if [ "$DRY_RUN" = true ]; then
  echo "==> DRY RUN: would upload db/daily/${NAME}$( [ "$DOW" = 7 ] && echo ' and db/weekly/'"${NAME}" )"
  echo "==> DRY RUN: would rotate db/daily keep 7$( [ "$DOW" = 7 ] && echo '; db/weekly keep 4' )"
  exit 0
fi

storage_upload "db/daily/${NAME}"
rotate "db/daily" 7
if [ "$DOW" = 7 ]; then
  storage_upload "db/weekly/${NAME}"
  rotate "db/weekly" 4
fi
echo "==> backup complete: ${NAME}"
```

Note: object names are date-stamped `familyroots-YYYY-MM-DD.dump.gz`, so lexicographic `name asc` == chronological — `rotate` deletes oldest-first correctly. Verify the list-endpoint response shape against Supabase Storage docs if the python filter errors (objects come back as a JSON array of `{"name": ...}`).

- [ ] **Step 2: Write `.github/workflows/db-backup.yml`**

```yaml
name: db-backup
on:
  schedule:
    - cron: "15 17 * * *"   # 17:15 UTC = 00:15 Asia/Ho_Chi_Minh
  workflow_dispatch: {}

permissions:
  contents: read

jobs:
  backup:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4
      - name: Check secrets
        id: gate
        env:
          PROD_DATABASE_URL: ${{ secrets.PROD_DATABASE_URL }}
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
        run: |
          if [ -z "$PROD_DATABASE_URL" ] || [ -z "$SUPABASE_URL" ] || [ -z "$SUPABASE_SERVICE_ROLE_KEY" ]; then
            echo "::notice::db-backup secrets not configured — skipping (see docs/ops/backup-restore.md go-live checklist)"
            echo "configured=false" >> "$GITHUB_OUTPUT"
          else
            echo "configured=true" >> "$GITHUB_OUTPUT"
          fi
      - name: Install postgres client
        if: steps.gate.outputs.configured == 'true'
        run: sudo apt-get update -qq && sudo apt-get install -y -qq postgresql-client
      - name: Run backup
        if: steps.gate.outputs.configured == 'true'
        env:
          DATABASE_URL: ${{ secrets.PROD_DATABASE_URL }}
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
        run: bash scripts/db_backup.sh
```

- [ ] **Step 3: Local verification (REAL, against docker pgdb)**

Run (from repo root, pgdb up):
```bash
DATABASE_URL="postgresql://postgres:postgres@localhost:5432/family_roots" BACKUP_TMPDIR=/tmp/fr-backup-test bash scripts/db_backup.sh --dry-run
```
Expected: dump file created, size printed, DRY RUN lines, exit 0. Record the output in your report. Also verify `--help` prints the header and a bad flag exits 2.

- [ ] **Step 4: shellcheck both paths**

Run: `uvx --from shellcheck-py shellcheck scripts/db_backup.sh` → no findings (fix any SC warnings properly, don't disable without a reason comment). Validate the workflow YAML parses: `python3 -c "import yaml,sys; yaml.safe_load(open('.github/workflows/db-backup.yml'))"`.

- [ ] **Step 5: Commit**

```bash
git add scripts/db_backup.sh .github/workflows/db-backup.yml
git commit -m "feat(ops): nightly off-provider DB backup — pg_dump to Supabase Storage with rotation"
```

---

### Task 2: `scripts/restore_drill.sh` + REAL drill run

**Files:**
- Create: `scripts/restore_drill.sh`
- Test: the drill itself, executed for real against a dump of the local dev DB (Step 3) — output recorded for Task 3's runbook.

**Interfaces:**
- Produces: `restore_drill.sh <dump.gz>` (or `--latest` to download the newest `db/daily/` object — requires SUPABASE_URL/SERVICE_ROLE_KEY). Restores into scratch DB `familyroots_restore_drill` on `PGHOST:PGPORT` (default localhost:5432, postgres/postgres), then verifies: (1) `alembic_version` present and matching `uv run alembic heads` (warn-not-fail if behind — an old dump is still a valid backup); (2) row-count smoke report for clans/persons/clan_memberships/marriages/parent_child/events/documents; (3) one recursive tree query (`SELECT count(*) FROM get_family_tree_flat(<any founder or any person id>, <its clan>, 5)`) executes without error — skip gracefully with a WARN if the DB has no persons. Prints a final `DRILL: PASS` / `DRILL: FAIL` line and exits 0/1 accordingly. Idempotent: drops the scratch DB first (`WITH (FORCE)`).

- [ ] **Step 1: Write the script** — structure:

```bash
#!/usr/bin/env bash
# Restore drill: prove a backup dump actually restores (docs/ops/backup-restore.md).
# Usage: restore_drill.sh <dump.gz> | --latest    (never touches production)
set -euo pipefail
# arg parsing (--latest downloads newest db/daily object via the same curl+python
# list call as db_backup.sh, then proceeds identically)
# PGADMIN_DSN="postgresql://postgres:postgres@${PGHOST:-localhost}:${PGPORT:-5432}/postgres"
# psql "$PGADMIN_DSN" -c 'DROP DATABASE IF EXISTS familyroots_restore_drill WITH (FORCE)'
# psql "$PGADMIN_DSN" -c 'CREATE DATABASE familyroots_restore_drill'
# gunzip -c "$DUMP" | pg_restore --no-owner --no-privileges -d "$SCRATCH_DSN"
# checks 1-3 via psql -tA; accumulate FAILURES counter; print report table;
# final PASS/FAIL line; exit accordingly
```

Write it fully (the report-table format is yours to design; keep it plain text). Reuse the `storage_list_names`-style curl for `--latest` (duplicate the small function — two standalone scripts beat a shared lib for ops tooling).

- [ ] **Step 2: shellcheck** — same command as Task 1; clean.

- [ ] **Step 3: RUN THE DRILL FOR REAL** (this is the point of the PR):

```bash
docker compose up -d pgdb
DATABASE_URL="postgresql://postgres:postgres@localhost:5432/family_roots" BACKUP_TMPDIR=/tmp/fr-drill bash -c 'pg_dump --format=custom --no-owner "$DATABASE_URL" | gzip > /tmp/fr-drill/familyroots-manual.dump.gz'   # or run db_backup.sh --dry-run and reuse its artifact
bash scripts/restore_drill.sh /tmp/fr-drill/familyroots-manual.dump.gz
```
Expected: `DRILL: PASS` with the report table (alembic head match, row counts ≥0, tree query ok/skip). Capture the FULL output verbatim in your report — Task 3 pastes it into the runbook's drill log. If the local dev DB is empty, counts of 0 + tree-skip WARN are acceptable and should be visible in the log.

- [ ] **Step 4: Commit**

```bash
git add scripts/restore_drill.sh
git commit -m "feat(ops): restore drill script — scratch-DB restore + schema/smoke verification"
```

---

### Task 3: Runbook rewrite + doc rows

**Files:**
- Modify: `docs/ops/backup-restore.md` (rewrite from "target" to ACTUAL — keep the still-deferred items honest)
- Modify: `docs/ops/deployment.md` (workflow table: add db-backup.yml row)
- Modify: `docs/ops/secrets.md` (3 new GitHub secrets rows) and `docs/ops/configuration.md` only if it has a secrets cross-reference section (read first)
- Modify: `docs/architecture/notifications-scheduler.md` — NO (job is GitHub-side, not APScheduler; do not touch)
- Test: none — backend full gate once as regression evidence.

**Interfaces:** Documents Tasks 1-2 actuals; the drill log from Task 2's report goes in verbatim.

- [ ] **Step 1: Rewrite `docs/ops/backup-restore.md`:** replace the ⚠️ CURRENT STATE banner with "ACTIVE since 2026-07-12" facts: what runs (workflow, schedule 00:15 VN, layout, rotation 7d/4w), RPO 24h / RTO ~1h manual, how to run on demand (workflow_dispatch / locally), restore procedure = `scripts/restore_drill.sh` (usage), **Drill log table** with the real Task-2 run (date, dump, result PASS, notes), quarterly drill cadence, **Go-live checklist** (create private `backups` bucket; add PROD_DATABASE_URL + SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY GitHub secrets; run workflow_dispatch once; run the drill against that first prod dump; verify rotation after 8 days), and the honest still-deferred list (Render-plan PITR verification; document-blob bucket mirroring; admin-succession runbook).
- [ ] **Step 2: deployment.md + secrets.md rows** per Files list (read each file's table format first).
- [ ] **Step 3: Backend full gate** (regression evidence — no backend files changed): from backend/, the 5 commands. Plus re-run shellcheck on both scripts.
- [ ] **Step 4: Commit**

```bash
git add docs/ops/backup-restore.md docs/ops/deployment.md docs/ops/secrets.md
git commit -m "docs(ops): backup-restore runbook — actuals, drill log, go-live checklist"
```
