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
# After the restore it runs scripts/restore_bootstrap_role.sql (ADR-052), which creates
# the cluster-wide familyroots_app role and re-grants what migrations 002 and 026 grant.
# A single-database dump carries neither, so without this step a restore into a new
# cluster yields a database the application cannot use.
# Then verifies: (1) alembic_version vs `uv run alembic heads` (warn, not fail, if
# behind — an old dump is still a valid backup); (2) row-count smoke report for the
# core tables; (3) one get_family_tree_flat() call (skipped with a WARN if the
# restored DB has no persons); (4) a request-role session — `SET LOCAL ROLE
# familyroots_app` plus the app.clan_id GUC, two-sided: the owning clan sees its
# persons and a clan that owns nothing sees 0. Check 4 is the one that makes
# DRILL: PASS mean the application can use the result; it FAILS, and names the role,
# when the bootstrap has not run. Prints DRILL: PASS or DRILL: FAIL and exits 0/1.
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
  # limit:1000 with no pagination loop: db_backup.sh's rotation (keep 7 daily /
  # 4 weekly) bounds this prefix to a handful of objects, so the bucket never
  # approaches the 1000-object page size — no pagination is needed here.
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
  # Supabase Storage's list response shape (leaf name vs. full "db/daily/name"
  # path) is unverified until go-live; strip any leading prefix so both shapes
  # rebuild the same correct download key instead of double-prefixing.
  latest_name="${latest_name#"db/daily"/}"
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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BOOTSTRAP_SQL="${SCRIPT_DIR}/restore_bootstrap_role.sql"
# Spelled out, not read from settings: migrations 002 and 026 spell it out too.
APP_ROLE="familyroots_app"

echo "==> dropping scratch DB if it exists: ${SCRATCH_DB}"
if ! psql "$ADMIN_DSN" -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS ${SCRATCH_DB} WITH (FORCE)"; then
  echo "::error::cannot reach Postgres at ${PGHOST_}:${PGPORT_} — is pgdb up?" >&2
  echo "DRILL: FAIL"
  exit 1
fi
echo "==> creating scratch DB: ${SCRATCH_DB}"
if ! psql "$ADMIN_DSN" -v ON_ERROR_STOP=1 -c "CREATE DATABASE ${SCRATCH_DB}"; then
  echo "::error::cannot reach Postgres at ${PGHOST_}:${PGPORT_} — is pgdb up?" >&2
  echo "DRILL: FAIL"
  exit 1
fi

echo "==> restoring ${DUMP} -> ${SCRATCH_DB}"
FAILURES=0
if gunzip -c "$DUMP" | pg_restore --no-owner --no-privileges --exit-on-error -d "$SCRATCH_DSN"; then
  echo "==> pg_restore completed"
else
  echo "::error::pg_restore failed"
  echo "DRILL: FAIL"
  exit 1
fi

 # --- Role bootstrap: the cluster role + its grants (ADR-052) ------------------------
# Runs AFTER pg_restore, because `GRANT ... ON ALL TABLES` needs the tables to exist.
# The current dumps are taken with --no-privileges, so nothing in the archive names the
# role and the restore itself does not need it. Idempotent: safe on a cluster that
# already holds the role, which is what a same-cluster drill hits.
echo "==> bootstrapping the ${APP_ROLE} role + grants (${BOOTSTRAP_SQL})"
if [ ! -f "$BOOTSTRAP_SQL" ]; then
  echo "::error::role bootstrap file not found: ${BOOTSTRAP_SQL}" >&2
  echo "DRILL: FAIL"
  exit 1
fi
if ! psql "$SCRATCH_DSN" -q -v ON_ERROR_STOP=1 -f "$BOOTSTRAP_SQL"; then
  echo "::error::role bootstrap failed — the restored database cannot serve a request-role session" >&2
  echo "DRILL: FAIL"
  exit 1
fi

 # --- Check 1: alembic head (warn-not-fail - an old dump is still a valid backup) ---
echo "==> checking alembic head"
db_version="$(psql "$SCRATCH_DSN" -tA -c 'SELECT version_num FROM alembic_version' 2>/dev/null || true)"
db_version="$(echo "$db_version" | tr -d '[:space:]')"
repo_head=""
if [ -d "${REPO_ROOT}/backend" ]; then
  repo_head="$(cd "${REPO_ROOT}/backend" && uv run alembic heads 2>/dev/null | head -n 1 | awk '{print $1}')" || true
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
  cnt="$(psql "$SCRATCH_DSN" -tA -c "SELECT count(*) FROM ${t}" 2>&1)" || true
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
  2>&1)" || true
if [[ ! "$person_row" =~ ^[0-9a-f-]{36}\|[0-9a-f-]{36}$ ]]; then
  tree_line="WARN — no persons with a clan in restored DB; tree query skipped"
else
  person_id="${person_row%%|*}"
  clan_id="${person_row##*|}"
  tree_count="$(psql "$SCRATCH_DSN" -tA \
    -c "SELECT count(*) FROM get_family_tree_flat('${person_id}', '${clan_id}', 5)" 2>&1)" || true
  if [[ "$tree_count" =~ ^[0-9]+$ ]]; then
    tree_line="OK   — get_family_tree_flat returned ${tree_count} row(s) for person ${person_id}"
  else
    tree_line="FAIL — ${tree_count}"
    FAILURES=$((FAILURES + 1))
  fi
