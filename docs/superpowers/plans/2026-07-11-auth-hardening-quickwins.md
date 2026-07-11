# Auth Hardening Quick Wins — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Two decision-free auth-hardening wins — a shared idempotent `ensure_profile` upsert helper (dedup + TOCTOU close), and a `GET /api/v1/claims` endpoint for a user to list their own identity claims.

**Architecture:** Item 1 extracts the duplicated `session.get→add` profile provisioning into one `pg_insert ... ON CONFLICT DO NOTHING` helper (mirroring `security.py`'s idiom) that both repos call. Item 2 adds a user-scoped read (query port + handler + route) mirroring the existing admin `list_clan_claims`.

**Tech Stack:** FastAPI, SQLAlchemy 2 async (psycopg), PostgreSQL, Pydantic v2, pytest-asyncio (real-DB via `migrated_db_url`; dependency-override `TestClient` for the route).

## Global Constraints

- **No schema/migration change.** Both items are code-only.
- **`ensure_profile` semantics preserved:** first-writer's `display_name` wins (ON CONFLICT DO NOTHING); `flush`, not `commit` (the caller's handler/UoW owns the transaction).
- **`GET /claims` is the caller's own data** (`user_id == caller`), across all clans — NOT clan-scoped; no cross-clan read of other users' claims.
- **New endpoint uses the `{"data": ...}` envelope** (the target convention; do not add a bare-model outlier). The pre-existing admin claims list stays bare (F-1 will align it later — out of scope here).
- **Hexagonal:** domain port stays framework-agnostic; SQL in infrastructure; route delegates only.
- **Quality gate (full, every task)** from `backend/`: `uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports` (use `uv run mypy`, NOT bare `uvx mypy`). All pass before commit.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `app/infrastructure/persistence/_profile.py` | Shared profile-provisioning helper | New |
| `app/infrastructure/persistence/auth_repository.py` | Auth write repo | `ensure_profile` delegates to helper |
| `app/infrastructure/persistence/invitation_repository.py` | Invitation write repo | `ensure_profile` delegates to helper |
| `app/domain/person/claim_repository.py` | `ClaimQueryPort` protocol | Add `list_user_claims` |
| `app/infrastructure/persistence/claim_repository.py` | `SqlAlchemyClaimQueryPort` | Implement `list_user_claims` |
| `app/application/person/claim_handlers.py` | `ClaimQueryHandler` | Add `list_my_claims` |
| `app/api/v1/claims.py` | `user_claims_router` | Add `GET ""` route |
| `tests/integration/test_ensure_profile_helper.py` | Item 1 real-DB test | New |
| `tests/integration/test_list_my_claims.py` | Item 2 real-DB test | New |
| `tests/unit/api/test_list_my_claims_endpoint.py` | Item 2 route test | New |

---

## Task 1: Shared `ensure_profile` upsert helper

**Files:**
- Create: `backend/app/infrastructure/persistence/_profile.py`
- Modify: `backend/app/infrastructure/persistence/auth_repository.py:89-102`
- Modify: `backend/app/infrastructure/persistence/invitation_repository.py:73-82`
- Test: `backend/tests/integration/test_ensure_profile_helper.py` (new)

**Interfaces:**
- Produces: `ensure_profile_row(session: AsyncSession, user_id: uuid.UUID, email: str, display_name: str | None) -> None` — idempotent, race-safe (`ON CONFLICT DO NOTHING` on PK `id`), flushes.
- Both repos' `ensure_profile(user_id, email, display_name)` signatures unchanged; bodies delegate.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/integration/test_ensure_profile_helper.py`:

