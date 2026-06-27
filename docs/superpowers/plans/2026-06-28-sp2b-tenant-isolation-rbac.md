# SP-2B: Tenant Isolation & RBAC — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the cross-clan read leaks (relationship and person-relationship projections), authorize the claim-listing endpoint against the path clan, and pin the deliberately-permissive `update_person` authorization with tests — so strict clan isolation (the locked decision) holds at the read path, not just the write path.

**Architecture:** Clan isolation is enforced in the application/repository layer (RLS is deferred to SP-3). We make `clan_id` a mandatory parameter on the relationship repository read (`get_by_id(id, clan_id)`) so cross-clan access returns "not found" (404, hiding existence) instead of leaking the row; we scope the person-relationship projections by `created_by_clan_id`; we guard the claim-list route so the path `{clan_id}` must equal the caller's active (header-validated) clan; and we lock the `update_person` viewer carve-out with explicit tests.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy 2.0 async, asyncpg, pytest + pytest-asyncio, `uv`. Local Postgres via `docker compose up -d pgdb` (postgres/postgres on localhost:5432).

## Global Constraints

- Python `>=3.14`; line length 100; ruff selectors per `pyproject.toml`.
- **Strict clan isolation** (locked decision): a clan may read only persons and relationship edges scoped to it. Cross-clan reads must NOT reveal data or existence — prefer 404 over 403 for a resource that exists only in another clan.
- Domain layer stays framework-agnostic; application imports domain + ports only.
- Every clan-scoped repository read takes `clan_id` and filters on it (the mandatory-clan_id contract).
- Soft-deleted edges (`is_deleted = true`) are excluded from reads.
- `update_person` keeps `RequireViewer` at the route on purpose: the handler grants a viewer edit access ONLY to their own linked person and ONLY for a whitelisted field set; editors/admins get full edits. Do NOT change this to `RequireEditor` (that would remove the legitimate self-edit feature). This corrects the SP-2 design note.
- Run tests from `backend/`: `uv run pytest <path> -v`. Lint: `uvx ruff check <path>`.
- Integration tests use the `tests/integration` fixtures (throwaway migrated Postgres; admin DSN `postgresql+psycopg2://postgres:postgres@localhost:5432/postgres`).

---

## Files

- Modify: `backend/app/domain/relationship/repository.py` — `get_by_id(id, clan_id)`.
- Modify: `backend/app/infrastructure/persistence/relationship_repository.py` — clan-scoped `get_by_id` for Marriage + ParentChild.
- Modify: `backend/app/application/relationship/handlers.py` — query + command handlers pass `clan_id`; cross-clan → not found.
- Modify: `backend/app/api/v1/relationships.py` — pass `clan_id` to the two query handlers.
- Modify: `backend/app/domain/person/query_port.py` + `backend/app/infrastructure/persistence/person_query_port.py` — `get_marriages`/`get_parent_child_links` take `clan_id` and filter `created_by_clan_id`.
- Modify: `backend/app/application/person/handlers.py` — `PersonQueryHandler.get_marriages`/`get_parent_child` pass `clan_id`.
- Modify: `backend/app/api/v1/persons.py` — pass `clan_id` at the 3 call sites.
- Modify: `backend/app/api/v1/claims.py` — guard `list_clan_claims` so path `{clan_id}` == active clan.
- Modify: `backend/app/application/person/handlers.py` (update method) + `backend/app/api/v1/persons.py` (update route) — documentation only.
- Create: `backend/tests/integration/test_relationship_isolation.py`, `backend/tests/integration/test_person_projection_isolation.py`.
- Create: `backend/tests/unit/api/test_claims_clan_guard.py`, `backend/tests/unit/application/test_person_update_authorization.py`.

---

## Task 1: Clan-scope relationship reads (close the cross-clan leak)

