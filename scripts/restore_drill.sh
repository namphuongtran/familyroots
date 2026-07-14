#!/usr/bin/env bash
# Restore drill: prove a backup dump actually restores (docs/ops/backup-restore.md).
# Usage: restore_drill.sh <dump.gz> | --latest
#   <dump.gz>  path to a gzip-compressed pg_dump custom-format archive, e.g. the file
#              produced by scripts/db_backup.sh (or `pg_dump --format=custom | gzip`).
#   --latest   download the newest backups/db/daily/ object from Supabase Storage first
#              (requires SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY).
# Never touches production: restores into a scratch DB (familyroots_restore_drill) on
# PGHOST:PGPORT (default localhost:5432, user/password default postgres/postgres),
# dropping and recreating it first (idempotent — safe to re-run).
# Then verifies: (1) alembic_version vs `uv run alembic heads` (warn, not fail, if
# behind — an old dump is still a valid backup); (2) row-count smoke report for the
# core tables; (3) one get_family_tree_flat() call (skipped with a WARN if the
# restored DB has no persons). Prints DRILL: PASS or DRILL: FAIL and exits 0/1.
set -euo pipefail

DUMP_ARG=""
LATEST=false
for arg in "$@"; do
  case "$arg" in
    --help)
      grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    --latest)
      LATEST=true ;;
    -*)
      echo "unknown arg: $arg" >&2; exit 2 ;;
    *)
      if [ -n "$DUMP_ARG" ]; then
        echo "unknown arg: $arg" >&2; exit 2
      fi
      DUMP_ARG="$arg" ;;
  esac
done

if [ "$LATEST" = true ] && [ -n "$DUMP_ARG" ]; then
  echo "specify either <dump.gz> or --latest, not both" >&2; exit 2
fi
if [ "$LATEST" = false ] && [ -z "$DUMP_ARG" ]; then
  echo "usage: restore_drill.sh <dump.gz> | --latest" >&2; exit 2
fi

BUCKET="backups"
TMPDIR_LOCAL="${BACKUP_TMPDIR:-$(mktemp -d)}"
if [ -n "${BACKUP_TMPDIR:-}" ]; then
  mkdir -p "$TMPDIR_LOCAL"
fi

storage_list_names() {  # $1 = prefix (db/daily). Prints one object name per line, oldest first.
  curl -sSf -X POST \
    -H "Authorization: Bearer ${SUPABASE_SERVICE_ROLE_KEY}" \
    -H "apikey: ${SUPABASE_SERVICE_ROLE_KEY}" \
    -H "Content-Type: application/json" \
    -d "{\"prefix\":\"$1\",\"limit\":1000,\"sortBy\":{\"column\":\"name\",\"order\":\"asc\"}}" \
    "${SUPABASE_URL}/storage/v1/object/list/${BUCKET}" \
    | python3 -c 'import json,sys; [print(o["name"]) for o in json.load(sys.stdin) if o.get("name")]'
}

storage_download() {  # $1 = object path (e.g. db/daily/NAME), $2 = local dest path
  curl -sSf \
    -H "Authorization: Bearer ${SUPABASE_SERVICE_ROLE_KEY}" \
    -H "apikey: ${SUPABASE_SERVICE_ROLE_KEY}" \
    "${SUPABASE_URL}/storage/v1/object/${BUCKET}/$1" -o "$2"
  echo "==> downloaded ${BUCKET}/$1 -> $2"
}

if [ "$LATEST" = true ]; then
  : "${SUPABASE_URL:?SUPABASE_URL is required for --latest}"
  : "${SUPABASE_SERVICE_ROLE_KEY:?SUPABASE_SERVICE_ROLE_KEY is required for --latest}"
  echo "==> looking up newest db/daily object"
  names="$(storage_list_names "db/daily")"
  latest_name="$(echo "$names" | tail -n 1)"
  if [ -z "$latest_name" ]; then
    echo "::error::no objects found under db/daily/ in bucket ${BUCKET}" >&2
    exit 1
  fi
  DUMP_ARG="${TMPDIR_LOCAL}/${latest_name}"
  storage_download "db/daily/${latest_name}" "$DUMP_ARG"
fi

DUMP="$DUMP_ARG"
if [ ! -f "$DUMP" ]; then
  echo "::error::dump file not found: $DUMP" >&2
  exit 1
fi

PGHOST_="${PGHOST:-localhost}"
PGPORT_="${PGPORT:-5432}"
PGUSER_="${PGUSER:-postgres}"
PGPASSWORD_="${PGPASSWORD:-postgres}"
SCRATCH_DB="familyroots_restore_drill"
ADMIN_DSN="postgresql://${PGUSER_}:${PGPASSWORD_}@${PGHOST_}:${PGPORT_}/postgres"
SCRATCH_DSN="postgresql://${PGUSER_}:${PGPASSWORD_}@${PGHOST_}:${PGPORT_}/${SCRATCH_DB}"