```python
"""ensure_profile_row is idempotent + race-safe; both repos delegate to it."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.infrastructure.persistence._profile import ensure_profile_row

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture()
async def async_session(migrated_db_url: str) -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine(migrated_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as session:
        yield session
    await engine.dispose()


async def _name(s: AsyncSession, uid: uuid.UUID) -> str | None:
    return await s.scalar(
        sa.text("SELECT display_name FROM user_profiles WHERE id = :id"), {"id": uid}
    )


async def test_ensure_profile_row_idempotent_and_no_clobber(async_session: AsyncSession) -> None:
    uid = uuid.uuid4()
    await ensure_profile_row(async_session, uid, "a@ex.com", "First")
    # Second call for the SAME id must not raise and must NOT overwrite display_name.
    await ensure_profile_row(async_session, uid, "a@ex.com", "Second")
    await async_session.commit()

    count = await async_session.scalar(
        sa.text("SELECT COUNT(*) FROM user_profiles WHERE id = :id"), {"id": uid}
    )
    assert count == 1
    assert await _name(async_session, uid) == "First"  # first writer wins


async def test_ensure_profile_row_defaults_display_name_from_email(
    async_session: AsyncSession,
) -> None:
    uid = uuid.uuid4()
    await ensure_profile_row(async_session, uid, "bob@ex.com", None)
    await async_session.commit()
    assert await _name(async_session, uid) == "bob"


async def test_both_repos_delegate(async_session: AsyncSession) -> None:
    from app.infrastructure.persistence.auth_repository import SqlAlchemyAuthRepository
    from app.infrastructure.persistence.invitation_repository import (
        SqlAlchemyInvitationRepository,
    )

    ua, ub = uuid.uuid4(), uuid.uuid4()
    await SqlAlchemyAuthRepository(async_session).ensure_profile(ua, "ua@ex.com", "UA")
    await SqlAlchemyInvitationRepository(async_session).ensure_profile(ub, "ub@ex.com", "UB")
    await async_session.commit()
    assert await _name(async_session, ua) == "UA"
    assert await _name(async_session, ub) == "UB"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/integration/test_ensure_profile_helper.py -xvs`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.infrastructure.persistence._profile'`.

- [ ] **Step 3: Create the helper**

Create `backend/app/infrastructure/persistence/_profile.py`:

```python
"""Shared UserProfile provisioning — idempotent, race-safe upsert.

Extracted from the two identical repo `ensure_profile` bodies; mirrors the
`ON CONFLICT DO NOTHING` idiom already used in `app/core/security.py`.
"""

from __future__ import annotations

import uuid

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_profile import UserProfile


async def ensure_profile_row(
    session: AsyncSession, user_id: uuid.UUID, email: str, display_name: str | None
) -> None:
    """Provision the local UserProfile row if absent.

    ON CONFLICT DO NOTHING on the PK makes a concurrent duplicate insert a no-op
    (no IntegrityError, no clobber — the first writer's row and display_name win).
    Flushes (not commits): the caller's handler/UoW owns the transaction.
    """
    stmt = (
        pg_insert(UserProfile)
        .values(
            id=user_id,
            email=email,
            display_name=display_name or email.split("@")[0],
        )
        .on_conflict_do_nothing(index_elements=["id"])
    )
    await session.execute(stmt)
    await session.flush()
```

(Confirm the model import path: the module defining `UserProfile` — `auth_repository.py` imports it as `UserProfileModel`, `invitation_repository.py` as `UserProfile`; use whichever real path those files use, i.e. `from app.models.user_profile import UserProfile`. If the actual module path differs, match the existing import in `invitation_repository.py`.)

- [ ] **Step 4: Delegate both repos to the helper**

In `backend/app/infrastructure/persistence/auth_repository.py`, replace the `ensure_profile` body (lines 89-102) with:

```python
    async def ensure_profile(
        self, user_id: uuid.UUID, email: str, display_name: str | None
    ) -> None:
        await ensure_profile_row(self._session, user_id, email, display_name)
```

Add the import near the other persistence imports at the top of the file:

```python
from app.infrastructure.persistence._profile import ensure_profile_row
```

