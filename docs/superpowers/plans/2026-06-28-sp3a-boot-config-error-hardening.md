# SP-3A: Boot / Config / Error Hardening — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the FamilyRoots backend safe to boot in production: fail fast on insecure config, ship structured logging, never leak tracebacks, lock down CORS/hosts, add DB connection pre-ping, and remove stale "RLS at the DB level" claims from code comments. (Heavier SP-3 items — auto-migrate-on-deploy, scheduler single-runner, Redis rate-limit, RLS layer-2 — are separate follow-on plans SP-3B/SP-3C.)

**Architecture:** All changes are in the boot/config/error layer (`app/main.py`, `app/core/config.py`, `app/core/logging.py`, `app/core/exceptions.py`, `app/core/database.py`) plus i18n. No domain/application changes. The app already registers `AppError`/`DomainError` handlers and a CORS middleware; we add a generic `Exception` handler, wire `configure_logging()`, fix the JSON formatter, replace the `["*"]`-under-debug CORS with an explicit allowlist, add `TrustedHostMiddleware`, add a pydantic `model_validator` for production config, and set `pool_pre_ping`.

**Tech Stack:** Python 3.14, FastAPI, Starlette, pydantic-settings, SQLAlchemy async, pytest, `uv`.

## Global Constraints

- Python `>=3.14`; line length 100; ruff selectors per `pyproject.toml`.
- The structured error envelope is `{"error": {"code", "message", "detail"}}` — the generic handler must produce exactly this shape (status 500, `code="internal_error"`), and must NOT include a traceback or exception message in the response.
- Production safety: when `APP_ENV == "production"`, the app must refuse to start (config validation error) if `APP_SECRET_KEY == "change-me-in-production"` or if `APP_DEBUG is True`. `APP_DEBUG` default flips to `False`.
- CORS with `allow_credentials=True` must never use `allow_origins=["*"]` (invalid per the CORS spec and unsafe) — use the explicit `CORS_ORIGINS` allowlist.
- Logging must emit valid JSON even when a log message contains quotes/newlines (use `json.dumps`, not f-string interpolation).
- No behavior change to the existing `AppError`/`DomainError` handlers.
- **git staging discipline:** stage ONLY each task's files (`git add <paths>`); NEVER `git add -A` — unrelated user doc WIP is in the working tree.
- Run tests from `backend/`. Lint `uvx ruff check <paths>`. After all tasks: `uv run pytest tests/unit tests/integration -q` and `uvx ruff check .` clean.

---

## Files

- Modify: `backend/app/core/config.py` (production validator, `APP_DEBUG` default, `ALLOWED_HOSTS`)
- Modify: `backend/app/core/logging.py` (valid-JSON formatter)
- Modify: `backend/app/core/exceptions.py` (generic exception handler)
- Modify: `backend/app/main.py` (wire logging, register generic handler, CORS allowlist, TrustedHostMiddleware, fix stale RLS comment)
- Modify: `backend/app/core/database.py` (`pool_pre_ping`, fix stale RLS docstring)
- Modify: `backend/app/i18n/*.json` (`error.internal_error` key)
- Tests: `backend/tests/unit/test_config_validation.py`, `backend/tests/unit/test_logging_formatter.py`, `backend/tests/unit/test_exception_envelope.py`

---

## Task 1: Production config fail-fast

**Files:**
- Modify: `backend/app/core/config.py`
- Create: `backend/tests/unit/test_config_validation.py`