fi
echo "  ${tree_line}"

 # --- Check 4: request-role session, two-sided (ADR-052) -----------------------------
# The first three checks all connect as the superuser that created the scratch DB, and a
# superuser bypasses RLS. This one drops to the role the request path actually uses
# (backend/app/core/rls.py:63) and asserts the OUTCOME rather than the grant count: the
# owning clan sees its persons, a clan that owns nothing sees none.
echo "==> request-role check (SET LOCAL ROLE ${APP_ROLE})"

app_role_persons() {  # $1 = uuid for app.clan_id. Prints psql output; last line = count on success.
  psql "$SCRATCH_DSN" -tA -q -v ON_ERROR_STOP=1 --single-transaction \
    -c "SET LOCAL ROLE ${APP_ROLE}" \
    -c "SELECT set_config('app.clan_id', '$1', true)" \
    -c "SELECT count(*) FROM persons" 2>&1
}
first_error() {  # $1 = psql output. Prints the first ERROR line, or the whole thing squashed.
  printf '%s\n' "$1" | grep -m1 'ERROR' || printf '%s' "$1" | tr '\n' ' '
}

role_present="$(psql "$SCRATCH_DSN" -tA \
  -c "SELECT count(*) FROM pg_roles WHERE rolname = '${APP_ROLE}'" 2>&1 | tr -d '[:space:]')"
if [ "$role_present" != "1" ]; then
  role_line="FAIL — role \"${APP_ROLE}\" does not exist in this cluster; every clan-scoped request would fail"
  FAILURES=$((FAILURES + 1))
else
  owner_clan="$(psql "$SCRATCH_DSN" -tA \
    -c "SELECT clan_id FROM clan_memberships GROUP BY clan_id ORDER BY count(*) DESC, clan_id LIMIT 1" \
    2>/dev/null | tr -d '[:space:]')" || true
  foreign_clan="00000000-0000-0000-0000-000000000000"
  if [ "$(psql "$SCRATCH_DSN" -tA -c "SELECT count(*) FROM clans WHERE id = '${foreign_clan}'" \
      2>/dev/null | tr -d '[:space:]')" != "0" ]; then
    foreign_clan="$(psql "$SCRATCH_DSN" -tA -c "SELECT gen_random_uuid()" 2>/dev/null | tr -d '[:space:]')"
  fi

  if [[ ! "$owner_clan" =~ ^[0-9a-f-]{36}$ ]]; then
    # No membership rows: isolation cannot be shown two-sided, but the role must still
    # be able to query at all — this is where a missing GRANT surfaces.
    probe_out="$(app_role_persons "$foreign_clan")" || true
    probe_n="$(printf '%s\n' "$probe_out" | tail -n 1 | tr -d '[:space:]')"
    if [[ "$probe_n" =~ ^[0-9]+$ ]]; then
      role_line="WARN — restored DB has no clan_memberships rows; ${APP_ROLE} can query persons, isolation not proven"
    else
      role_line="FAIL — $(first_error "$probe_out")"
      FAILURES=$((FAILURES + 1))
    fi
  else
    own_out="$(app_role_persons "$owner_clan")" || true
    own_n="$(printf '%s\n' "$own_out" | tail -n 1 | tr -d '[:space:]')"
    foreign_out="$(app_role_persons "$foreign_clan")" || true
    foreign_n="$(printf '%s\n' "$foreign_out" | tail -n 1 | tr -d '[:space:]')"
    if [[ ! "$own_n" =~ ^[0-9]+$ ]]; then
      role_line="FAIL — $(first_error "$own_out")"
      FAILURES=$((FAILURES + 1))
    elif [[ ! "$foreign_n" =~ ^[0-9]+$ ]]; then
      role_line="FAIL — $(first_error "$foreign_out")"
      FAILURES=$((FAILURES + 1))
    elif [ "$own_n" -eq 0 ]; then
      role_line="FAIL — ${APP_ROLE} sees 0 persons under owning clan ${owner_clan}, which has memberships"
      FAILURES=$((FAILURES + 1))
    elif [ "$foreign_n" -ne 0 ]; then
      role_line="FAIL — clan isolation broken: ${foreign_n} person(s) visible under clan ${foreign_clan}, which owns nothing"
      FAILURES=$((FAILURES + 1))
    else
      role_line="OK   — ${APP_ROLE} sees ${own_n} person(s) under clan ${owner_clan}, ${foreign_n} under a clan that owns nothing"
    fi
  fi
fi
echo "  ${role_line}"

 # --- Report table -------------------------------------------------------------------
echo ""
echo "===== Restore Drill Report ====="
echo "dump:        ${DUMP}"
echo "scratch db:  ${SCRATCH_DB} @ ${PGHOST_}:${PGPORT_}"
echo "alembic:     ${alembic_line}"
echo "row counts:"
printf '%s' "$ROW_REPORT"
echo "tree query:  ${tree_line}"
echo "request role: ${role_line}"
echo "================================="

if [ "$FAILURES" -eq 0 ]; then
  echo "DRILL: PASS"
  exit 0
else
  echo "DRILL: FAIL (${FAILURES} check(s) failed)"
  exit 1
fi