In `backend/app/infrastructure/persistence/invitation_repository.py`, replace the `ensure_profile` body (lines 73-82) with the identical delegating body above, and add the same import. If the now-unused `UserProfileModel` / `UserProfile` model import becomes unused in a file, remove it (ruff will flag F401).

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/integration/test_ensure_profile_helper.py -v`
Expected: PASS (idempotent + no-clobber, email-default name, both repos delegate).

- [ ] **Step 6: Run the full gate**

Run: `cd backend && uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports`
Expected: all green (existing auth/invitation tests still pass — behavior preserved).

- [ ] **Step 7: Commit**

```bash
git add app/infrastructure/persistence/_profile.py app/infrastructure/persistence/auth_repository.py app/infrastructure/persistence/invitation_repository.py tests/integration/test_ensure_profile_helper.py
git commit -m "refactor(backend): shared ensure_profile upsert helper (dedup + ON CONFLICT race-safe) (auth-hardening)"
```

---

## Task 2: `GET /api/v1/claims` — list my own claims

**Files:**
- Modify: `backend/app/domain/person/claim_repository.py` (`ClaimQueryPort` protocol)
- Modify: `backend/app/infrastructure/persistence/claim_repository.py` (`SqlAlchemyClaimQueryPort`)
- Modify: `backend/app/application/person/claim_handlers.py` (`ClaimQueryHandler`)
- Modify: `backend/app/api/v1/claims.py` (`user_claims_router`)
- Test: `backend/tests/integration/test_list_my_claims.py` (new)
- Test: `backend/tests/unit/api/test_list_my_claims_endpoint.py` (new)

**Interfaces:**
- Consumes: existing `ClaimModel`, `require_active_user` (→ `UserProfile` with `.id`), `get_claim_query_handler`, `IdentityClaimPaginatedResponse` / `IdentityClaimResponse`.
- Produces:
  - `ClaimQueryPort.list_user_claims(user_id, status, page, page_size) -> tuple[list[ClaimModel], int]`.
  - `ClaimQueryHandler.list_my_claims(*, user_id, status=None, page=1, page_size=20) -> IdentityClaimPaginatedResponse`.
  - `GET /api/v1/claims` → `{"data": <IdentityClaimPaginatedResponse dict>}`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/integration/test_list_my_claims.py`:

```python
"""ClaimQueryHandler.list_my_claims returns the caller's own claims, filtered + paged."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.application.person.claim_handlers import ClaimQueryHandler
from app.infrastructure.persistence.claim_repository import SqlAlchemyClaimQueryPort

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture()
async def async_session(migrated_db_url: str) -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine(migrated_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as session:
        yield session
    await engine.dispose()


async def _clan(s: AsyncSession) -> uuid.UUID:
    cid = uuid.uuid4()
    await s.execute(
        sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :sl)"),
        {"id": cid, "sl": f"c-{cid.hex[:8]}"},
    )
    return cid


async def _user(s: AsyncSession) -> uuid.UUID:
    uid = uuid.uuid4()
    await s.execute(
        sa.text("INSERT INTO user_profiles (id, email, display_name) VALUES (:id, :e, 'U')"),
        {"id": uid, "e": f"u-{uid.hex[:8]}@ex.com"},
    )
    return uid


async def _person(s: AsyncSession, clan_id: uuid.UUID, creator: uuid.UUID) -> uuid.UUID:
    pid = uuid.uuid4()
    await s.execute(
        sa.text(
            "INSERT INTO persons (id, full_name, gender, created_by_clan_id, created_by) "
            "VALUES (:id, 'P', 'male', :c, :cb)"
        ),
        {"id": pid, "c": clan_id, "cb": creator},
    )
    return pid


async def _claim(
    s: AsyncSession, user_id: uuid.UUID, person_id: uuid.UUID, status: str = "PENDING"
) -> None:
    await s.execute(
        sa.text(
            "INSERT INTO identity_claims (id, user_id, person_id, status) "
            "VALUES (:id, :u, :p, :st)"
        ),
        {"id": uuid.uuid4(), "u": user_id, "p": person_id, "st": status},
    )


async def _seed(async_session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    clan = await _clan(async_session)
    creator = uuid.uuid4()
    user_a, user_b = await _user(async_session), await _user(async_session)
    p1, p2, p3 = (
        await _person(async_session, clan, creator),
        await _person(async_session, clan, creator),
        await _person(async_session, clan, creator),
    )
    await _claim(async_session, user_a, p1, "PENDING")
    await _claim(async_session, user_a, p2, "APPROVED")
    await _claim(async_session, user_b, p3, "PENDING")  # other user's claim
    await async_session.commit()
    return user_a, user_b


async def test_list_my_claims_returns_only_callers_claims(async_session: AsyncSession) -> None:
    user_a, user_b = await _seed(async_session)
    handler = ClaimQueryHandler(SqlAlchemyClaimQueryPort(async_session))

    result = await handler.list_my_claims(user_id=user_a)
    assert result.total == 2
    assert {str(i.user_id) for i in result.items} == {str(user_a)}  # never user_b's

    result_b = await handler.list_my_claims(user_id=user_b)
    assert result_b.total == 1


async def test_list_my_claims_status_filter_and_paging(async_session: AsyncSession) -> None:
    user_a, _ = await _seed(async_session)
    handler = ClaimQueryHandler(SqlAlchemyClaimQueryPort(async_session))

    pending = await handler.list_my_claims(user_id=user_a, status="PENDING")
    assert pending.total == 1 and pending.items[0].status == "PENDING"

    page1 = await handler.list_my_claims(user_id=user_a, page=1, page_size=1)
    assert page1.total == 2 and len(page1.items) == 1  # total counts all, page returns 1
```