**Files:**
- Modify: `backend/app/domain/relationship/repository.py`
- Modify: `backend/app/infrastructure/persistence/relationship_repository.py:130-134, 149-153`
- Modify: `backend/app/application/relationship/handlers.py` (query handlers `:149-150, :157-158`; command handlers `update`/`delete` for both aggregates)
- Modify: `backend/app/api/v1/relationships.py:84, 168`
- Create: `backend/tests/integration/test_relationship_isolation.py`

**Interfaces:**
- Produces: `MarriageRepository.get_by_id(marriage_id, clan_id)` / `ParentChildRepository.get_by_id(link_id, clan_id)` return the entity only when `created_by_clan_id == clan_id` and not soft-deleted, else `None`. `MarriageQueryHandler.get_by_id(marriage_id, clan_id)` / `ParentChildQueryHandler.get_by_id(link_id, clan_id)` forward `clan_id`. Command handlers fetch with `clan_id`; cross-clan → `EntityNotFoundError`.

- [ ] **Step 1: Write the failing isolation test**

Create `backend/tests/integration/test_relationship_isolation.py`. It seeds two clans + a marriage and a parent-child edge in clan A, then asserts clan B cannot read them. Reuse the `async_session` pattern from `tests/integration/test_auth_provisioning.py` (convert the sync `migrated_db_url` to asyncpg).

```python
"""A clan must not read relationship edges created by another clan (strict isolation)."""

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.application.relationship.handlers import MarriageQueryHandler, ParentChildQueryHandler
from app.infrastructure.persistence.relationship_repository import (
    SqlAlchemyMarriageRepository,
    SqlAlchemyParentChildRepository,
)


@pytest.fixture()
async def async_session(migrated_db_url):
    async_dsn = migrated_db_url.replace("postgresql+psycopg2", "postgresql+asyncpg")
    engine = create_async_engine(async_dsn)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as session:
        yield session
    await engine.dispose()


async def _seed(session: AsyncSession):
    clan_a, clan_b = uuid.uuid4(), uuid.uuid4()
    for cid, slug in ((clan_a, f"a-{clan_a.hex[:6]}"), (clan_b, f"b-{clan_b.hex[:6]}")):
        await session.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, :n, :s)"),
            {"id": cid, "n": slug, "s": slug},
        )
    p1, p2, child = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    for pid in (p1, p2, child):
        await session.execute(
            sa.text(
                "INSERT INTO persons (id, full_name, gender, created_by_clan_id, created_by) "
                "VALUES (:id, 'P', 'unknown', :cid, :cb)"
            ),
            {"id": pid, "cid": clan_a, "cb": uuid.uuid4()},
        )
    marriage_id, link_id = uuid.uuid4(), uuid.uuid4()
    await session.execute(
        sa.text(
            "INSERT INTO marriages (id, person1_id, person2_id, created_by_clan_id, status, created_by) "
            "VALUES (:id, :p1, :p2, :cid, 'married', :cb)"
        ),
        {"id": marriage_id, "p1": p1, "p2": p2, "cid": clan_a, "cb": uuid.uuid4()},
    )
    await session.execute(
        sa.text(
            "INSERT INTO parent_child (id, parent_id, child_id, created_by_clan_id, relationship_type, created_by) "
            "VALUES (:id, :p, :c, :cid, 'biological', :cb)"
        ),
        {"id": link_id, "p": p1, "c": child, "cid": clan_a, "cb": uuid.uuid4()},
    )
    await session.commit()
    return clan_a, clan_b, marriage_id, link_id


@pytest.mark.asyncio
async def test_marriage_not_readable_cross_clan(async_session: AsyncSession):
    clan_a, clan_b, marriage_id, _ = await _seed(async_session)
    handler = MarriageQueryHandler(SqlAlchemyMarriageRepository(async_session))
    assert await handler.get_by_id(marriage_id, clan_a) is not None
    assert await handler.get_by_id(marriage_id, clan_b) is None


@pytest.mark.asyncio
async def test_parent_child_not_readable_cross_clan(async_session: AsyncSession):
    clan_a, clan_b, _, link_id = await _seed(async_session)
    handler = ParentChildQueryHandler(SqlAlchemyParentChildRepository(async_session))
    assert await handler.get_by_id(link_id, clan_a) is not None
    assert await handler.get_by_id(link_id, clan_b) is None
```

