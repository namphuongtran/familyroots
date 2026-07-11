# PR-J Read-Model Bugs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the two remaining PR-J read-model correctness bugs — platform_admin clan detail `total_users = 0` (miscounted via a coupled join), and person includes silently swallowed to `[]` on sub-query errors.

**Architecture:** Two isolated fixes. (A) Replace the single coupled stats query in `get_clan_detail` with two independent clan-scoped counts (mirroring the sibling `get_metrics` method). (B) Make `_fetch_included_data` re-raise the first exception instead of coercing it to `[]`. No schema change, no migration, no API-shape change.

**Tech Stack:** FastAPI, SQLAlchemy 2 async (psycopg), PostgreSQL, pytest-asyncio (real-DB via `migrated_db_url` for Bug A; fake-handler unit test for Bug B).

## Global Constraints

- **No schema/migration change; response shapes unchanged** (`ClanDetailView`/`ClanStatsView`, and the persons read-endpoint payload).
- **Clan isolation:** all counts clan-scoped; clan A's stats never include clan B's members/users.
- **`total_members`** = distinct **non-soft-deleted** persons in the clan (`Person.is_deleted = false`) — consistent with `get_metrics`. **`total_users`** = distinct users with a role in the clan (`count(distinct UserClanRole.user_id)`, regardless of `is_approved`).
- **Include errors propagate:** a raised include sub-query must surface as an error (re-raised, original type preserved) — never a silent `[]`.
- **Quality gate (full, every task)** from `backend/`: `uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/` (use `uv run mypy`, NOT bare `uvx mypy`), plus `uv run lint-imports`. All pass before commit.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `app/infrastructure/persistence/platform_admin_query_port.py` | Platform-admin read projections | Rewrite `get_clan_detail` stats to two independent counts |
| `app/api/v1/persons.py` | Persons read routes | `_fetch_included_data` re-raises instead of swallowing |
| `tests/integration/test_platform_clan_stats.py` | Real-DB stats test (Bug A) | New |
| `tests/unit/api/test_person_include_errors.py` | Include-error unit test (Bug B) | New |

---

## Task 1: Bug A — independent clan-detail stat counts

**Files:**
- Modify: `backend/app/infrastructure/persistence/platform_admin_query_port.py:63-72`
- Test: `backend/tests/integration/test_platform_clan_stats.py` (new)

