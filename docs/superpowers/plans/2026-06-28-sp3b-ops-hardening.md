# SP-3B (lite): Ops Hardening — Scheduler single-runner + Rate-limit — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the anniversary scheduler safe to run across multiple replicas (only one fires the job), and make the auth rate limiter proxy-aware and memory-bounded — both with no new infra.

**Architecture:** The APScheduler job (`app/services/scheduler.py`) runs in-process in every replica; we gate its body with a PostgreSQL **advisory lock** so exactly one instance executes per tick. The in-memory rate limiter (`app/core/rate_limit.py`) currently keys on `request.client.host` (the proxy IP behind a load balancer) and never evicts IP buckets (slow leak); we derive the client IP from `X-Forwarded-For` when a trusted proxy is configured, and evict empty buckets.

**Scope note:** Redis-backed rate limiting and the pgbouncer `statement_cache_size` arg are deferred — the former by decision (in-memory is fine single-replica), the latter because it is DB-driver-specific and folds into the imminent psycopg-v3 driver-unification pass (`docs/plans/2026-04-29-alembic-psycopg-driver-plan.md`). Auto-migrate-on-deploy is delivered by that same v3 pass.

**Tech Stack:** Python 3.14, FastAPI/Starlette, APScheduler, SQLAlchemy async, PostgreSQL advisory locks, pytest.

## Global Constraints