- [ ] **Step 2: Run the test — confirm it fails**

Run: `cd backend && docker compose -f ../docker-compose.yml up -d pgdb && uv run pytest tests/integration/test_relationship_isolation.py -v`
Expected: FAIL — current `get_by_id(marriage_id)` takes no `clan_id` (TypeError) — and even adapted, the unscoped lookup would return the row for clan_b.

- [ ] **Step 3: Update the repository protocol**

In `backend/app/domain/relationship/repository.py`, add `clan_id` to both reads:

```python
class MarriageRepository(Protocol):
    async def get_by_id(self, marriage_id: uuid.UUID, clan_id: uuid.UUID) -> Marriage | None: ...
    async def save(self, marriage: Marriage) -> None: ...


class ParentChildRepository(Protocol):
    async def get_by_id(self, link_id: uuid.UUID, clan_id: uuid.UUID) -> ParentChild | None: ...
    async def save(self, link: ParentChild) -> None: ...
```

- [ ] **Step 4: Make the SQLAlchemy reads clan-scoped**

In `relationship_repository.py`, replace `SqlAlchemyMarriageRepository.get_by_id` (lines 130-134):

```python
    async def get_by_id(
        self, marriage_id: uuid.UUID, clan_id: uuid.UUID
    ) -> MarriageEntity | None:
        result = await self._session.execute(
            select(MarriageModel).where(
                MarriageModel.id == marriage_id,
                MarriageModel.created_by_clan_id == clan_id,
                MarriageModel.is_deleted.is_(False),
            )
        )
        model = result.scalar_one_or_none()
        return _marriage_to_domain(model) if model else None
```

And `SqlAlchemyParentChildRepository.get_by_id` (lines 149-153):

```python
    async def get_by_id(
        self, link_id: uuid.UUID, clan_id: uuid.UUID
    ) -> ParentChildEntity | None:
        result = await self._session.execute(
            select(ParentChildModel).where(
                ParentChildModel.id == link_id,
                ParentChildModel.created_by_clan_id == clan_id,
                ParentChildModel.is_deleted.is_(False),
            )
        )
        model = result.scalar_one_or_none()
        return _pc_to_domain(model) if model else None
```

(`select` is already imported at the top of the file.)

- [ ] **Step 5: Thread `clan_id` through the handlers**

In `application/relationship/handlers.py`:

Query handlers — replace `MarriageQueryHandler.get_by_id` and `ParentChildQueryHandler.get_by_id`:

```python
class MarriageQueryHandler:
    def __init__(self, repo: MarriageRepository) -> None:
        self._repo = repo

    async def get_by_id(self, marriage_id: uuid.UUID, clan_id: uuid.UUID) -> Marriage | None:
        return await self._repo.get_by_id(marriage_id, clan_id)


class ParentChildQueryHandler:
    def __init__(self, repo: ParentChildRepository) -> None:
        self._repo = repo

    async def get_by_id(self, link_id: uuid.UUID, clan_id: uuid.UUID) -> ParentChild | None:
        return await self._repo.get_by_id(link_id, clan_id)
```

Command handlers — in `MarriageCommandHandler.update`/`delete` and `ParentChildCommandHandler.update`/`delete`, change the fetch to pass `cmd.clan_id` and drop the now-redundant `created_by_clan_id` check (the scoped fetch returns `None` cross-clan, which becomes a 404 — correct for strict isolation). For `MarriageCommandHandler.update` (lines 60-64):

```python
        marriage = await self._repo.get_by_id(cmd.marriage_id, cmd.clan_id)
        if not marriage:
            raise EntityNotFoundError("marriage_not_found")
```

Apply the identical pattern to `MarriageCommandHandler.delete` (drop the `ForbiddenError` block), `ParentChildCommandHandler.update`, and `ParentChildCommandHandler.delete` (use `cmd.link_id`, `parent_child_not_found`). `ForbiddenError` may become an unused import — if so, remove it from the import on line 22.

