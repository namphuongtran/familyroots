# Alembic + Postgres Driver Unification (psycopg v3) — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace `asyncpg` (runtime) and `psycopg2-binary` (dev) with a single `psycopg[binary]` v3 dependency, so alembic migrations run inside the runtime image both locally (`docker compose exec api alembic upgrade head`) and on Render (`preDeployCommand`).

**Architecture:** psycopg v3 ships sync + async drivers in one package and reuses a single SQLAlchemy URL (`postgresql+psycopg://`). `create_async_engine` auto-selects async; `engine_from_config` (alembic) auto-selects sync. A `field_validator` on `Settings.DATABASE_URL` normalizes any incoming URL form (`postgres://`, `postgresql://`, `postgresql+asyncpg://`, `postgresql+psycopg2://`) to the canonical `postgresql+psycopg://` so Render's bare `connectionString` and stale developer `.env` files keep working.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy 2.0, Alembic, Pydantic Settings v2, psycopg[binary] v3, uv, Docker Compose, Render blueprint.

**Reference design:** `docs/plans/2026-04-29-alembic-psycopg-driver-design.md`

---

## Pre-flight

**One-time setup before starting Task 1:**

```bash
cd "/Volumes/Macext01 HD/playground/familyroots"
git status                                  # confirm clean (or only AGENTS.md / GEMINI.md modified, which are unrelated)
git checkout -b fix/alembic-psycopg-driver  # work on a branch
docker compose ps                           # confirm pgdb + api are running (from earlier)
```

If pgdb/api aren't up: `docker compose up -d pgdb api`.

---

## Task 1: TDD red — add failing test for `DATABASE_URL` validator

**Files:**
- Create: `backend/tests/core/test_config.py`

**Step 1.1: Confirm tests directory layout**

Run: `ls backend/tests/`
Expected: `conftest.py` exists. There may not yet be a `core/` subdir — that's fine, create it.

**Step 1.2: Create the test file**

Create `backend/tests/core/test_config.py`:

```python
"""Tests for app.core.config — DATABASE_URL normalization."""

from __future__ import annotations

import pytest

from app.core.config import Settings


@pytest.mark.parametrize(
    "raw,expected",
    [
        # Render injects bare postgresql:// (no driver) via fromDatabase.connectionString
        (
            "postgresql://user:pass@host:5432/db",
            "postgresql+psycopg://user:pass@host:5432/db",
        ),
        # Render historically also used postgres:// scheme
        (
            "postgres://user:pass@host:5432/db",
            "postgresql+psycopg://user:pass@host:5432/db",
        ),
        # Legacy developer .env files
        (
            "postgresql+asyncpg://user:pass@host:5432/db",
            "postgresql+psycopg://user:pass@host:5432/db",
        ),
        # Old sync driver
        (
            "postgresql+psycopg2://user:pass@host:5432/db",
            "postgresql+psycopg://user:pass@host:5432/db",
        ),
        # Already canonical — no-op
        (
            "postgresql+psycopg://user:pass@host:5432/db",
            "postgresql+psycopg://user:pass@host:5432/db",
        ),
        # Query string preserved
        (
            "postgresql+asyncpg://user:pass@host:5432/db?sslmode=require",
            "postgresql+psycopg://user:pass@host:5432/db?sslmode=require",
        ),
    ],
)
def test_database_url_is_normalized_to_psycopg(raw: str, expected: str) -> None:
    settings = Settings(DATABASE_URL=raw)
    assert settings.DATABASE_URL == expected
```

**Step 1.3: Run the new test, confirm it fails**

Run: `cd backend && .venv/bin/pytest tests/core/test_config.py -v`
Expected: FAIL — either `ModuleNotFoundError: No module named 'tests.core'` (missing `__init__.py` — fix below) or the parametrized cases fail because the validator doesn't exist yet.

If you get the import/collection error, also create an empty `backend/tests/core/__init__.py`:
```bash
touch backend/tests/core/__init__.py
```
Then re-run. The expected failure is now the assertion failures, e.g. `assert 'postgresql://...' == 'postgresql+psycopg://...'`.

**Step 1.4: Commit the failing test**

```bash
git add backend/tests/core/__init__.py backend/tests/core/test_config.py
git commit -m "test(config): add failing DATABASE_URL normalization tests"
```

---

## Task 2: TDD green — implement validator and new default

**Files:**
- Modify: `backend/app/core/config.py`

**Step 2.1: Read the current file**

Run: `cat backend/app/core/config.py`
Expected: ~50 lines, `Settings` class with `DATABASE_URL: str = "postgresql+asyncpg://..."` on line 25.

**Step 2.2: Apply the change**

Replace the imports block and add the validator. The full updated file:

```python
"""Application configuration — loaded from environment variables."""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_CANONICAL_DB_DRIVER = "postgresql+psycopg"


class Settings(BaseSettings):
    """Application settings loaded from .env file and environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # App
    APP_ENV: str = "development"
    APP_SECRET_KEY: str = "change-me-in-production"
    APP_DEBUG: bool = True
    APP_PORT: int = 8000

    # Supabase / PostgreSQL
    DATABASE_URL: str = "postgresql+psycopg://postgres:password@localhost:5432/family_roots"
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_JWT_SECRET: str = ""  # From Supabase Dashboard > API
    SUPABASE_STORAGE_BUCKET: str = "family-roots-files"

    # Firebase FCM
    FIREBASE_CREDENTIALS_PATH: str = "./firebase-credentials.json"

    # Sentry
    SENTRY_DSN: str = ""

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:8080"]

    # Scheduler
    NOTIFICATION_CRON_HOUR: int = 7
    NOTIFICATION_DAYS_BEFORE: int = 7

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        """Rewrite any supported URL form to the canonical psycopg v3 dialect.

        Render injects bare ``postgresql://...`` (or historically ``postgres://``)
        via ``fromDatabase.connectionString``. Older developer ``.env`` files may
        still carry ``+asyncpg``. Normalizing here means the rest of the app and
        Alembic always see one URL form.
        """
        if not isinstance(value, str) or "://" not in value:
            return value
        scheme, rest = value.split("://", 1)
        # postgres:// → postgresql://, then strip any +driver suffix
        base = scheme.split("+", 1)[0]
        if base == "postgres":
            base = "postgresql"
        if base != "postgresql":
            return value  # leave non-postgres URLs untouched
        return f"{_CANONICAL_DB_DRIVER}://{rest}"


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()


settings = get_settings()
```

**Step 2.3: Run the validator test, confirm it passes**

Run: `cd backend && .venv/bin/pytest tests/core/test_config.py -v`
Expected: 6 passed.

**Step 2.4: Run the full backend suite to confirm no regressions**

Run: `cd backend && .venv/bin/pytest -q`
Expected: All previously-passing tests still pass. (Conftest uses pure mocks; no DB needed.)

**Step 2.5: Commit**

```bash
git add backend/app/core/config.py
git commit -m "feat(config): normalize DATABASE_URL to psycopg v3 dialect"
```

---

## Task 3: Swap dependencies — psycopg v3 in, asyncpg + psycopg2 out

**Files:**
- Modify: `backend/pyproject.toml`
- Regenerate: `backend/uv.lock`

**Step 3.1: Edit `backend/pyproject.toml`**

In `[project].dependencies`:
- Remove the line: `"asyncpg>=0.31.0",`
- Add (alphabetically near `pydantic`): `"psycopg[binary]>=3.2",`

In `[dependency-groups].dev`:
- Remove the line: `"psycopg2-binary>=2.9.11",`

**Step 3.2: Re-lock**

Run: `cd backend && uv lock`
Expected: `uv.lock` updated. Should mention adding `psycopg`, `psycopg-binary`, removing `asyncpg`, removing `psycopg2-binary`.

**Step 3.3: Sync host venv (so future host-side `pytest`/`alembic` runs use psycopg v3)**

Run: `cd backend && uv sync`
Expected: env updated. Confirm:
```bash
cd backend && .venv/bin/python -c "import psycopg; print(psycopg.__version__)"
```
Expected: prints `3.x.y`.

**Step 3.4: Confirm asyncpg is gone**

Run: `cd backend && .venv/bin/python -c "import asyncpg" 2>&1 | head -1`
Expected: `ModuleNotFoundError: No module named 'asyncpg'`.