- Python `>=3.14`; line length 100; ruff selectors per `pyproject.toml`; mypy strict (run `uv run mypy app/ tests/`, not `uvx mypy`).
- CI gate (must pass): `uvx ruff check .`, `uvx ruff format --check .`, `uv run mypy app/ tests/`, `uv run pytest tests/`.
- No new runtime dependency / infra service.
- The advisory lock must be released even if the job raises (try/finally), and a lock-contended run must be a clean no-op (log + return), not an error.
- Rate-limit: only trust `X-Forwarded-For` when a trusted-proxy setting is enabled (don't let clients spoof their IP by default).
- **git staging discipline:** stage only each task's files (`git add <paths>`); NEVER `git add -A` (unrelated user doc WIP under `docs/` is in the tree).
- Run tests from `backend/`. Postgres running at `familyroots-pgdb` (postgres/postgres@localhost:5432); integration tests use the `migrated_db_url` fixture.

---

## Files

- Modify: `backend/app/services/scheduler.py` (advisory-lock gate)
- Create: `backend/tests/integration/test_scheduler_lock.py`
- Modify: `backend/app/core/rate_limit.py` (proxy-aware IP + bounded buckets)
- Modify: `backend/app/core/config.py` (`RATE_LIMIT_TRUST_FORWARDED_FOR` setting)
- Modify: `backend/app/main.py` (pass the trust flag into the middleware)
- Create: `backend/tests/unit/test_rate_limit.py`

---

## Task 1: Scheduler single-runner via PostgreSQL advisory lock

**Files:**
- Modify: `backend/app/services/scheduler.py`
- Create: `backend/tests/integration/test_scheduler_lock.py`

**Interfaces:**
- Produces: `send_anniversary_notifications()` acquires a session-scoped advisory lock (`pg_try_advisory_lock(_JOB_LOCK_KEY)`) at the start; if not acquired (another replica holds it), it logs and returns without processing; on acquisition it runs the existing logic and releases the lock in a `finally`. `_JOB_LOCK_KEY: int` is a module-level constant.

- [ ] **Step 1: Write the failing integration test**

Create `backend/tests/integration/test_scheduler_lock.py`. It holds the advisory lock on one connection, then runs the job (which opens its own session via `AsyncSessionLocal`, monkeypatched to the test DB) and asserts the job no-ops (inserts no `notification_log` rows):

```python
"""When the job's advisory lock is already held, the run is a clean no-op."""

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.services import scheduler


@pytest.fixture()
async def async_engine(migrated_db_url):
    async_dsn = migrated_db_url.replace("postgresql+psycopg2", "postgresql+asyncpg")
    engine = create_async_engine(async_dsn)
    yield engine
    await engine.dispose()


@pytest.mark.asyncio
async def test_job_skips_when_lock_held(async_engine, monkeypatch):
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    # Point the job at the test DB.
    monkeypatch.setattr("app.core.database.AsyncSessionLocal", maker)

    # Seed a clan + a recurring event due today so the job WOULD send if it ran.
    async with maker() as s:
        clan_id = uuid.uuid4()
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :sg)"),
            {"id": clan_id, "sg": f"c{clan_id.hex[:6]}"},
        )
        await s.commit()

    # Hold the advisory lock on a dedicated connection for the whole test.
    holder = await async_engine.connect()
    try:
        got = await holder.execute(
            sa.text("SELECT pg_try_advisory_lock(:k)"), {"k": scheduler._JOB_LOCK_KEY}
        )
        assert got.scalar() is True  # we hold it

        # Run the job — it must fail to acquire the lock and no-op.
        await scheduler.send_anniversary_notifications()

        async with maker() as s:
            n = await s.execute(sa.text("SELECT COUNT(*) FROM notification_log"))
            assert n.scalar() == 0  # job did not process anything
    finally:
        await holder.execute(
            sa.text("SELECT pg_advisory_unlock(:k)"), {"k": scheduler._JOB_LOCK_KEY}
        )
        await holder.close()
```

- [ ] **Step 2: Run — confirm it fails**

Run: `cd backend && docker compose -f ../docker-compose.yml up -d pgdb && uv run pytest tests/integration/test_scheduler_lock.py -v`
Expected: FAIL — `scheduler._JOB_LOCK_KEY` does not exist yet (AttributeError); and the unguarded job would run regardless of the held lock.

- [ ] **Step 3: Add the advisory-lock gate**

In `scheduler.py`, add a module-level constant near the top (after `logger`):

```python
# Fixed key for the cross-replica advisory lock guarding the anniversary job.
_JOB_LOCK_KEY = 728_115_001
```

Then wrap the body of `send_anniversary_notifications`. Replace the `async with AsyncSessionLocal() as db:` block opening with an advisory-lock acquire/skip/finally-release. Concretely, the function becomes:

```python
async def send_anniversary_notifications() -> None:
    """Daily job: find events with upcoming anniversaries and send FCM notifications.

    A PostgreSQL advisory lock ensures only one replica runs the job per tick;
    other replicas acquire-fail and no-op. Deduplicates via ``notification_log``.
    """
    from app.core.database import AsyncSessionLocal
    from app.services.notification import send_to_clan

    today = date.today()

    async with AsyncSessionLocal() as db:
        acquired = await db.execute(
            text("SELECT pg_try_advisory_lock(:k)"), {"k": _JOB_LOCK_KEY}
        )
        if not acquired.scalar():
            logger.info("Anniversary job lock held by another instance — skipping this run")
            return
        try:
            result = await db.execute(
                text("""
                    <UNCHANGED: the existing SELECT ... FROM public.events e ...>
                """)
            )
            events = result.mappings().all()

            for event in events:
                <UNCHANGED: the existing per-event loop body>
        finally:
            await db.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _JOB_LOCK_KEY})
```

Keep the existing SELECT query and per-event loop EXACTLY as they are — only (a) add the acquire + early-return, and (b) wrap the existing work in `try: ... finally: pg_advisory_unlock`. Do not change the dedup/insert logic. (The advisory lock is session-scoped; releasing it explicitly before the session closes is correct and also released automatically on disconnect.)

- [ ] **Step 4: Run — confirm pass**

Run: `cd backend && uv run pytest tests/integration/test_scheduler_lock.py -v`
Expected: PASS (job no-ops while the lock is held; 0 notification_log rows).

- [ ] **Step 5: Lint + mypy + commit**

```bash
cd backend && uvx ruff check app/services/scheduler.py tests/integration/test_scheduler_lock.py && uvx ruff format --check app/services/scheduler.py tests/integration/test_scheduler_lock.py && uv run mypy app/ tests/
git add backend/app/services/scheduler.py backend/tests/integration/test_scheduler_lock.py
git commit -m "feat(scheduler): single-runner via PG advisory lock (multi-replica safe)"
```

---

## Task 2: Rate limiter — proxy-aware client IP + bounded memory

**Files:**
- Modify: `backend/app/core/config.py` (add `RATE_LIMIT_TRUST_FORWARDED_FOR: bool = False`)
- Modify: `backend/app/core/rate_limit.py`
- Modify: `backend/app/main.py` (pass the flag to the middleware)
- Create: `backend/tests/unit/test_rate_limit.py`

**Interfaces:**
- Produces: `RateLimitMiddleware(app, *, path_prefix, max_requests, window_seconds, trust_forwarded_for=False)`. When `trust_forwarded_for` is True and an `X-Forwarded-For` header is present, the client IP is its first hop (`xff.split(",")[0].strip()`); otherwise `request.client.host`. Empty buckets are deleted after pruning so `self._hits` stays bounded to IPs active within the window.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/test_rate_limit.py`. Test the IP-resolution + bucket-eviction logic directly via a small helper + the middleware. To keep it unit-level, add a `_client_ip(request)` method on the middleware and test it, plus test eviction:

```python
"""Rate limiter: proxy-aware client IP + bounded bucket memory."""

import time
from types import SimpleNamespace

import pytest

from app.core.rate_limit import RateLimitMiddleware


def _mw(trust: bool) -> RateLimitMiddleware:
    return RateLimitMiddleware(
        app=lambda *a, **k: None,
        path_prefix="/api/v1/auth",
        max_requests=2,
        window_seconds=60,
        trust_forwarded_for=trust,
    )


def _req(path: str, *, xff: str | None = None, host: str = "10.0.0.1"):
    headers = {}
    if xff is not None:
        headers["x-forwarded-for"] = xff
    return SimpleNamespace(
        url=SimpleNamespace(path=path),
        headers=headers,
        client=SimpleNamespace(host=host),
    )


def test_client_ip_uses_xff_first_hop_when_trusted():
    mw = _mw(trust=True)
    ip = mw._client_ip(_req("/api/v1/auth/login", xff="203.0.113.7, 10.0.0.1", host="10.0.0.1"))
    assert ip == "203.0.113.7"


def test_client_ip_ignores_xff_when_not_trusted():
    mw = _mw(trust=False)
    ip = mw._client_ip(_req("/api/v1/auth/login", xff="203.0.113.7", host="10.0.0.1"))
    assert ip == "10.0.0.1"


def test_empty_bucket_is_evicted():
    mw = _mw(trust=False)
    ip = "10.0.0.9"
    # One hit far in the past, then prune at "now" → bucket becomes empty → key dropped.
    mw._hits[ip] = [time.monotonic() - 9999]
    mw._prune(ip, time.monotonic() - mw._window)
    assert ip not in mw._hits
```

- [ ] **Step 2: Run — confirm it fails**

Run: `cd backend && uv run pytest tests/unit/test_rate_limit.py -v`
Expected: FAIL — `_client_ip` / `_prune` and the `trust_forwarded_for` param don't exist yet.

- [ ] **Step 3: Add the config flag**

In `config.py`, add near `CORS_ORIGINS`/`ALLOWED_HOSTS`:

```python
    RATE_LIMIT_TRUST_FORWARDED_FOR: bool = False
```

- [ ] **Step 4: Refactor the middleware**

In `rate_limit.py`, add the `trust_forwarded_for` constructor arg, extract `_client_ip` and `_prune`, and evict empty buckets:

```python
    def __init__(
        self,
        app: Any,
        *,
        path_prefix: str = "/api/v1/auth",
        max_requests: int = 20,
        window_seconds: int = 60,
        trust_forwarded_for: bool = False,
    ) -> None:
        super().__init__(app)
        self._prefix = path_prefix
        self._max = max_requests
        self._window = window_seconds
        self._trust_xff = trust_forwarded_for
        self._hits: dict[str, list[float]] = defaultdict(list)

    def _client_ip(self, request: Request) -> str:
        if self._trust_xff:
            xff = request.headers.get("x-forwarded-for")
            if xff:
                return xff.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _prune(self, client_ip: str, cutoff: float) -> list[float]:
        bucket = [t for t in self._hits.get(client_ip, []) if t > cutoff]
        if bucket:
            self._hits[client_ip] = bucket
        else:
            self._hits.pop(client_ip, None)
        return bucket

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not request.url.path.startswith(self._prefix):
            return await call_next(request)

        client_ip = self._client_ip(request)
        now = time.monotonic()
        cutoff = now - self._window
        bucket = self._prune(client_ip, cutoff)

        if len(bucket) >= self._max:
            retry_after = int(bucket[0] - cutoff) + 1
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please try again later."},
                headers={"Retry-After": str(retry_after)},
            )

        self._hits[client_ip].append(now)
        return await call_next(request)