Create `backend/tests/unit/api/test_list_my_claims_endpoint.py`:

```python
"""GET /api/v1/claims returns the caller's claims in the {data:...} envelope."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.claims import user_claims_router
from app.core.permissions import require_active_user
from app.infrastructure.dependencies import get_claim_query_handler
from app.schemas.claim import IdentityClaimPaginatedResponse


class _FakeClaimQueryHandler:
    def __init__(self) -> None:
        self.last: dict[str, Any] = {}

    async def list_my_claims(
        self, *, user_id: uuid.UUID, status: str | None = None, page: int = 1, page_size: int = 20
    ) -> IdentityClaimPaginatedResponse:
        self.last = {"user_id": user_id, "status": status, "page": page, "page_size": page_size}
        return IdentityClaimPaginatedResponse(items=[], total=0, page=page, page_size=page_size)


def _client(handler: _FakeClaimQueryHandler) -> TestClient:
    app = FastAPI()
    app.include_router(user_claims_router, prefix="/api/v1/claims")
    app.dependency_overrides[require_active_user] = lambda: SimpleNamespace(id=uuid.uuid4())
    app.dependency_overrides[get_claim_query_handler] = lambda: handler
    return TestClient(app)


def test_list_my_claims_envelope_and_params() -> None:
    handler = _FakeClaimQueryHandler()
    resp = _client(handler).get("/api/v1/claims?status=PENDING&page=2&page_size=5")
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body and body["data"]["total"] == 0  # {"data": {...}} envelope
    assert handler.last["status"] == "PENDING"
    assert handler.last["page"] == 2 and handler.last["page_size"] == 5


def test_list_my_claims_rejects_bad_page() -> None:
    resp = _client(_FakeClaimQueryHandler()).get("/api/v1/claims?page=0")
    assert resp.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/integration/test_list_my_claims.py tests/unit/api/test_list_my_claims_endpoint.py -xvs`
Expected: FAIL — `ClaimQueryHandler` has no `list_my_claims` (AttributeError) and the route 404s.

- [ ] **Step 3: Add the query-port method (protocol + impl)**

In `backend/app/domain/person/claim_repository.py`, add to the `ClaimQueryPort` Protocol (after `list_clan_claims`):

```python
    async def list_user_claims(
        self,
        user_id: uuid.UUID,
        status: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[Any], int]:
        """List claims submitted by the given user, across all clans."""
        ...
```

In `backend/app/infrastructure/persistence/claim_repository.py`, add to `SqlAlchemyClaimQueryPort` (after `list_clan_claims`):