**Step 3.5: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock
git commit -m "chore(deps): replace asyncpg + psycopg2-binary with psycopg[binary] v3"
```

---

## Task 4: Drop the asyncpg-strip hack in alembic env

**Files:**
- Modify: `backend/migrations/env.py` (line 29)

**Step 4.1: Edit `backend/migrations/env.py`**

Replace:
```python
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL.replace("+asyncpg", ""))
```
with:
```python
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
```

**Step 4.2: Update the file docstring (optional but worth it for the next reader)**

The first docstring currently says:
```
"""Alembic environment configuration — single schema.

No multi-schema complexity. Alembic manages the public schema only.
Clan data isolation is handled by clan_id column + Supabase RLS.
"""
```
Append a sentence:
```
"""Alembic environment configuration — single schema.

No multi-schema complexity. Alembic manages the public schema only.
Clan data isolation is handled by clan_id column + Supabase RLS.

DATABASE_URL is normalized to ``postgresql+psycopg://`` by Settings, so
``engine_from_config`` here uses the sync side of the same psycopg v3
driver the application uses for async.
"""
```

**Step 4.3: Smoke alembic from the host against the running pgdb**

Run:
```bash
cd backend && DATABASE_URL="postgresql://postgres:postgres@localhost:5432/family_roots" .venv/bin/alembic current
```
Expected: prints something like `001_initial (head)` (the migration we already applied earlier).

**Step 4.4: Commit**

```bash
git add backend/migrations/env.py
git commit -m "refactor(alembic): drop asyncpg-strip hack — psycopg v3 sync uses same URL"
```

---

## Task 5: Update docker-compose.yml DATABASE_URL

**Files:**
- Modify: `docker-compose.yml` (line 31)

**Step 5.1: Apply the change**

Change:
```yaml
DATABASE_URL: postgresql+asyncpg://${POSTGRES_USER:-postgres}:${POSTGRES_PASSWORD:-postgres}@pgdb:5432/${POSTGRES_DB:-family_roots}
```
to:
```yaml
DATABASE_URL: postgresql+psycopg://${POSTGRES_USER:-postgres}:${POSTGRES_PASSWORD:-postgres}@pgdb:5432/${POSTGRES_DB:-family_roots}
```

**Step 5.2: Commit**

```bash
git add docker-compose.yml
git commit -m "chore(compose): use postgresql+psycopg DATABASE_URL"
```

---

## Task 6: Update `backend/.env.example`

**Files:**
- Modify: `backend/.env.example` (line 8)

**Step 6.1: Apply the change**

Change:
```
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/family_roots
```
to:
```
DATABASE_URL=postgresql+psycopg://postgres:password@localhost:5432/family_roots
```

**Step 6.2: Commit**

```bash
git add backend/.env.example
git commit -m "docs(env): use postgresql+psycopg DATABASE_URL example"
```

---

## Task 7: Wire Render `preDeployCommand`

**Files:**
- Modify: `infra/render/render.yaml`

**Step 7.1: Read current render.yaml**

Run: `cat infra/render/render.yaml`
Expected: shows `services:` with one `web` service named `familyroots-api` and `healthCheckPath: /health`.

**Step 7.2: Add `preDeployCommand` under the `api` service**

Add the following line directly under `healthCheckPath: /health`:
```yaml
    preDeployCommand: alembic upgrade head
```

(Indented 4 spaces — same level as `healthCheckPath`.)

**Step 7.3: Verify YAML still parses**

Run: `python3 -c "import yaml; print(yaml.safe_load(open('infra/render/render.yaml')))"` — only if PyYAML is installed. Otherwise skip and rely on visual inspection.

**Step 7.4: Commit**

```bash
git add infra/render/render.yaml
git commit -m "feat(render): run alembic upgrade head as preDeployCommand"
```

---

## Task 8: Update `backend/README.md`

**Files:**
- Modify: `backend/README.md` (line 8)

**Step 8.1: Apply the change**

Change:
```
- **Database**: PostgreSQL via Supabase (async SQLAlchemy + asyncpg)
```
to:
```
- **Database**: PostgreSQL via Supabase (async SQLAlchemy + psycopg v3)
```

**Step 8.2: Optional sweep — check Dockerfile comment**

`backend/Dockerfile` line 9 says "asyncpg C extension" in a comment. Update:
```
# Native-extension build deps (psycopg v3 binary wheels, cryptography wheels, etc.)
```
This is purely cosmetic — the `gcc/g++/libc6-dev` are still needed for cryptography wheels.

**Step 8.3: Commit**

```bash
git add backend/README.md backend/Dockerfile
git commit -m "docs: update driver references from asyncpg to psycopg v3"
```

---

## Task 9: Rebuild the api image and smoke the full path

**Files:** none (verification only).

**Step 9.1: Bring down the API container so the rebuild is clean**

Run: `docker compose stop api && docker compose rm -f api`
Expected: api container removed, pgdb still running.

**Step 9.2: Rebuild without cache to make sure the new lock is used**

Run: `docker compose build --no-cache api`
Expected: build succeeds. Watch the `uv sync` lines — should show `psycopg-binary` being installed.

**Step 9.3: Bring api back up**

Run: `docker compose up -d api`
Then watch logs until healthy:
```bash
docker compose logs -f api
```
Expected: uvicorn starts, no import errors. Ctrl-C the log follower once you see `Uvicorn running on ...`.

**Step 9.4: Confirm psycopg is in the image and asyncpg is not**

Run:
```bash
docker compose exec api python -c "import psycopg; print('psycopg', psycopg.__version__)"
docker compose exec api python -c "import asyncpg" 2>&1 | head -1
```
Expected:
- First command: `psycopg 3.x.y`
- Second command: `ModuleNotFoundError: No module named 'asyncpg'`

**Step 9.5: Confirm `/health` works (async path)**

Run: `curl -s -w "\nHTTP %{http_code}\n" http://localhost:8000/health`
Expected: `{"status":"ok","database":"connected"}` and `HTTP 200`.