echo "==> dropping scratch DB if it exists: ${SCRATCH_DB}"
psql "$ADMIN_DSN" -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS ${SCRATCH_DB} WITH (FORCE)"
echo "==> creating scratch DB: ${SCRATCH_DB}"
psql "$ADMIN_DSN" -v ON_ERROR_STOP=1 -c "CREATE DATABASE ${SCRATCH_DB}"

echo "==> restoring ${DUMP} -> ${SCRATCH_DB}"
FAILURES=0
if gunzip -c "$DUMP" | pg_restore --no-owner --no-privileges -d "$SCRATCH_DSN"; then
  echo "==> pg_restore completed"
else
  echo "::error::pg_restore failed"
  echo "DRILL: FAIL"
  exit 1
fi

 # --- Check 1: alembic head (warn-not-fail - an old dump is still a valid backup) ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "==> checking alembic head"
db_version="$(psql "$SCRATCH_DSN" -tA -c 'SELECT version_num FROM alembic_version' 2>/dev/null || true)"
db_version="$(echo "$db_version" | tr -d '[:space:]')"
repo_head=""
if [ -d "${REPO_ROOT}/backend" ]; then
  repo_head="$(cd "${REPO_ROOT}/backend" && uv run alembic heads 2>/dev/null | head -n 1 | awk '{print $1}')"
fi

alembic_line=""
if [ -z "$db_version" ]; then
  alembic_line="WARN — alembic_version table not found/empty in restored dump"
elif [ -z "$repo_head" ]; then
  alembic_line="WARN — could not determine repo alembic head (backend/ or uv unavailable); dump reports ${db_version}"
elif [ "$db_version" = "$repo_head" ]; then
  alembic_line="OK   — dump at ${db_version}, matches repo head"
else
  alembic_line="WARN — dump at ${db_version}, repo head is ${repo_head} (dump predates head; not a failure)"
fi
echo "  ${alembic_line}"

 # --- Check 2: row-count smoke report ------------------------------------------------
echo "==> row-count smoke report"
ROW_REPORT=""
for t in clans persons clan_memberships marriages parent_child events documents; do
  cnt="$(psql "$SCRATCH_DSN" -tA -c "SELECT count(*) FROM ${t}" 2>&1)"
  if [[ "$cnt" =~ ^[0-9]+$ ]]; then
    line="$(printf '  %-20s %s' "$t" "$cnt")"
  else
    line="$(printf '  %-20s ERROR: %s' "$t" "$cnt")"
    FAILURES=$((FAILURES + 1))
  fi
  echo "$line"
  ROW_REPORT="${ROW_REPORT}${line}"$'\n'
done

 # --- Check 3: tree query (get_family_tree_flat) - skip gracefully if no persons ----
echo "==> tree query check (get_family_tree_flat)"
person_row="$(psql "$SCRATCH_DSN" -tA -F'|' \
  -c "SELECT id, created_by_clan_id FROM persons WHERE is_deleted = false AND created_by_clan_id IS NOT NULL LIMIT 1" \
  2>&1)"
if [ -z "$person_row" ]; then
  tree_line="WARN — no persons with a clan in restored DB; tree query skipped"
else
  person_id="${person_row%%|*}"
  clan_id="${person_row##*|}"
  tree_count="$(psql "$SCRATCH_DSN" -tA \
    -c "SELECT count(*) FROM get_family_tree_flat('${person_id}', '${clan_id}', 5)" 2>&1)"
  if [[ "$tree_count" =~ ^[0-9]+$ ]]; then
    tree_line="OK   — get_family_tree_flat returned ${tree_count} row(s) for person ${person_id}"
  else
    tree_line="FAIL — ${tree_count}"
    FAILURES=$((FAILURES + 1))
  fi
fi
echo "  ${tree_line}"

 # --- Report table -------------------------------------------------------------------
echo ""
echo "===== Restore Drill Report ====="
echo "dump:        ${DUMP}"
echo "scratch db:  ${SCRATCH_DB} @ ${PGHOST_}:${PGPORT_}"
echo "alembic:     ${alembic_line}"
echo "row counts:"
printf '%s' "$ROW_REPORT"
echo "tree query:  ${tree_line}"
echo "================================="

if [ "$FAILURES" -eq 0 ]; then
  echo "DRILL: PASS"
  exit 0
else
  echo "DRILL: FAIL (${FAILURES} check(s) failed)"
  exit 1
fi
