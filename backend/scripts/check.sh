#!/usr/bin/env bash
# The backend gate: format → lint → import contracts → types → tests.
#
# CI (backend-ci.yml) runs exactly this script, so a branch that fails CI fails
# here and vice versa — no uvx-vs-uv drift, no forgotten step. All tools run
# from the locked virtualenv (`uv run`), never a floating latest version.
#
# Every step runs even if an earlier one fails (a format error must not hide a
# type error), and each exit code is checked individually — no chaining that
# could mask a failure.
#
# Integration tests need Postgres: `docker compose up -d pgdb` from the repo
# root (CI provides its own service container).
#
# Known divergence: env vars. CI sets DATABASE_URL / APP_ENV=testing /
# APP_SECRET_KEY on the workflow step; locally the suite reads your shell and
# backend/.env. The commands are identical — the environment is yours.
#
# Usage: scripts/check.sh [extra pytest args...]

set -u
cd "$(dirname "$0")/.." || exit 1

PYTEST_EXTRA=("$@")
failed=()

step() {
  local name="$1"
  shift
  echo
  echo "━━ ${name} ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  if "$@"; then
    echo "✓ ${name}"
  else
    echo "✗ ${name} FAILED"
    failed+=("${name}")
  fi
}

step "format (ruff format --check)" uv run ruff format --check .
step "lint (ruff check)" uv run ruff check .
step "imports (import-linter)" uv run lint-imports
step "types (mypy)" uv run mypy app/ tests/
# The ${arr[@]+...} idiom keeps `set -u` happy on macOS's bash 3.2 when no
# extra args are given.
step "tests (pytest)" uv run pytest tests/ --cov=app --cov-report=xml \
  ${PYTEST_EXTRA[@]+"${PYTEST_EXTRA[@]}"}

echo
if ((${#failed[@]})); then
  echo "Gate FAILED: ${failed[*]}"
  exit 1
fi
echo "Gate passed."
