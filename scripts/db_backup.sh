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
if [ -n "${BACKUP_TMPDIR:-}" ]; then
  mkdir -p "$TMPDIR_LOCAL"
fi
DUMP_PATH="${TMPDIR_LOCAL}/${NAME}"

echo "==> $(pg_dump --version) at $(command -v pg_dump), custom format -> ${DUMP_PATH}"
# Strip any SQLAlchemy-style +driver suffix (e.g. +psycopg, +asyncpg) if present;
# pg_dump wants a plain postgresql:// scheme (equivalent of scheme.split("+", 1)[0]).
CLEAN_URL="$(printf '%s' "$DATABASE_URL" | sed -E 's#^([a-z]+)\+[a-z0-9]+://#\1://#')"
pg_dump --format=custom --no-owner --no-privileges "$CLEAN_URL" | gzip > "$DUMP_PATH"
SIZE_BYTES=$(wc -c < "$DUMP_PATH" | tr -d ' ')
echo "==> dump size: ${SIZE_BYTES} bytes"
if [ "$SIZE_BYTES" -gt 419430400 ]; then
  echo "::warning::backup exceeds 400MB — review Supabase Storage limits/plan"
fi
if [ "$SIZE_BYTES" -lt 1024 ]; then
  echo "::error::dump suspiciously small (<1KB) — treating as failure"; exit 1
fi

# Integrity checks on the exact file about to be uploaded. Any failure exits
# before upload and rotation, so a damaged dump never displaces a good one.
echo "==> verifying with $(pg_restore --version) at $(command -v pg_restore)"
if ! gzip -t "$DUMP_PATH"; then
  echo "::error::check 1 failed (gzip -t): gzip stream is damaged"; exit 1
fi
echo "==> check 1 ok: gzip -t"
# Full read of the archive: --list reads only the TOC and passes a truncated one.
if ! gunzip -c "$DUMP_PATH" | pg_restore --file=/dev/null; then
  echo "::error::check 2 failed (pg_restore full read): archive is truncated or unreadable"; exit 1
fi
echo "==> check 2 ok: pg_restore full read"
# Capture first: under pipefail, grep -q closing the pipe early could fail the pipeline.
TOC="$(gunzip -c "$DUMP_PATH" | pg_restore --list)" || {
  echo "::error::check 3 failed (pg_restore --list): cannot read the table of contents"; exit 1; }
if ! printf '%s\n' "$TOC" | grep -Eq 'TABLE DATA public alembic_version([[:space:]]|$)'; then
  echo "::error::check 3 failed (TOC): no 'TABLE DATA public alembic_version' entry, dump lacks the application schema and rows"; exit 1
fi
echo "==> check 3 ok: TOC lists TABLE DATA public alembic_version"

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
  # limit:1000 with no pagination loop: rotation (keep 7 daily / 4 weekly) means
  # this prefix never holds more than a handful of objects, so the bucket never
  # approaches the 1000-object page size — no pagination is needed here.
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
      # Supabase Storage's list response shape (leaf name vs. full "$1/name"
      # path) is unverified until go-live; strip any leading prefix so both
      # shapes rebuild the same correct delete key instead of double-prefixing.
      n="${n#"$1"/}"
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