**Interfaces:**
- Consumes: `ClanMembership` (person↔clan link), `Person` (`is_deleted`), `UserClanRole` (`user_id`, `clan_id`) — all already imported in the module.
- Produces: `get_clan_detail(clan_id) -> ClanDetailView` — same return shape; `stats.total_members` = distinct non-deleted persons in the clan, `stats.total_users` = distinct role-holding users in the clan.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/integration/test_platform_clan_stats.py`:

```python
"""platform_admin get_clan_detail stats: total_users must not be coupled to member count."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.infrastructure.persistence.platform_admin_query_port import (
    SqlAlchemyPlatformAdminQueryPort,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture()
async def async_session(migrated_db_url: str) -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine(migrated_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as session:
        yield session
    await engine.dispose()


async def _clan(s: AsyncSession, cid: uuid.UUID) -> None:
    await s.execute(
        sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :sl)"),
        {"id": cid, "sl": f"c-{cid.hex[:8]}"},
    )


async def _profile(s: AsyncSession, uid: uuid.UUID) -> None:
    await s.execute(
        sa.text("INSERT INTO user_profiles (id, email, display_name) VALUES (:id, :e, 'U')"),
        {"id": uid, "e": f"u-{uid.hex[:8]}@ex.com"},
    )


async def _role(s: AsyncSession, uid: uuid.UUID, cid: uuid.UUID) -> None:
    now = datetime.now(UTC)
    await s.execute(
        sa.text(
            "INSERT INTO user_clan_roles "
            "(user_id, clan_id, role, is_approved, approved_by, approved_at) "
            "VALUES (:u, :c, 'admin', true, :u, :at)"
        ),
        {"u": uid, "c": cid, "at": now},
    )


async def _person_member(
    s: AsyncSession, clan_id: uuid.UUID, creator: uuid.UUID, *, deleted: bool = False
) -> uuid.UUID:
    pid = uuid.uuid4()
    await s.execute(
        sa.text(
            "INSERT INTO persons (id, full_name, gender, created_by_clan_id, created_by, "
            " is_deleted) VALUES (:id, 'P', 'male', :c, :cb, :d)"
        ),
        {"id": pid, "c": clan_id, "cb": creator, "d": deleted},
    )
    await s.execute(
        sa.text("INSERT INTO clan_memberships (person_id, clan_id) VALUES (:p, :c)"),
        {"p": pid, "c": clan_id},
    )
    return pid


async def test_total_users_counted_when_clan_has_no_persons(async_session: AsyncSession) -> None:
    """The regression: users with roles but zero person-memberships must still count."""
    clan_id = uuid.uuid4()
    await _clan(async_session, clan_id)
    u1, u2 = uuid.uuid4(), uuid.uuid4()
    for u in (u1, u2):
        await _profile(async_session, u)
        await _role(async_session, u, clan_id)
    await async_session.commit()

    detail = await SqlAlchemyPlatformAdminQueryPort(async_session).get_clan_detail(clan_id)
    assert detail.stats.total_users == 2   # was 0 before the fix (no memberships → no rows)
    assert detail.stats.total_members == 0


async def test_members_exclude_soft_deleted_and_users_independent(
    async_session: AsyncSession,
) -> None:
    clan_id, creator = uuid.uuid4(), uuid.uuid4()
    await _clan(async_session, clan_id)
    await _person_member(async_session, clan_id, creator)                 # live
    await _person_member(async_session, clan_id, creator)                 # live
    await _person_member(async_session, clan_id, creator, deleted=True)   # excluded
    u1, u2, u3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    for u in (u1, u2, u3):
        await _profile(async_session, u)
        await _role(async_session, u, clan_id)
    await async_session.commit()

    detail = await SqlAlchemyPlatformAdminQueryPort(async_session).get_clan_detail(clan_id)
    assert detail.stats.total_members == 2   # soft-deleted person excluded
    assert detail.stats.total_users == 3


async def test_clan_stats_isolated_from_other_clan(async_session: AsyncSession) -> None:
    clan_a, clan_b, creator = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await _clan(async_session, clan_a)
    await _clan(async_session, clan_b)
    await _person_member(async_session, clan_a, creator)
    ua, ub = uuid.uuid4(), uuid.uuid4()
    await _profile(async_session, ua)
    await _profile(async_session, ub)
    await _role(async_session, ua, clan_a)
    await _role(async_session, ub, clan_b)      # clan B's user must not count for clan A
    # clan B also gets 2 persons
    await _person_member(async_session, clan_b, creator)
    await _person_member(async_session, clan_b, creator)
    await async_session.commit()

    port = SqlAlchemyPlatformAdminQueryPort(async_session)
    a = await port.get_clan_detail(clan_a)
    assert a.stats.total_members == 1 and a.stats.total_users == 1
    b = await port.get_clan_detail(clan_b)
    assert b.stats.total_members == 2 and b.stats.total_users == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/integration/test_platform_clan_stats.py -xvs`
Expected: FAIL — `test_total_users_counted_when_clan_has_no_persons` asserts `total_users == 2` but the coupled query returns 0 (no `ClanMembership` rows → no result rows → counts 0).

- [ ] **Step 3: Rewrite the stats computation**

In `backend/app/infrastructure/persistence/platform_admin_query_port.py`, replace the current stats block in `get_clan_detail` (the `stats_result = await self._session.execute(select(...).select_from(ClanMembership).outerjoin(...).where(...))` through `stats = stats_result.one()`, lines 63-72) with two independent counts:

```python
        total_members = (
            await self._session.scalar(
                select(func.count(func.distinct(Person.id)))
                .select_from(ClanMembership)
                .join(Person, Person.id == ClanMembership.person_id)
                .where(
                    ClanMembership.clan_id == clan_id,
                    Person.is_deleted.is_(False),
                )
            )
            or 0
        )
        total_users = (
            await self._session.scalar(
                select(func.count(func.distinct(UserClanRole.user_id))).where(
                    UserClanRole.clan_id == clan_id
                )
            )
            or 0
        )
```

Then update the `ClanStatsView` construction to use the locals directly:

```python
            stats=ClanStatsView(
                total_members=total_members,
                total_users=total_users,
            ),
```

(`func`, `select`, `Person`, `ClanMembership`, `UserClanRole` are already imported at the top of the module.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/integration/test_platform_clan_stats.py -v`
Expected: PASS (all three: users-without-members, soft-delete exclusion, cross-clan isolation).

- [ ] **Step 5: Run the full gate**

Run: `cd backend && uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add app/infrastructure/persistence/platform_admin_query_port.py tests/integration/test_platform_clan_stats.py
git commit -m "fix(backend): platform clan detail counts total_users independently of member count (PR-J)"
```

---

## Task 2: Bug B — propagate include sub-query errors

**Files:**
- Modify: `backend/app/api/v1/persons.py:215-219`
- Test: `backend/tests/unit/api/test_person_include_errors.py` (new)

**Interfaces:**
- Consumes: `_fetch_included_data(handler, clan_id, person_id, includes) -> dict[str, list[Any]]` — its `handler` calls `get_marriages` / `get_parent_child` / `get_timeline` / `get_documents`, each `async (clan_id, person_id) -> list`.
- Produces: same signature and happy-path result; on any include sub-query raising, the original exception is re-raised (not coerced to `[]`).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/api/test_person_include_errors.py`:

```python
"""_fetch_included_data must propagate a failing include sub-query, not swallow it to []."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.api.v1.persons import _fetch_included_data