```python
    async def list_user_claims(
        self,
        user_id: uuid.UUID,
        status: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[ClaimModel], int]:
        query = select(ClaimModel).where(ClaimModel.user_id == user_id)
        if status:
            query = query.where(ClaimModel.status == status)

        count_query = select(func.count()).select_from(query.subquery())
        total = await self._session.scalar(count_query) or 0

        query = (
            query.order_by(ClaimModel.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self._session.execute(query)
        return list(result.scalars().all()), total
```

- [ ] **Step 4: Add the handler method**

In `backend/app/application/person/claim_handlers.py`, add to `ClaimQueryHandler` (after `list_clan_claims`):

```python
    async def list_my_claims(
        self,
        *,
        user_id: uuid.UUID,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> IdentityClaimPaginatedResponse:
        """List the caller's own identity claims (across all clans)."""
        claims, total = await self._query_port.list_user_claims(user_id, status, page, page_size)
        return IdentityClaimPaginatedResponse(
            items=[IdentityClaimResponse.model_validate(c) for c in claims],
            total=total,
            page=page,
            page_size=page_size,
        )
```

- [ ] **Step 5: Add the route**

In `backend/app/api/v1/claims.py`, add the import for the query handler and `ClaimQueryHandler` if not already imported (`ClaimQueryHandler` and `get_claim_query_handler` are already imported for the admin list). Add `Query` is already imported. Add this route on `user_claims_router` (place it BEFORE the existing `DELETE /{claim_id}`):

```python
@user_claims_router.get(
    "",
    summary="List my identity claims",
)
async def list_my_claims(
    status: str | None = Query(None, description="Filter by status (e.g., PENDING)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: UserProfile = Depends(require_active_user),
    handler: ClaimQueryHandler = Depends(get_claim_query_handler),
) -> dict[str, Any]:
    """List identity claims submitted by the current user, across all clans."""
    paginated = await handler.list_my_claims(
        user_id=user.id, status=status, page=page, page_size=page_size
    )
    return {"data": paginated.model_dump()}
```

(`UserProfile`, `require_active_user`, `ClaimQueryHandler`, `get_claim_query_handler`, `Query`, `Depends`, `Any` are all already imported at the top of `claims.py`.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/integration/test_list_my_claims.py tests/unit/api/test_list_my_claims_endpoint.py -v`
Expected: PASS (own-claims-only + isolation from other user, status filter, paging, envelope, 422 on bad page).

- [ ] **Step 7: Run the full gate**

Run: `cd backend && uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports`
Expected: all green.

- [ ] **Step 8: Commit**

```bash
git add app/domain/person/claim_repository.py app/infrastructure/persistence/claim_repository.py app/application/person/claim_handlers.py app/api/v1/claims.py tests/integration/test_list_my_claims.py tests/unit/api/test_list_my_claims_endpoint.py
git commit -m "feat(backend): GET /claims — user lists their own identity claims (auth-hardening)"
```

---

## Self-Review

**1. Spec coverage:**
- Item 1 (shared upsert helper, dedup + TOCTOU) → Task 1; idempotent/no-clobber/default-name/both-repos-delegate tested. ✅
- Item 2 (GET /claims list-my-claims) → Task 2; own-claims-only + isolation + filter + paging + `{data}` envelope + 422 tested. ✅
- No schema change; semantics preserved (flush, first-writer wins); envelope = `{data}`. ✅
- Email verification + F-1 of existing routes → not in any task (out of scope). ✅

**2. Placeholder scan:** No TBD/TODO; every step has complete code + exact commands. (One explicit "confirm the model import path" note in Task 1 Step 3 resolves an import-alias ambiguity, with the concrete fallback given.) ✅

**3. Type consistency:** `ensure_profile_row(session, user_id, email, display_name)` identical in helper (Task 1) and both repo call sites. `list_user_claims(user_id, status, page, page_size) -> tuple[list[ClaimModel], int]` identical across port protocol + impl + handler consumption. `list_my_claims(*, user_id, status=None, page=1, page_size=20) -> IdentityClaimPaginatedResponse` identical in handler + route call + fake-handler test double. Route returns `dict[str, Any]` = `{"data": <model_dump>}`. ✅
