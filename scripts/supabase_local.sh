#!/usr/bin/env bash
# The local Supabase stack: auth (GoTrue) + Storage, beside `pgdb`, not instead of it.
# Full prose, costs and traps: docs/ops/local-supabase.md. Read that before changing this.
#
# Usage:
#   scripts/supabase_local.sh up        start the stack and WAIT until every container is healthy
#   scripts/supabase_local.sh down      stop it, keeping a backup of the Supabase database
#   scripts/supabase_local.sh destroy   stop it and DELETE the Supabase database (auth.users included)
#   scripts/supabase_local.sh wait      assert every container is healthy, without starting anything
#   scripts/supabase_local.sh status    the CLI's own status output
#   scripts/supabase_local.sh env       the three backend variables, ready to paste into .env
#
# Why a wrapper and not plain `supabase start`:
#   `supabase start` gives supabase_storage_* three 10-second health probes and no start
#   period. Measured 2026-08-22 on this repo's dev machine, storage-api v1.69.11 takes about
#   31 seconds to bind its port, so the CLI declares it unhealthy and tears the whole stack
#   down, every time, on a stack that is in fact fine ten seconds later. `up` therefore
#   passes --ignore-health-check and then asserts health itself, on a longer clock. The
#   assertion is not skipped; only the CLI's too-short window is.
set -euo pipefail

# Pin the CLI. No global install: npx fetches this exact version, so a developer's machine
# and CI run the same one. Bump deliberately, and re-measure the numbers in the ops doc.
SUPABASE_CLI_VERSION="2.115.0"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_ID="familyroots"          # supabase/config.toml:5 (container name suffix)
HEALTH_TIMEOUT_SECONDS="${SUPABASE_HEALTH_TIMEOUT:-240}"

supa() { npx --yes "supabase@${SUPABASE_CLI_VERSION}" --workdir "$ROOT_DIR" "$@"; }

# The four containers this product cannot work without. Named explicitly, because asking
# "is everything I can see healthy?" is not the same question as "is the stack up": `docker ps`
# lists only RUNNING containers, so a stopped one silently leaves the set and the answer comes
# back yes. That defect was in this script, and stopping supabase_auth_familyroots on 2026-08-22
# still printed "all containers healthy". Assert the roster, then assert its health.
REQUIRED_SERVICES=(db auth kong storage)

container_state() {  # running | exited | absent
  docker inspect "$1" --format '{{.State.Status}}' 2>/dev/null || echo absent
}

health_state() {     # healthy | starting | unhealthy | none
  docker inspect "$1" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' 2>/dev/null || echo none
}

wait_for_health() {
  local deadline=$(( SECONDS + HEALTH_TIMEOUT_SECONDS ))
  local bad name state health roster
  while :; do
    bad=""

    # 1. The roster: every required service must exist and be running.
    for svc in "${REQUIRED_SERVICES[@]}"; do
      name="supabase_${svc}_${PROJECT_ID}"
      state="$(container_state "$name")"
      [ "$state" = "running" ] || bad="${bad}  ${name}: ${state}"$'\n'
    done

    # 2. Health: every supabase container that exists, required or not. A container with no
    #    healthcheck reports "none"; that is not a failure.
    roster="$(docker ps -a --filter "name=supabase_.*_${PROJECT_ID}$" --format '{{.Names}}')"
    while read -r name; do
      [ -n "$name" ] || continue
      state="$(container_state "$name")"
      health="$(health_state "$name")"
      if [ "$state" != "running" ]; then
        case "$bad" in *"  ${name}: "*) ;; *) bad="${bad}  ${name}: ${state}"$'\n' ;; esac
      elif [ "$health" != "healthy" ] && [ "$health" != "none" ]; then
        bad="${bad}  ${name}: ${health}"$'\n'
      fi
    done <<< "$roster"

    if [ -z "$bad" ]; then
      echo "supabase_local: all containers healthy."
      docker ps -a --filter "name=supabase_.*_${PROJECT_ID}$" --format '  {{.Names}}\t{{.Status}}'
      return 0
    fi
    if [ "$SECONDS" -ge "$deadline" ]; then
      echo "supabase_local: not healthy after ${HEALTH_TIMEOUT_SECONDS}s:" >&2
      printf '%s' "$bad" >&2
      echo "  logs: docker logs supabase_storage_${PROJECT_ID}" >&2
      return 1
    fi
    sleep 5
  done
}

case "${1:-}" in
  up)
    supa start --ignore-health-check
    wait_for_health
    ;;
  down)
    supa stop
    ;;
  destroy)
    # --no-backup DELETES the Supabase database. Every auth.users row goes with it, and
    # S-073's seeding has to run again. `down` is the one you usually want.
    supa stop --no-backup
    ;;
  wait)
    # The health assertion on its own. `up` runs it; CI can run it after a restart, and it is
    # how you prove the assertion can fail: stop a container, then run this.
    wait_for_health
    ;;
  status)
    supa status
    ;;
  env)
    # SUPABASE_URL is deliberately NOT the 127.0.0.1 that `supabase status` prints.
    # supabase/config.toml pins the token issuer to supabase.localhost so that one string
    # works from the macOS host and from inside a container. A 127.0.0.1 SUPABASE_URL
    # gives 401 invalid_token against a perfectly healthy stack.
    echo "SUPABASE_URL=http://supabase.localhost:54321"
    supa status -o env 2>/dev/null | sed -n 's/^ANON_KEY=/SUPABASE_ANON_KEY=/p;s/^SERVICE_ROLE_KEY=/SUPABASE_SERVICE_ROLE_KEY=/p'
    ;;
  *)
    sed -n '2,15p' "${BASH_SOURCE[0]}"
    exit 2
    ;;
esac