- [ ] **Step 6: Pass `clan_id` at the routes**

In `app/api/v1/relationships.py`, `get_marriage` (line 84): `marriage = await query_handler.get_by_id(marriage_id, clan_id)`. `get_parent_child` (line 168): `link = await query_handler.get_by_id(link_id, clan_id)`. (Both routes already inject `clan_id`.)

- [ ] **Step 7: Run the isolation test + existing relationship tests**

Run: `cd backend && uv run pytest tests/integration/test_relationship_isolation.py tests/test_relationships.py -v`
Expected: the isolation test PASSES. If any existing test in `tests/test_relationships.py` asserted a 403 / `not_managing_clan` for a cross-clan update/delete, update it to expect `EntityNotFoundError` / `marriage_not_found` (strict isolation hides existence) and note the change in your report. Do not weaken any other assertion.

- [ ] **Step 8: Lint + commit**

```bash
cd backend && uvx ruff check app/domain/relationship/repository.py app/infrastructure/persistence/relationship_repository.py app/application/relationship/handlers.py app/api/v1/relationships.py tests/integration/test_relationship_isolation.py
git add -A && git commit -m "fix(isolation): clan-scope relationship reads; cross-clan returns not-found"
```

---

## Task 2: Clan-scope person→relationship projections

**Files:**
- Modify: `backend/app/domain/person/query_port.py:14-18`
- Modify: `backend/app/infrastructure/persistence/person_query_port.py:31-49`
- Modify: `backend/app/application/person/handlers.py:177-185`
- Modify: `backend/app/api/v1/persons.py:195, 420, ~437`
- Create: `backend/tests/integration/test_person_projection_isolation.py`

**Interfaces:**
- Produces: `PersonQueryPort.get_marriages(clan_id, person_id)` and `get_parent_child_links(clan_id, person_id)` return only edges with `created_by_clan_id == clan_id` (matching the `(clan_id, person_id)` signature already used by `get_documents`/`get_events`). `PersonQueryHandler.get_marriages(clan_id, person_id)` / `get_parent_child(clan_id, person_id)` forward `clan_id`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/integration/test_person_projection_isolation.py` (reuse the `async_session` fixture pattern and the clan/person/edge seeding from Task 1's test — duplicate the small seed inline; do not import across test files):

```python
"""Person marriage/parent-child projections must only surface edges of the active clan."""

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.infrastructure.persistence.person_query_port import SqlAlchemyPersonQueryPort


@pytest.fixture()
async def async_session(migrated_db_url):
    async_dsn = migrated_db_url.replace("postgresql+psycopg2", "postgresql+asyncpg")
    engine = create_async_engine(async_dsn)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_marriages_scoped_to_clan(async_session: AsyncSession):
    clan_a, clan_b = uuid.uuid4(), uuid.uuid4()
    for cid, s in ((clan_a, f"a-{clan_a.hex[:6]}"), (clan_b, f"b-{clan_b.hex[:6]}")):
        await async_session.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, :n, :s)"),
            {"id": cid, "n": s, "s": s},
        )
    p1, p2 = uuid.uuid4(), uuid.uuid4()
    for pid in (p1, p2):
        await async_session.execute(
            sa.text(
                "INSERT INTO persons (id, full_name, gender, created_by_clan_id, created_by) "
                "VALUES (:id, 'P', 'unknown', :cid, :cb)"
            ),
            {"id": pid, "cid": clan_a, "cb": uuid.uuid4()},
        )
    # Marriage edge owned by clan_b but referencing clan_a's person p1.
    await async_session.execute(
        sa.text(
            "INSERT INTO marriages (id, person1_id, person2_id, created_by_clan_id, status, created_by) "
            "VALUES (:id, :p1, :p2, :cid, 'married', :cb)"
        ),
        {"id": uuid.uuid4(), "p1": p1, "p2": p2, "cid": clan_b, "cb": uuid.uuid4()},
    )
    await async_session.commit()

    port = SqlAlchemyPersonQueryPort(async_session)
    assert await port.get_marriages(clan_a, p1) == []  # clan_a must not see clan_b's edge
    assert len(await port.get_marriages(clan_b, p1)) == 1