**Interfaces:**
- Produces: `Settings` raises a `ValidationError` at construction when `APP_ENV == "production"` AND (`APP_SECRET_KEY == "change-me-in-production"` OR `APP_DEBUG is True`). `APP_DEBUG` default is `False`. New `ALLOWED_HOSTS: list[str] = ["*"]` field (used by Task 4).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_config_validation.py`:

```python
"""Production config must fail fast on insecure values."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def _build(**overrides):
    # _env_file=None so the developer's local .env does not interfere.
    return Settings(_env_file=None, **overrides)


def test_dev_defaults_ok():
    s = _build(APP_ENV="development")
    assert s.APP_DEBUG is False  # new default


def test_production_rejects_default_secret():
    with pytest.raises(ValidationError):
        _build(APP_ENV="production", APP_SECRET_KEY="change-me-in-production")


def test_production_rejects_debug_true():
    with pytest.raises(ValidationError):
        _build(APP_ENV="production", APP_SECRET_KEY="a-real-secret", APP_DEBUG=True)


def test_production_with_safe_values_ok():
    s = _build(APP_ENV="production", APP_SECRET_KEY="a-real-secret", APP_DEBUG=False)
    assert s.APP_ENV == "production"
```

- [ ] **Step 2: Run — confirm failures**

Run: `cd backend && uv run pytest tests/unit/test_config_validation.py -v`
Expected: `test_dev_defaults_ok` FAILS (APP_DEBUG currently defaults True) and the two production-reject tests FAIL (no validator yet).

- [ ] **Step 3: Flip the default + add the validator**

In `config.py`, change `APP_DEBUG: bool = True` to `APP_DEBUG: bool = False`. Add `ALLOWED_HOSTS: list[str] = ["*"]` near `CORS_ORIGINS`. Add the import `from pydantic import model_validator` and add this method to `Settings` (after the fields):

```python
    @model_validator(mode="after")
    def _enforce_production_safety(self) -> "Settings":
        if self.APP_ENV == "production":
            if self.APP_SECRET_KEY == "change-me-in-production":
                raise ValueError("APP_SECRET_KEY must be set to a real secret in production")
            if self.APP_DEBUG:
                raise ValueError("APP_DEBUG must be False in production")
        return self
```

- [ ] **Step 4: Run — confirm pass**

Run: `cd backend && uv run pytest tests/unit/test_config_validation.py -v`
Expected: all 4 pass. (A `ValueError` in a pydantic `model_validator` surfaces as `ValidationError`.)

- [ ] **Step 5: Lint + commit (specific files)**

```bash
cd backend && uvx ruff check app/core/config.py tests/unit/test_config_validation.py
git add backend/app/core/config.py backend/tests/unit/test_config_validation.py
git commit -m "feat(config): fail fast on insecure production config; APP_DEBUG defaults false"
```

---

## Task 2: Valid-JSON log formatter

**Files:**
- Modify: `backend/app/core/logging.py`
- Create: `backend/tests/unit/test_logging_formatter.py`

**Interfaces:**
- Produces: `configure_logging()` installs a formatter that emits valid JSON per record (parseable by `json.loads`), with keys `time`, `level`, `logger`, `message`. A `JsonFormatter` class is exported for testing.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_logging_formatter.py`:

```python
"""Log records must serialize to valid JSON even with quotes/newlines."""

import json
import logging

from app.core.logging import JsonFormatter


def _record(msg: str) -> logging.LogRecord:
    return logging.LogRecord(
        name="test.logger", level=logging.INFO, pathname=__file__, lineno=1,
        msg=msg, args=(), exc_info=None,
    )


def test_message_with_quotes_is_valid_json():
    out = JsonFormatter().format(_record('he said "hi"\nthen left'))
    parsed = json.loads(out)  # must not raise
    assert parsed["message"] == 'he said "hi"\nthen left'
    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "test.logger"
    assert "time" in parsed
```

- [ ] **Step 2: Run — confirm it fails**

Run: `cd backend && uv run pytest tests/unit/test_logging_formatter.py -v`
Expected: FAIL — `JsonFormatter` does not exist (ImportError); the current code uses a plain `logging.Formatter` with an f-string template that would produce invalid JSON for this input.

- [ ] **Step 3: Implement a real JSON formatter**

In `logging.py`, replace the `handler.setFormatter(logging.Formatter(...))` template approach with a `JsonFormatter` class. Add `import json` at the top, and:

```python
class JsonFormatter(logging.Formatter):
    """Emit each log record as a single valid JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)
