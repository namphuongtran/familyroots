#!/usr/bin/env bash
# Reads the web's production host after the web deploy (release.yml, #404).
# Inputs (env): WEB_ORIGIN (production host), DEPLOYMENT_URL (printed by the deploy step),
# VERCEL_TOKEN. Passes only when (1) the production host is an alias of the deployment this
# run made and (2) /login answers 200. Check 1 is the one a status-only read cannot make:
# a production alias still on the previous deployment also answers 200.
set -uo pipefail

origin="${WEB_ORIGIN%/}"
host="${origin#*://}"; host="${host%%:*}"; host="${host%%/*}"
deployment="${DEPLOYMENT_URL:?DEPLOYMENT_URL is empty}"
vercel_cli="${VERCEL_CLI:-pnpm dlx vercel@63.1.0}"

fail() {
  echo "::error::$1. Production already serves the new web deployment: roll back (docs/ops/deployment.md, Rollback)"
  exit 1
}

# One read per run: `vercel inspect` lists the deployment's aliases.
inspected="$($vercel_cli inspect "$deployment" --token="$VERCEL_TOKEN" 2>&1)" || true
echo "$inspected"
if ! printf '%s\n' "$inspected" | grep -Eq "(^|[^A-Za-z0-9.-])(https://)?${host//./\\.}([^A-Za-z0-9.-]|$)"; then
  fail "Production host $host is not an alias of the deployment this run made ($deployment), so it serves another deployment"
fi
echo "serves this deployment: $host is an alias of $deployment"

url="$origin/login"
body="$(mktemp)"
for attempt in 1 2 3 4 5 6; do
  status="$(curl -sS --max-time 60 -o "$body" -w '%{http_code}' "$url" || true)"
  echo "attempt $attempt: GET $url -> ${status:-no answer}"
  if [ "$status" = "200" ]; then
    exit 0
  fi
  [ "$attempt" = 6 ] || sleep "${RETRY_SLEEP:-10}"
done
echo "Last body:"; head -c 2000 "$body"; echo
fail "GET $url answered ${status:-nothing} after 6 attempts"