```

- [ ] **Step 2: Run the test — confirm it fails**

Run: `cd backend && uv run pytest tests/integration/test_person_projection_isolation.py -v`
Expected: FAIL — `get_marriages(person_id)` takes one arg (TypeError); the current query ignores clan and would return the clan_b edge for clan_a.

- [ ] **Step 3: Update the query port protocol**

In `app/domain/person/query_port.py`, change the two signatures:

```python
    async def get_marriages(self, clan_id: uuid.UUID, person_id: uuid.UUID) -> list[dict[str, Any]]:
        """Fetch marriages for a person, scoped to the active clan."""
        ...

    async def get_parent_child_links(
        self, clan_id: uuid.UUID, person_id: uuid.UUID
    ) -> list[dict[str, Any]]:
        """Fetch parent-child links for a person, scoped to the active clan."""
        ...
```

- [ ] **Step 4: Scope the SQLAlchemy implementation**

In `person_query_port.py`, replace `get_marriages` (lines 31-39) and `get_parent_child_links` (lines 41-49):

```python
    async def get_marriages(
        self, clan_id: uuid.UUID, person_id: uuid.UUID
    ) -> list[dict[str, Any]]:
        result = await self._session.execute(
            select(Marriage).where(
                or_(Marriage.person1_id == person_id, Marriage.person2_id == person_id),
                Marriage.created_by_clan_id == clan_id,
                Marriage.is_deleted.is_(False),
            )
        )
        marriages = result.scalars().all()
        return [MarriageResponse.model_validate(m).model_dump() for m in marriages]

    async def get_parent_child_links(
        self, clan_id: uuid.UUID, person_id: uuid.UUID
    ) -> list[dict[str, Any]]:
        result = await self._session.execute(
            select(ParentChild).where(
                or_(ParentChild.parent_id == person_id, ParentChild.child_id == person_id),
                ParentChild.created_by_clan_id == clan_id,
                ParentChild.is_deleted.is_(False),
            )
        )
        links = result.scalars().all()
        return [ParentChildResponse.model_validate(link).model_dump() for link in links]
```

- [ ] **Step 5: Thread `clan_id` through the application handler**

In `app/application/person/handlers.py`, update `PersonQueryHandler.get_marriages` (line 177) and `get_parent_child` (line ~183):

```python
    async def get_marriages(self, clan_id: uuid.UUID, person_id: uuid.UUID) -> list[dict[str, Any]]:
        return await self._query_port.get_marriages(clan_id, person_id)

    async def get_parent_child(
        self, clan_id: uuid.UUID, person_id: uuid.UUID
    ) -> list[dict[str, Any]]:
        return await self._query_port.get_parent_child_links(clan_id, person_id)