```

And in `configure_logging()`, set `handler.setFormatter(JsonFormatter())` instead of the f-string `logging.Formatter(...)`.

- [ ] **Step 4: Run — confirm pass**

Run: `cd backend && uv run pytest tests/unit/test_logging_formatter.py -v`
Expected: PASS.

- [ ] **Step 5: Lint + commit**

```bash
cd backend && uvx ruff check app/core/logging.py tests/unit/test_logging_formatter.py
git add backend/app/core/logging.py backend/tests/unit/test_logging_formatter.py
git commit -m "fix(logging): emit valid JSON via JsonFormatter (handles quotes/newlines)"
```

---

## Task 3: Generic exception handler (envelope, no traceback leak)

**Files:**
- Modify: `backend/app/core/exceptions.py`
- Modify: `backend/app/i18n/*.json` (add `error.internal_error`)
- Create: `backend/tests/unit/test_exception_envelope.py`

**Interfaces:**
- Produces: `unhandled_exception_handler(request, exc) -> JSONResponse` returns status 500 with `{"error": {"code": "internal_error", "message": <localized>, "detail": {}}}`, logging the exception server-side. It does NOT include the exception's message/traceback in the response body.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_exception_envelope.py`:

```python
"""The generic exception handler returns the standard envelope, no traceback."""

import json

import pytest
from starlette.requests import Request

from app.core.exceptions import unhandled_exception_handler


def _request() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "headers": []})


@pytest.mark.asyncio
async def test_unhandled_exception_returns_envelope_without_traceback():
    exc = RuntimeError("super secret internal detail")
    resp = await unhandled_exception_handler(_request(), exc)
    assert resp.status_code == 500
    body = json.loads(resp.body)
    assert body["error"]["code"] == "internal_error"
    assert "detail" in body["error"]
    # The internal exception text must NOT leak into the response.
    assert "super secret internal detail" not in resp.body.decode()
```

- [ ] **Step 2: Run — confirm it fails**

Run: `cd backend && uv run pytest tests/unit/test_exception_envelope.py -v`
Expected: FAIL — `unhandled_exception_handler` does not exist (ImportError).

- [ ] **Step 3: Add the handler**

In `exceptions.py`, add at the top `import logging` and `logger = logging.getLogger(__name__)`, then append:

```python
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all: log the real error server-side, return the standard envelope.

    Never leaks the exception message or traceback to the client.
    """
    from app.services.translator import t

    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": t("error.internal_error"),
                "detail": {},
            }
        },
    )
```

- [ ] **Step 4: Add the i18n key + register the handler**

Add `"error.internal_error"` to every `backend/app/i18n/*.json` (read one to match the existing key style/structure; mirror an existing `error.*` key). Suggested values: en "An unexpected error occurred.", vi "Đã xảy ra lỗi không mong muốn.", plus the other locales present.

In `app/main.py`, register it alongside the existing handlers (after the `DomainError` registration):

```python
from app.core.exceptions import (
    AppError,
    app_exception_handler,
    domain_exception_handler,
    unhandled_exception_handler,
)
...
    application.add_exception_handler(Exception, unhandled_exception_handler)
```

- [ ] **Step 5: Run — confirm pass + import sanity**

Run: `cd backend && uv run pytest tests/unit/test_exception_envelope.py -v && uv run python -c "import app.main"`
Expected: PASS; import OK.

- [ ] **Step 6: Lint + commit**

```bash
cd backend && uvx ruff check app/core/exceptions.py app/main.py
git add backend/app/core/exceptions.py backend/app/main.py backend/app/i18n/
git commit -m "feat(errors): generic exception handler returns envelope without leaking traceback"
```

---

## Task 4: CORS allowlist + TrustedHostMiddleware + remove stale RLS comments

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/app/core/database.py`

**Interfaces:**
- Produces: CORS always uses `settings.CORS_ORIGINS` (never `["*"]` with credentials); `TrustedHostMiddleware` added with `settings.ALLOWED_HOSTS`; the stale "Supabase RLS at the DB level" comments in `main.py` (lines ~96-98) and `database.py` (docstring lines ~2-6) are corrected to "application/repository-layer isolation; RLS deferred (SP-3C)".

- [ ] **Step 0: Wire `configure_logging()` into the lifespan**

In `main.py`, add `from app.core.logging import configure_logging` and call `configure_logging()` as the FIRST statement inside the `lifespan` startup (before the Sentry init block). Without this, the JSON formatter from Task 2 never takes effect.

- [ ] **Step 1: CORS allowlist**

In `main.py`, change the CORS middleware `allow_origins` from `settings.CORS_ORIGINS if not settings.APP_DEBUG else ["*"]` to:

```python
        allow_origins=settings.CORS_ORIGINS,
```

(Developers add localhost origins via `CORS_ORIGINS`, which already defaults to `["http://localhost:3000", "http://localhost:8080"]`.)

- [ ] **Step 2: TrustedHostMiddleware**

In `main.py`, add the import `from starlette.middleware.trustedhost import TrustedHostMiddleware` and register it (before or after CORS):

```python
    application.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.ALLOWED_HOSTS)
```

(`ALLOWED_HOSTS` defaults to `["*"]` for dev — a no-op; operators set real hosts in production.)

- [ ] **Step 3: Fix the stale RLS comment in main.py**

Replace the comment block at `main.py` lines ~96-98:

```python
    # NOTE: No tenant middleware — clan isolation is enforced in the
    # application/repository layer (every clan-scoped read takes clan_id).
    # Users select their active clan via the X-Current-Clan-Id header.
    # DB-level RLS is a planned defense-in-depth addition (SP-3C), not yet active.
```

- [ ] **Step 4: Fix the stale RLS docstring in database.py**

Replace the module docstring (`database.py` lines 1-6) with:

```python
"""Async SQLAlchemy engine and session management.

Single schema — no search_path switching. clan_id isolation is enforced in the
application/repository layer (explicit clan_id filtering on every clan-scoped
read). DB-level RLS is a planned defense-in-depth addition (SP-3C), not yet active.
"""
```

- [ ] **Step 5: Verify no stale claims remain + import sanity**

Run: `cd backend && grep -rn "RLS at the DB level\|RLS enforces" app/ && echo "FOUND" || echo "clean"`
Expected: `clean` (no matches).
Run: `cd backend && uv run python -c "import app.main"` → OK.

- [ ] **Step 6: Lint + commit**

```bash
cd backend && uvx ruff check app/main.py app/core/database.py
git add backend/app/main.py backend/app/core/database.py
git commit -m "fix(security): explicit CORS allowlist + TrustedHostMiddleware; correct stale RLS comments"
```

---

## Task 5: DB connection pre-ping

**Files:**
- Modify: `backend/app/core/database.py`

**Interfaces:**
- Produces: the async engine is created with `pool_pre_ping=True`, so stale/closed connections (Supabase/pgbouncer, `pool_recycle=300`) are detected and replaced before use rather than surfacing as errors.

- [ ] **Step 1: Add pool_pre_ping**

In `database.py`, add `pool_pre_ping=True` to the `create_async_engine(...)` call:

```python
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_recycle=300,
    pool_pre_ping=True,
    echo=settings.APP_DEBUG,
)
```

- [ ] **Step 2: Verify import + engine builds**

Run: `cd backend && uv run python -c "from app.core.database import engine; print(engine.pool.__class__.__name__)"`
Expected: prints a pool class name (e.g. `AsyncAdaptedQueuePool`), no error.

- [ ] **Step 3: Commit**

```bash
cd backend && uvx ruff check app/core/database.py
git add backend/app/core/database.py
git commit -m "fix(db): enable pool_pre_ping to recycle stale connections"
```

---

## Done criteria (SP-3A)

- `Settings` refuses to construct with insecure production values; `APP_DEBUG` defaults false — `test_config_validation.py` green.
- Logging emits valid JSON for messages containing quotes/newlines — `test_logging_formatter.py` green; `configure_logging()` is wired (Task 3/4 leave it ready — see note).
- Unhandled exceptions return the standard envelope with no traceback leak — `test_exception_envelope.py` green.
- CORS uses an explicit allowlist; `TrustedHostMiddleware` present; stale "RLS at the DB level" comments gone.
- Engine uses `pool_pre_ping`.
- Full `tests/unit` + `tests/integration` suite passes; `ruff check .` clean.

## Notes for the executor

- `configure_logging()` wiring into the lifespan: do it in Task 3 or Task 4's main.py edit — add `from app.core.logging import configure_logging` and call `configure_logging()` as the FIRST line of the `lifespan` startup (before Sentry init). Include this in whichever main.py-touching task you do first; verify with `uv run python -c "import app.main"`. (If neither task ends up wiring it, add a one-line follow-up — the formatter is useless unwired.)
- Run pytest from `backend/`. `git add <specific paths>` only — never `git add -A` (user doc WIP in tree).
- After all tasks: `uv run pytest tests/unit tests/integration -q` + `uvx ruff check .` must be clean.
- Out of scope (SP-3B/3C): auto-migrate-on-deploy entrypoint, scheduler single-runner advisory lock, Redis-backed rate limiting + proxy-aware client IP, asyncpg `statement_cache_size=0` for pgbouncer, and RLS layer-2.
```