**Step 9.6: Confirm alembic works in-container (sync path)**

Run: `docker compose exec api alembic current`
Expected: prints `001_initial (head)` (or similar).

**Step 9.7: Test on a clean DB to validate `alembic upgrade head` from scratch**

```bash
docker compose down
docker volume rm familyroots_pgdata
docker compose up -d pgdb api
# Wait for healthy
docker compose ps
docker compose exec api alembic upgrade head
```
Expected: alembic runs `001_initial` from empty schema, no errors. Then:
```bash
docker compose exec pgdb psql -U postgres -d family_roots -c "\dt" | head -25
```
Expected: 18 tables listed (same set as before).

**Step 9.8: Smoke a write endpoint**

Pick a no-auth-required endpoint to confirm the async write path works under psycopg v3. `POST /api/v1/auth/register` is the natural choice. Inspect its request body shape first:
```bash
curl -s http://localhost:8000/openapi.json | python3 -c "import sys, json; d=json.load(sys.stdin); import json as j; print(j.dumps(d['paths']['/api/v1/auth/register']['post'], indent=2))" | head -40
```
Then send a request matching that schema:
```bash
curl -i -X POST http://localhost:8000/api/v1/auth/register \
  -H 'Content-Type: application/json' \
  -d '{ ... payload matching the schema ... }'
```
Expected: `2xx` response, or a `4xx` validation error from the app (NOT a 500 — a 500 would indicate a driver problem). If you get a `500`, stop and investigate before proceeding.

**Step 9.9: No commit — this task is verification only.**

---

## Task 10: Run the full backend test suite (in-container and host)

**Files:** none.

**Step 10.1: In-container test run**

Run: `docker compose exec api pytest -q`
Expected: same green result as `make backend-test`. If `pytest` isn't available in the runtime image (it's a dev dep), skip and rely on the host run below.

**Step 10.2: Host test run (authoritative)**

Run: `cd backend && .venv/bin/pytest -q`
Expected: all tests green, including the new `test_config.py`.

**Step 10.3: Lint + type-check**

Run: `make backend-lint`
Expected: ruff + mypy clean. If mypy complains about the `field_validator` import or signature, fix in place and amend the Task 2 commit (`git commit --amend --no-edit` is fine here since the commit is local-only).

**Step 10.4: No commit unless lint/type fixes were needed.** Otherwise, skip.

---

## Task 11: Final sweep + push

**Files:** none.

**Step 11.1: Confirm no stray `asyncpg` references**

Run: `grep -rn "asyncpg" backend infra docker-compose.yml --include="*.py" --include="*.yml" --include="*.yaml" --include="*.toml" --include="*.md" 2>/dev/null`
Expected: no results (or only this plan / design doc, which is fine).

**Step 11.2: Confirm no stray `psycopg2` references**

Run: `grep -rn "psycopg2" backend infra docker-compose.yml --include="*.py" --include="*.yml" --include="*.yaml" --include="*.toml" --include="*.md" 2>/dev/null`
Expected: no results outside of plan/design docs.

**Step 11.3: Review the diff**

Run: `git log --oneline main..HEAD`
Expected: ~7 commits (test, config, deps, alembic env, compose, .env.example, render, docs).

**Step 11.4: Push the branch**

```bash
git push -u origin fix/alembic-psycopg-driver
```

**Step 11.5: Open a PR**

Use the design doc as the PR description body, or summarize as:

> Replaces asyncpg + dev-only psycopg2 with a single psycopg[binary] v3 dependency. Alembic now runs in the runtime image (`docker compose exec api alembic upgrade head`) and on Render via `preDeployCommand`. URL normalization in `Settings` handles Render's bare `postgresql://` connection string and stale developer `+asyncpg` URLs. No schema or data migration.

---

## Acceptance criteria (recap)

- [ ] `docker compose exec api alembic upgrade head` succeeds against an empty DB.
- [ ] `curl /health` returns `{"status":"ok","database":"connected"}` after the rebuild.
- [ ] `psycopg` importable in the runtime image; `asyncpg` not.
- [ ] Backend test suite green (`make backend-test`).
- [ ] `make backend-lint` clean.
- [ ] `infra/render/render.yaml` declares `preDeployCommand: alembic upgrade head`.
- [ ] No `asyncpg` or `psycopg2` references remain in source/config/docs.

## Rollback

Revert the merge commit. No schema or data change occurred; only the driver and configuration changed.