```

(Read the exact current method names/bodies first; match them. Keep the method name `get_parent_child` as the route calls it.)

- [ ] **Step 6: Pass `clan_id` at the 3 call sites in persons.py**

Update the call sites (line 195 in the aggregate detail endpoint, line 420 in `person_marriages`, and the `person_parent_child` route's `handler.get_parent_child(person_id)`): pass `clan_id` first, e.g. `handler.get_marriages(clan_id, person_id)` and `handler.get_parent_child(clan_id, person_id)`. The `clan_id` is in scope at all three (each route injects `clan_id = Depends(get_current_clan_id)`); for line 195 confirm the enclosing function has `clan_id` and use it.

- [ ] **Step 7: Run tests**

Run: `cd backend && uv run pytest tests/integration/test_person_projection_isolation.py tests/test_persons.py -v`
Expected: isolation test PASSES; existing person tests still pass (fix any that called `get_marriages(person_id)` with the old arity, updating to the new signature; note any such change).

- [ ] **Step 8: Lint + commit**

```bash
cd backend && uvx ruff check app/domain/person/query_port.py app/infrastructure/persistence/person_query_port.py app/application/person/handlers.py app/api/v1/persons.py tests/integration/test_person_projection_isolation.py
git add -A && git commit -m "fix(isolation): scope person marriage/parent-child projections to active clan"
```

---

## Task 3: Authorize claim listing against the path clan

**Files:**
- Modify: `backend/app/api/v1/claims.py:44-62`
- Create: `backend/tests/unit/api/test_claims_clan_guard.py`

**Interfaces:**
- Consumes: `get_current_clan_id` (resolves + validates the caller's active clan from the `X-Current-Clan-Id` header against approved memberships).
- Produces: `list_clan_claims` raises `HTTPException(403)` when the path `{clan_id}` differs from the caller's active clan, so an admin of clan A cannot read clan B's claims by changing the path.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/api/__init__.py` if missing (it already exists per the repo layout — skip if present), then create `backend/tests/unit/api/test_claims_clan_guard.py`. Call the route coroutine directly with explicit args (bypassing FastAPI DI):

```python
"""list_clan_claims must reject a path clan that differs from the caller's active clan."""

import uuid

import pytest
from fastapi import HTTPException

from app.api.v1 import claims


class _FakeHandler:
    async def list_clan_claims(self, *, clan_id, status, page, page_size):
        from types import SimpleNamespace

        return SimpleNamespace(model_dump=lambda: {"claims": [], "total": 0})


@pytest.mark.asyncio
async def test_list_clan_claims_rejects_path_clan_mismatch():
    path_clan = uuid.uuid4()
    active_clan = uuid.uuid4()  # different → caller is not acting in the path clan
    with pytest.raises(HTTPException) as exc:
        await claims.list_clan_claims(
            clan_id=path_clan,
            status=None,
            page=1,
            page_size=20,
            active_clan_id=active_clan,
            user=object(),
            handler=_FakeHandler(),
            fields=None,
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_list_clan_claims_allows_matching_clan():
    clan = uuid.uuid4()
    result = await claims.list_clan_claims(
        clan_id=clan,
        status=None,
        page=1,
        page_size=20,
        active_clan_id=clan,
        user=object(),
        handler=_FakeHandler(),
        fields=None,
    )
    assert result == {"claims": [], "total": 0}
```

- [ ] **Step 2: Run — confirm it fails**

Run: `cd backend && uv run pytest tests/unit/api/test_claims_clan_guard.py -v`
Expected: FAIL — `list_clan_claims` has no `active_clan_id` parameter yet (TypeError), and no 403 guard exists.

- [ ] **Step 3: Add the active-clan guard to the route**

In `app/api/v1/claims.py`, add the import and the dependency + guard. Add to the imports at the top:

```python
from app.core.security import get_current_clan_id
```

Update the `list_clan_claims` signature to inject the active clan and guard it (add the `active_clan_id` parameter after `user` and the check as the first statement in the body):

```python
async def list_clan_claims(
    clan_id: uuid.UUID,
    status: str | None = Query(None, description="Filter by status (e.g., PENDING)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: UserProfile = Depends(RequireClanRole(["admin", "editor"])),
    active_clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: ClaimQueryHandler = Depends(get_claim_query_handler),
    fields: str | None = Query(None),
) -> dict[str, Any]:
    """List paginated identity claims for persons created by this clan."""
    if clan_id != active_clan_id:
        raise HTTPException(
            status_code=403, detail="Path clan does not match your active clan"
        )
    paginated = await handler.list_clan_claims(
        clan_id=clan_id, status=status, page=page, page_size=page_size
    )
    ...
```

Add `from fastapi import HTTPException` to the existing fastapi import line if not present. `RequireClanRole(["admin","editor"])` already confirms the caller is admin/editor of their active clan; combined with the guard, the caller must be admin/editor of the path clan. (Write endpoints — approve/reject/unlink/prelink — are already protected by `_verify_admin_access` against the claim's actual clan, so they don't need this guard.)