```

(Keep the module docstring; update its "swap for Redis" note to mention the proxy-aware/bounded behavior is in place for single-replica.)

- [ ] **Step 5: Wire the flag in main.py**

In `main.py`, where `RateLimitMiddleware` is added, pass `trust_forwarded_for=settings.RATE_LIMIT_TRUST_FORWARDED_FOR`.

- [ ] **Step 6: Run tests + mypy + format**

Run: `cd backend && uv run pytest tests/unit/test_rate_limit.py -v` → pass.
Run: `uv run mypy app/ tests/` → clean; `uvx ruff format --check app/core/rate_limit.py app/core/config.py app/main.py tests/unit/test_rate_limit.py && uvx ruff check app/core/rate_limit.py app/core/config.py app/main.py tests/unit/test_rate_limit.py` → clean.

- [ ] **Step 7: Commit**

```bash
cd backend && git add app/core/rate_limit.py app/core/config.py app/main.py tests/unit/test_rate_limit.py
git commit -m "feat(rate-limit): proxy-aware client IP (opt-in) + bounded bucket memory"
```

---

## Done criteria (SP-3B lite)

- The anniversary job no-ops cleanly when its advisory lock is held by another instance — `test_scheduler_lock.py` green; lock released in `finally`.
- The rate limiter derives the client IP from `X-Forwarded-For` only when `RATE_LIMIT_TRUST_FORWARDED_FOR` is set, and evicts empty buckets — `test_rate_limit.py` green.
- Full `tests/unit` + `tests/integration` suite passes; `ruff check .`, `ruff format --check .`, `mypy app/ tests/` all clean.

## Notes for the executor

- Run pytest from `backend/`; integration tests need `docker compose up -d pgdb`.
- `git add <specific paths>` only — never `git add -A`.
- Deferred to the psycopg-v3 pass (next): auto-migrate-on-deploy + the pgbouncer `statement_cache_size`/`prepare_threshold` driver arg. Deferred by decision: Redis-backed rate limiting.
- Run `uvx ruff format --check .` AND `uv run mypy app/ tests/` before declaring done — these are the two CI gates a prior pass forgot.