pytestmark = pytest.mark.asyncio


class _FakeHandler:
    """Stand-in PersonQueryHandler: timeline raises, the rest return lists."""

    async def get_marriages(self, clan_id: uuid.UUID, person_id: uuid.UUID) -> list[Any]:
        return [{"marriage_id": "m1"}]

    async def get_parent_child(self, clan_id: uuid.UUID, person_id: uuid.UUID) -> list[Any]:
        return [{"relation_id": "pc1"}]

    async def get_timeline(self, clan_id: uuid.UUID, person_id: uuid.UUID) -> list[Any]:
        raise RuntimeError("timeline query blew up")

    async def get_documents(self, clan_id: uuid.UUID, person_id: uuid.UUID) -> list[Any]:
        return [{"document_id": "d1"}]


async def test_failing_include_propagates_not_swallowed() -> None:
    with pytest.raises(RuntimeError, match="timeline query blew up"):
        await _fetch_included_data(
            _FakeHandler(),  # type: ignore[arg-type]
            uuid.uuid4(),
            uuid.uuid4(),
            ["marriages", "timeline"],
        )


async def test_happy_path_returns_all_lists() -> None:
    result = await _fetch_included_data(
        _FakeHandler(),  # type: ignore[arg-type]
        uuid.uuid4(),
        uuid.uuid4(),
        ["marriages", "parent_child", "documents"],
    )
    assert result == {
        "marriages": [{"marriage_id": "m1"}],
        "parent_child": [{"relation_id": "pc1"}],
        "documents": [{"document_id": "d1"}],
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/api/test_person_include_errors.py -xvs`
Expected: FAIL — `test_failing_include_propagates_not_swallowed`: no exception is raised because the current code coerces the `RuntimeError` to `[]` (`res if isinstance(res, list) else []`), so `pytest.raises` sees no error.

- [ ] **Step 3: Re-raise instead of swallowing**

In `backend/app/api/v1/persons.py`, replace the tail of `_fetch_included_data` (lines 215-219):

```python
    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    res_dict = {}
    for key, res in zip(tasks.keys(), results, strict=False):
        res_dict[key] = res if isinstance(res, list) else []
    return res_dict
```

with:

```python
    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    res_dict: dict[str, list[Any]] = {}
    for key, res in zip(tasks.keys(), results, strict=False):
        # A failing include sub-query must surface as an error (handled by the app's
        # exception handlers), never be masked as empty data. Re-raise the original
        # exception, preserving its type so the same envelope is produced.
        if isinstance(res, BaseException):
            raise res
        res_dict[key] = res
    return res_dict
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/unit/api/test_person_include_errors.py -v`
Expected: PASS (failing include propagates `RuntimeError`; happy path returns all three lists).

- [ ] **Step 5: Run the full gate**

Run: `cd backend && uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add app/api/v1/persons.py tests/unit/api/test_person_include_errors.py
git commit -m "fix(backend): propagate person include sub-query errors instead of swallowing to [] (PR-J)"
```

---

## Self-Review

**1. Spec coverage:**
- Bug A (total_users coupled to member count) → Task 1; the regression case (users, zero members) is `test_total_users_counted_when_clan_has_no_persons`. ✅
- total_members excludes soft-deleted; total_users independent + distinct user → Task 1 fix + `test_members_exclude_soft_deleted_and_users_independent`. ✅
- Clan isolation → `test_clan_stats_isolated_from_other_clan`. ✅
- Bug B (include swallow) → Task 2; propagation asserted by `test_failing_include_propagates_not_swallowed`, happy path preserved. ✅
- No migration / no shape change → neither task touches schema or view/response models. ✅
- S3 minors / typed-DTO breadth → not in any task (explicitly out of scope). ✅

**2. Placeholder scan:** No TBD/TODO/"handle errors"; every code step is complete and runnable. ✅

**3. Type consistency:** Task 1 uses `func.count(func.distinct(...))` + `session.scalar(...)` (matches the module's existing imports and the `get_metrics` idiom); `ClanStatsView(total_members=, total_users=)` matches the existing constructor. Task 2 keeps `_fetch_included_data`'s signature and return type `dict[str, list[Any]]`; the fake handler's method signatures match the real `PersonQueryHandler` include methods `(clan_id, person_id) -> list`. ✅