- [ ] **Step 4: Run — confirm pass**

Run: `cd backend && uv run pytest tests/unit/api/test_claims_clan_guard.py -v`
Expected: both tests PASS.

- [ ] **Step 5: Lint + commit**

```bash
cd backend && uvx ruff check app/api/v1/claims.py tests/unit/api/test_claims_clan_guard.py
git add -A && git commit -m "fix(isolation): authorize claim listing against the path clan, not just the header"
```

---

## Task 4: Pin the update_person viewer carve-out (documentation + tests)

**Files:**
- Modify: `backend/app/api/v1/persons.py` (the `update_person` route — comment only) and `backend/app/application/person/handlers.py:84-115` (comment only)
- Create: `backend/tests/unit/application/test_person_update_authorization.py`

**Interfaces:**
- Consumes: `PersonCommandHandler.update(cmd: UpdatePerson)` where `cmd.actor.role` is the caller's resolved clan role and `cmd.changes` is the field dict. Authorization: a `viewer` may update ONLY their own linked person (`UserProfile.person_id == cmd.person_id`) and ONLY whitelisted fields; `editor`/`admin` may update freely.
- Produces: no behavior change — tests that pin the existing authorization, plus comments explaining why the route is `RequireViewer`.

**Context (design correction):** the SP-2 design said to change `update_person` to `RequireEditor`. That is WRONG: the route is `RequireViewer` on purpose so the handler's self-edit carve-out can run. Keep `RequireViewer`. This task makes the intent explicit and regression-proof; it does not change the gate.

- [ ] **Step 1: Write the authorization tests (they should PASS against current code — they pin behavior)**

Create `backend/tests/unit/application/test_person_update_authorization.py`. Use fakes for the repo + uow + session, exercising `PersonCommandHandler.update`:

```python
"""Pin update_person authorization: viewers edit only their own person, whitelisted fields."""

import uuid

import pytest

from app.application.person.commands import UpdatePerson
from app.application.person.handlers import PersonCommandHandler
from app.domain.shared.exceptions import ForbiddenError
from app.domain.shared.value_objects import ActorInfo


class _PersonEntity:
    def __init__(self):
        self.id = uuid.uuid4()
        self.changes_applied = None

    def update(self, changes, actor, clan_id):
        self.changes_applied = changes


class _Profile:
    def __init__(self, person_id):
        self.person_id = person_id


class _FakeSession:
    def __init__(self, profile):
        self._profile = profile

    async def get(self, model, key):
        return self._profile


class _FakeUow:
    def __init__(self, profile):
        self.session = _FakeSession(profile)
        self.commits = 0

    def track(self, agg):
        pass

    async def commit(self):
        self.commits += 1


class _FakeRepo:
    def __init__(self, person):
        self._person = person

    async def get_in_clan(self, person_id, clan_id):
        return self._person

    async def save(self, person):
        pass


def _actor(role, user_id):
    # ActorInfo carries user_id + role; construct via from_jwt-compatible shape.
    return ActorInfo(user_id=user_id, role=role)


@pytest.mark.asyncio
async def test_viewer_can_edit_own_whitelisted_field():
    person = _PersonEntity()
    uid = uuid.uuid4()
    handler = PersonCommandHandler(_FakeRepo(person), _FakeUow(_Profile(person.id)))
    cmd = UpdatePerson(
        person_id=person.id, clan_id=uuid.uuid4(),
        actor=_actor("viewer", uid), changes={"phone": "0900000000"},
    )
    await handler.update(cmd)
    assert person.changes_applied == {"phone": "0900000000"}


@pytest.mark.asyncio
async def test_viewer_cannot_edit_other_person():
    person = _PersonEntity()
    uid = uuid.uuid4()
    # profile is linked to a DIFFERENT person
    handler = PersonCommandHandler(_FakeRepo(person), _FakeUow(_Profile(uuid.uuid4())))
    cmd = UpdatePerson(
        person_id=person.id, clan_id=uuid.uuid4(),
        actor=_actor("viewer", uid), changes={"phone": "x"},
    )
    with pytest.raises(ForbiddenError):
        await handler.update(cmd)


@pytest.mark.asyncio
async def test_viewer_cannot_edit_nonwhitelisted_field():
    person = _PersonEntity()
    uid = uuid.uuid4()
    handler = PersonCommandHandler(_FakeRepo(person), _FakeUow(_Profile(person.id)))
    cmd = UpdatePerson(
        person_id=person.id, clan_id=uuid.uuid4(),
        actor=_actor("viewer", uid), changes={"full_name": "Hacked"},
    )
    with pytest.raises(ForbiddenError):
        await handler.update(cmd)


@pytest.mark.asyncio
async def test_editor_can_edit_any_field():
    person = _PersonEntity()
    handler = PersonCommandHandler(_FakeRepo(person), _FakeUow(_Profile(uuid.uuid4())))
    cmd = UpdatePerson(
        person_id=person.id, clan_id=uuid.uuid4(),
        actor=_actor("editor", uuid.uuid4()), changes={"full_name": "New Name"},
    )
    await handler.update(cmd)
    assert person.changes_applied == {"full_name": "New Name"}
```

Before running, read `app/domain/shared/value_objects.py` to confirm the `ActorInfo` constructor field names (`user_id`, `role`) and `app/application/person/commands.py` for `UpdatePerson`'s fields; adjust the `_actor(...)` construction and `UpdatePerson(...)` kwargs to match exactly. If `ActorInfo` requires more fields, populate them minimally.

- [ ] **Step 2: Run the tests**

Run: `cd backend && uv run pytest tests/unit/application/test_person_update_authorization.py -v`
Expected: all 4 PASS against the current handler (they pin existing behavior). If any fails, the handler's authorization differs from the documented contract — STOP and report it (do not weaken the test).

- [ ] **Step 3: Document the intentional `RequireViewer` on the route**

In `app/api/v1/persons.py`, above the `update_person` route's `user_role: ClanRole = RequireViewer` line, add a comment:

```python
    # RequireViewer (not RequireEditor) is intentional: the handler grants a viewer
    # edit access ONLY to their own linked person and ONLY whitelisted fields, while
    # editors/admins get full edits. See PersonCommandHandler.update.
```

And in `app/application/person/handlers.py`, above the `if cmd.actor.role == "viewer":` block (line 90), add:

```python
        # Self-edit carve-out: a viewer may edit ONLY their own linked person and ONLY
        # the whitelisted fields below. Editors/admins (role != "viewer") skip this and
        # may edit any field. This is why the route uses RequireViewer, not RequireEditor.
```

- [ ] **Step 4: Lint + commit**

```bash
cd backend && uvx ruff check app/api/v1/persons.py app/application/person/handlers.py tests/unit/application/test_person_update_authorization.py
git add -A && git commit -m "test(persons): pin update_person viewer self-edit carve-out; document intent"
```

---

## Done criteria (SP-2B)

- A clan cannot read another clan's marriage / parent-child by ID (returns not-found) — `test_relationship_isolation.py` green.
- Person marriage/parent-child projections only surface the active clan's edges — `test_person_projection_isolation.py` green.
- `list_clan_claims` rejects a path clan that differs from the caller's active clan — `test_claims_clan_guard.py` green.
- `update_person` viewer carve-out is pinned by tests (own+whitelist OK; other person / non-whitelist field → Forbidden; editor full) — `test_person_update_authorization.py` green; `RequireViewer` documented as intentional.
- All existing tests still pass (any cross-clan 403 relationship assertions updated to 404 with a note).

## Notes for the executor

- Run pytest from `backend/`. Integration tests need `docker compose up -d pgdb`.
- The cross-clan response for relationship update/delete changes from 403 to 404 — this is intentional (strict isolation hides existence). Update any existing test that encoded 403 and call it out in the report.
- Do NOT change `update_person`'s `RequireViewer` to `RequireEditor` — see Task 4 context.
