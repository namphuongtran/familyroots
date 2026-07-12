# Data Integrity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the five 2026-07-12 data-integrity findings: required optimistic concurrency on persons/marriages/parent_child (H1), last-admin race lock (C1), re-validation on relationship updates (H2), spouse_order uniqueness (M3), unbounded cycle detection (M1).

**Architecture:** Spec = `docs/superpowers/specs/2026-07-12-data-integrity-design.md`. One migration (`015_data_integrity`) adds `version` columns + a partial unique index. OCC is enforced by an atomic conditional `UPDATE ... WHERE version = :expected` in the repositories; the last-admin invariant by `SELECT ... FOR UPDATE` over the clan's admin rows; H2/M3 by extending the domain validator with exclusion params; M1 by an unbounded recursive CTE.

**Tech Stack:** FastAPI, SQLAlchemy 2 async (psycopg), Alembic, Pydantic v2, pytest-asyncio against real Postgres.

## Global Constraints

- Quality gate after EVERY task (from `backend/`): `uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports`
- mypy MUST be `uv run mypy app/ tests/` (bare `uvx mypy` breaks on the pydantic plugin).
- Migration revision ids ≤32 chars, single linear chain; new head: `015_data_integrity` revises `014_drop_date_approx`.
- Handlers/domain raise `app.domain.shared.exceptions.*` ONLY (never `app.core.exceptions` — import-linter ratchet must not grow).
- Every new error code gets `error.<code>` entries in ALL FOUR i18n files (`app/i18n/{vi,en,fr,zh}.json`) — `tests/unit/test_i18n_coverage.py` fails CI otherwise.
- Integration tests need Postgres: `docker compose up -d pgdb` (throwaway DB via the `migrated_db_url`/`sync_engine`/session fixtures in `tests/integration/conftest.py`).
- Do NOT `git add -A`; stage explicit paths.
- New error codes in this PR: `stale_write`, `clan.last_admin_cannot_remove`, `relationship.duplicate_spouse_order` — each also gets a row in `docs/contracts/error-codes.md` (Task 7).
- OCC contract (frozen): PATCH body requires `expected_version: int (>=1)`; missing → 422; mismatch → 409 `stale_write` with `detail={"current_version": <int>}`; success increments `version` by 1 and echoes it.

---

### Task 1: Migration 015 + ORM `version` columns + spouse_order unique index

**Files:**
- Create: `backend/migrations/versions/015_data_integrity.py`
- Modify: `backend/app/models/person.py` (after the audit columns, ~line 78)
- Modify: `backend/app/models/marriage.py` (after `spouse_order`)
- Modify: `backend/app/models/parent_child.py` (after `birth_order`)
- Test: `backend/tests/integration/test_data_integrity_migration.py`

**Interfaces:**
- Consumes: migration chain head `014_drop_date_approx`.
- Produces: columns `persons.version`, `marriages.version`, `parent_child.version` (INTEGER NOT NULL server_default '1'); partial unique index `uq_marriages_spouse_order`. ORM models gain `version: Mapped[int]`. Later tasks rely on the column name `version` exactly.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/integration/test_data_integrity_migration.py
"""Migration 015: version columns + spouse_order partial unique index."""

import uuid

import pytest
import sqlalchemy as sa

pytestmark = pytest.mark.integration


def test_version_columns_exist_default_1(sync_engine):
    insp = sa.inspect(sync_engine)
    for table in ("persons", "marriages", "parent_child"):
        cols = {c["name"]: c for c in insp.get_columns(table)}
        assert "version" in cols, f"{table}.version missing"
        assert cols["version"]["nullable"] is False
        assert "1" in str(cols["version"]["default"])


def test_spouse_order_unique_index_blocks_duplicates(sync_engine, seeded_clan_and_persons):
    """Two active marriages of the same person1 with the same spouse_order must
    violate uq_marriages_spouse_order. Divorced/soft-deleted rows must NOT collide."""
    clan_id, p1, p2, p3 = seeded_clan_and_persons
    ins = sa.text(
        """INSERT INTO marriages
           (id, person1_id, person2_id, created_by_clan_id, status, spouse_order,
            is_deleted, created_by)
           VALUES (:id, :p1, :p2, :clan, :status, :so, :deleted, :actor)"""
    )
    actor = str(uuid.uuid4())
    with sync_engine.begin() as conn:
        conn.execute(ins, dict(id=str(uuid.uuid4()), p1=p1, p2=p2, clan=clan_id,
                               status="married", so=1, deleted=False, actor=actor))
    with pytest.raises(sa.exc.IntegrityError):
        with sync_engine.begin() as conn:
            conn.execute(ins, dict(id=str(uuid.uuid4()), p1=p1, p2=p3, clan=clan_id,
                                   status="married", so=1, deleted=False, actor=actor))
    # divorced row with same order is allowed
    with sync_engine.begin() as conn:
        conn.execute(ins, dict(id=str(uuid.uuid4()), p1=p1, p2=p3, clan=clan_id,
                               status="divorced", so=1, deleted=False, actor=actor))
```

Add a module-level `seeded_clan_and_persons` fixture in the same file that inserts one clan + three persons + memberships with raw SQL (mirror the insert helpers used in `tests/integration/test_tenant_isolation.py` — copy the minimal columns those inserts use).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/integration/test_data_integrity_migration.py -v`
Expected: FAIL — `persons.version missing`.

- [ ] **Step 3: Write the migration**

```python
# backend/migrations/versions/015_data_integrity.py
"""Data-integrity hardening: OCC version columns + spouse_order uniqueness.

- persons / marriages / parent_child gain `version INTEGER NOT NULL DEFAULT 1`
  (optimistic concurrency; PATCH requires expected_version, see ADR-017).
- Partial unique index guarantees a person1's ACTIVE marriages have distinct
  spouse_order (vợ cả/hai/ba ordering is deterministic).
- Pre-check: if existing data already violates spouse_order uniqueness, FAIL
  with the offending rows listed — the operator must resolve history manually;
  we never silently renumber a gia phả.

Revision ID: 015_data_integrity
Revises: 014_drop_date_approx
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "015_data_integrity"
down_revision: str | None = "014_drop_date_approx"
branch_labels = None
depends_on = None

_TABLES = ("persons", "marriages", "parent_child")


def upgrade() -> None:
    conn = op.get_bind()
    dupes = conn.execute(
        sa.text(
            """SELECT created_by_clan_id, person1_id, spouse_order, COUNT(*)
               FROM marriages
               WHERE spouse_order IS NOT NULL AND is_deleted = false
                 AND status = 'married'
               GROUP BY created_by_clan_id, person1_id, spouse_order
               HAVING COUNT(*) > 1"""
        )
    ).fetchall()
    if dupes:
        raise RuntimeError(
            "spouse_order duplicates exist; resolve before migrating: "
            + "; ".join(f"clan={r[0]} person1={r[1]} order={r[2]} x{r[3]}" for r in dupes)
        )

    for table in _TABLES:
        op.add_column(
            table,
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        )

    op.execute(
        """CREATE UNIQUE INDEX uq_marriages_spouse_order
           ON marriages (created_by_clan_id, person1_id, spouse_order)
           WHERE spouse_order IS NOT NULL AND is_deleted = false
             AND status = 'married'"""
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_marriages_spouse_order")
    for table in _TABLES:
        op.drop_column(table, "version")
```

- [ ] **Step 4: Add the ORM columns (all three models, same shape)**

In `backend/app/models/person.py`, `marriage.py`, `parent_child.py` add next to the audit columns:

```python
    # Optimistic concurrency (ADR-017): bumped by every repository UPDATE;
    # PATCH requests must present the matching expected_version.
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
```

(Import `Integer` from sqlalchemy where not already imported.)

- [ ] **Step 5: Run tests + drift gate**

Run: `cd backend && uv run pytest tests/integration/test_data_integrity_migration.py tests/integration/test_schema_baseline.py -v`
Expected: PASS (round-trip + autogenerate-no-diff prove model/migration agree).

- [ ] **Step 6: Full gate, then commit**

```bash
git add backend/migrations/versions/015_data_integrity.py backend/app/models/person.py backend/app/models/marriage.py backend/app/models/parent_child.py backend/tests/integration/test_data_integrity_migration.py
git commit -m "feat(backend): migration 015 — OCC version columns + spouse_order unique index (data-integrity)"
```

---

### Task 2: OCC end-to-end for persons

**Files:**
- Modify: `backend/app/domain/person/entity.py` (add `version` field, NOT in `_UPDATABLE_FIELDS`)
- Modify: `backend/app/infrastructure/persistence/person_mapper.py` (`to_domain`/`to_orm` carry version; `apply_to_orm` untouched)
- Modify: `backend/app/infrastructure/persistence/person_repository.py:161-169` (`save`)
- Modify: `backend/app/application/person/commands.py` (`UpdatePerson` gains `expected_version: int`)
- Modify: `backend/app/application/person/handlers.py:112-151` (`update` threads it)
- Modify: `backend/app/schemas/person.py` (`PersonUpdateRequest` + responses)
- Modify: `backend/app/api/v1/persons.py:363-385` (route pops `expected_version`)
- Modify: `backend/app/i18n/{vi,en,fr,zh}.json` (`error.stale_write`)
- Test: `backend/tests/integration/test_occ_persons.py`

**Interfaces:**
- Consumes: `version` column from Task 1.
- Produces: `SqlAlchemyPersonRepository.save(person, *, expected_version: int | None = None)` — `None` ⇒ unconditional update (delete/restore/claim paths unchanged) but STILL bumps version; int ⇒ conditional, raising `ConflictError("stale_write", detail={"current_version": n})` on mismatch. Tasks 3 mirrors this exact signature/behavior on the relationship repos. Response models emit `version: int`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/integration/test_occ_persons.py
"""Optimistic concurrency on PATCH /persons/{id} (H1)."""

import pytest

pytestmark = pytest.mark.integration

# Use the existing HTTP-flow fixtures (app client + seeded clan/editor auth) —
# mirror the setup used in tests/integration/test_auth_http_flow.py /
# test_person_precision_write_path.py (client, auth headers, created person).


async def test_patch_without_expected_version_is_422(client, editor_headers, person_id):
    resp = await client.patch(
        f"/api/v1/persons/{person_id}", json={"occupation": "Nông dân"},
        headers=editor_headers,
    )
    assert resp.status_code == 422


async def test_fresh_patch_increments_and_echoes_version(client, editor_headers, person_id):
    get1 = await client.get(f"/api/v1/persons/{person_id}", headers=editor_headers)
    v = get1.json()["data"]["version"]
    resp = await client.patch(
        f"/api/v1/persons/{person_id}",
        json={"occupation": "Quan triều Nguyễn", "expected_version": v},
        headers=editor_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["version"] == v + 1


async def test_stale_patch_is_409_stale_write_and_loses_nothing(
    client, editor_headers, person_id
):
    get1 = await client.get(f"/api/v1/persons/{person_id}", headers=editor_headers)
    v = get1.json()["data"]["version"]
    # Editor A wins:
    ok = await client.patch(
        f"/api/v1/persons/{person_id}",
        json={"biography": "Tiểu sử hai trang", "expected_version": v},
        headers=editor_headers,
    )
    assert ok.status_code == 200
    # Editor B (still holding v) loses with 409, and A's field survives:
    stale = await client.patch(
        f"/api/v1/persons/{person_id}",
        json={"occupation": "Thợ rèn", "expected_version": v},
        headers=editor_headers,
    )
    assert stale.status_code == 409
    body = stale.json()["error"]
    assert body["code"] == "stale_write"
    assert body["detail"]["current_version"] == v + 1
    after = await client.get(f"/api/v1/persons/{person_id}", headers=editor_headers)
    assert after.json()["data"]["biography"] == "Tiểu sử hai trang"


async def test_true_concurrent_patches_one_wins(person_handler_two_sessions, person_id):
    """Two INDEPENDENT sessions/handlers race the same expected_version.

    Exactly one succeeds; the other raises ConflictError('stale_write'). Build
    the two-session fixtures the same way tests/integration/test_claim_approval.py
    builds its concurrent handlers (two sessionmakers on the migrated DB)."""
    import asyncio

    handler_a, handler_b, current_version = person_handler_two_sessions
    results = await asyncio.gather(
        handler_a.update(make_update(person_id, {"biography": "A"}, current_version)),
        handler_b.update(make_update(person_id, {"occupation": "B"}, current_version)),
        return_exceptions=True,
    )
    failures = [r for r in results if isinstance(r, Exception)]
    assert len(failures) == 1
    assert getattr(failures[0], "code", "") == "stale_write"


async def test_soft_delete_also_bumps_version(client, admin_headers, editor_headers, person_id):
    get1 = await client.get(f"/api/v1/persons/{person_id}", headers=editor_headers)
    v = get1.json()["data"]["version"]
    await client.delete(f"/api/v1/persons/{person_id}", headers=admin_headers)
    await client.post(f"/api/v1/persons/{person_id}/restore", headers=admin_headers)
    stale = await client.patch(
        f"/api/v1/persons/{person_id}",
        json={"notes": "x", "expected_version": v},
        headers=editor_headers,
    )
    assert stale.status_code == 409  # delete+restore bumped version twice
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && uv run pytest tests/integration/test_occ_persons.py -v`
Expected: FAIL (422 test may accidentally pass; version-echo tests fail with KeyError 'version').

- [ ] **Step 3: Implement**

`entity.py` — inside the Person dataclass, next to the audit fields:

```python
    # Optimistic concurrency (ADR-017). Not client-updatable; the repository
    # bumps it on every successful UPDATE.
    version: int = 1
```

`person_mapper.py` — add `version=model.version` in `to_domain(...)` and `version=entity.version` in `to_orm(...)`. Do NOT add to `UPDATABLE_FIELDS`.

`person_repository.py` — replace `save`:

```python
    async def save(self, person: PersonEntity, *, expected_version: int | None = None) -> None:
        """Insert, or update with an optimistic-concurrency check (ADR-017).

        expected_version=None (delete/restore/claim paths) updates unconditionally
        but still bumps version so any concurrent PATCH sees a stale_write.
        """
        self._uow.track(person)
        existing = await self._session.get(PersonModel, person.id)
        if existing is None:
            self._session.add(to_orm(person))
            return

        values = {f: getattr(person, f) for f in UPDATABLE_FIELDS}
        stmt = (
            sql_update(PersonModel)
            .where(PersonModel.id == person.id)
            .values(**values, version=PersonModel.version + 1)
        )
        if expected_version is not None:
            stmt = stmt.where(PersonModel.version == expected_version)
        result = await self._session.execute(stmt)
        if result.rowcount == 0:
            current = await self._session.scalar(
                select(PersonModel.version).where(PersonModel.id == person.id)
            )
            raise ConflictError("stale_write", detail={"current_version": current})
        await self._session.refresh(existing)  # sync identity map with the core UPDATE
        person.version = existing.version
```

Imports to add: `from sqlalchemy import update as sql_update`, `from app.domain.shared.exceptions import ConflictError`, and `UPDATABLE_FIELDS` from the mapper.

`commands.py` — `UpdatePerson` gains `expected_version: int` (frozen dataclass field, no default).

`handlers.py::update` — pass it through: `await self._repo.save(person, expected_version=cmd.expected_version)` (the viewer whitelist logic is untouched — `expected_version` never enters `changes`).

`schemas/person.py`:
- `PersonUpdateRequest`: add `expected_version: int = Field(..., ge=1)` (required).
- `PersonResponse` and `PersonSummary`: add `version: int = 1` (default shields legacy dict read-paths; entity/ORM paths carry the real value).

`api/v1/persons.py::update_person`:

```python
    changes = body.model_dump(exclude_unset=True)
    expected_version = changes.pop("expected_version")
    person = await handler.update(
        UpdatePerson(
            person_id=person_id,
            clan_id=clan_id,
            actor=ActorInfo.from_jwt(current_user, user_role.value),
            changes=changes,
            expected_version=expected_version,
        )
    )
```

i18n ×4: `"error.stale_write"` — vi: `"Bản ghi đã được người khác sửa. Vui lòng tải lại và thử lại."`; en: `"This record was modified by someone else. Reload and try again."`; fr/zh: equivalent translations.

Fix any other `repo.save(person)` callers mypy flags (delete/restore/claim call sites need no change — keyword-only param with default).

- [ ] **Step 4: Run tests**

Run: `cd backend && uv run pytest tests/integration/test_occ_persons.py -q && uv run pytest -q`
Expected: PASS, full suite green (some existing PATCH-person tests will now need `expected_version` — update them to GET first or pass `expected_version=1` on freshly created persons; that churn belongs to this task).

- [ ] **Step 5: Full gate, commit**

```bash
git add backend/app backend/tests backend/migrations
git commit -m "feat(backend): required optimistic concurrency on persons PATCH (stale_write 409)"
```

---

### Task 3: OCC for marriages + parent_child (mirror of Task 2)

**Files:**
- Modify: `backend/app/domain/relationship/entities.py` (both dataclasses: `version: int = 1`; NOT in either `_*_UPDATABLE_FIELDS`)
- Modify: `backend/app/infrastructure/persistence/relationship_repository.py` (`_marriage_to_domain`/`_marriage_to_orm`/`_pc_to_domain`/`_pc_to_orm` carry version; both `save()` methods → conditional-UPDATE shape from Task 2, using `_MARRIAGE_UPDATABLE`/`_PC_UPDATABLE` as the values source)
- Modify: `backend/app/application/relationship/commands.py` (`UpdateMarriage`/`UpdateParentChild` gain `expected_version: int`)
- Modify: `backend/app/application/relationship/handlers.py:63-71,117-125` (thread to `repo.save(..., expected_version=...)`)
- Modify: `backend/app/schemas/marriage.py` (`MarriageUpdateRequest` + `MarriageResponse`), `backend/app/schemas/parent_child.py` (same)
- Modify: `backend/app/api/v1/relationships.py:95-113,180-197` (pop `expected_version` from changes)
- Test: `backend/tests/integration/test_occ_relationships.py`

**Interfaces:**
- Consumes: Task 2's exact save signature convention: `save(entity, *, expected_version: int | None = None)`, `ConflictError("stale_write", detail={"current_version": n})`.
- Produces: `MarriageResponse.version`, `ParentChildResponse.version`; PATCH marriage/parent-child require `expected_version`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/integration/test_occ_relationships.py
"""Optimistic concurrency on marriage + parent-child PATCH (H1)."""
import pytest

pytestmark = pytest.mark.integration

# Fixtures: clan + editor auth + two persons + one marriage + one parent-child
# link created via the API (POST returns version=1 in the body).


async def test_marriage_patch_without_expected_version_is_422(client, editor_headers, marriage_id):
    resp = await client.patch(
        f"/api/v1/relationships/marriages/{marriage_id}",
        json={"notes": "x"}, headers=editor_headers,
    )
    assert resp.status_code == 422


async def test_marriage_fresh_patch_increments_version(client, editor_headers, marriage_id):
    get1 = await client.get(f"/api/v1/relationships/marriages/{marriage_id}", headers=editor_headers)
    v = get1.json()["data"]["version"]
    resp = await client.patch(
        f"/api/v1/relationships/marriages/{marriage_id}",
        json={"marriage_place": "Huế", "expected_version": v}, headers=editor_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["version"] == v + 1


async def test_marriage_stale_patch_is_409(client, editor_headers, marriage_id):
    get1 = await client.get(f"/api/v1/relationships/marriages/{marriage_id}", headers=editor_headers)
    v = get1.json()["data"]["version"]
    await client.patch(
        f"/api/v1/relationships/marriages/{marriage_id}",
        json={"notes": "first", "expected_version": v}, headers=editor_headers,
    )
    stale = await client.patch(
        f"/api/v1/relationships/marriages/{marriage_id}",
        json={"notes": "second", "expected_version": v}, headers=editor_headers,
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "stale_write"
    assert stale.json()["error"]["detail"]["current_version"] == v + 1


async def test_parent_child_full_occ_cycle(client, editor_headers, parent_child_id):
    # 422 missing version
    r0 = await client.patch(
        f"/api/v1/relationships/parent-child/{parent_child_id}",
        json={"notes": "x"}, headers=editor_headers,
    )
    assert r0.status_code == 422
    # fresh increments
    get1 = await client.get(f"/api/v1/relationships/parent-child/{parent_child_id}", headers=editor_headers)
    v = get1.json()["data"]["version"]
    r1 = await client.patch(
        f"/api/v1/relationships/parent-child/{parent_child_id}",
        json={"birth_order": 2, "expected_version": v}, headers=editor_headers,
    )
    assert r1.status_code == 200 and r1.json()["data"]["version"] == v + 1
    # stale 409
    r2 = await client.patch(
        f"/api/v1/relationships/parent-child/{parent_child_id}",
        json={"birth_order": 3, "expected_version": v}, headers=editor_headers,
    )
    assert r2.status_code == 409 and r2.json()["error"]["code"] == "stale_write"
```

(If the GET-single routes for marriage/parent-child return via `{"data": ...}` with `version` absent, that is the bug this task fixes — the assertion stands.) Also add `from sqlalchemy import update as sql_update` and `from app.domain.shared.exceptions import ConflictError` imports in `relationship_repository.py` during Step 3.
- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/integration/test_occ_relationships.py -v` → FAIL.
- [ ] **Step 3: Implement** exactly per the Files list; both `save()` bodies:

```python
    async def save(self, marriage: MarriageEntity, *, expected_version: int | None = None) -> None:
        self._uow.track(marriage)
        existing = await self._session.get(MarriageModel, marriage.id)
        if existing is None:
            self._session.add(_marriage_to_orm(marriage))
            return
        values = {f: getattr(marriage, f) for f in _MARRIAGE_UPDATABLE}
        stmt = (
            sql_update(MarriageModel)
            .where(MarriageModel.id == marriage.id)
            .values(**values, version=MarriageModel.version + 1)
        )
        if expected_version is not None:
            stmt = stmt.where(MarriageModel.version == expected_version)
        result = await self._session.execute(stmt)
        if result.rowcount == 0:
            current = await self._session.scalar(
                select(MarriageModel.version).where(MarriageModel.id == marriage.id)
            )
            raise ConflictError("stale_write", detail={"current_version": current})
        await self._session.refresh(existing)
        marriage.version = existing.version
```

(ParentChild identical with `_PC_UPDATABLE`/`ParentChildModel`.) Schemas: `expected_version: int = Field(..., ge=1)` on both UpdateRequests; `version: int = 1` on both Responses. Routes pop it from `changes` before building the command (both PATCH routes).

- [ ] **Step 4: Run tests + full suite** — update any existing marriage/parent-child PATCH tests to send `expected_version`.
- [ ] **Step 5: Full gate, commit**

```bash
git add backend/app backend/tests
git commit -m "feat(backend): optimistic concurrency on marriage + parent-child PATCH"
```

---

### Task 4: Last-admin invariant under lock (C1)

**Files:**
- Modify: `backend/app/infrastructure/persistence/clan_repository.py` (new `lock_admin_count`)
- Modify: `backend/app/application/clan/handlers.py:101-159` (`change_role`, `remove_user`)
- Modify: `backend/app/i18n/{vi,en,fr,zh}.json` (`error.clan.last_admin_cannot_remove`)
- Test: `backend/tests/integration/test_last_admin_race.py`

**Interfaces:**
- Consumes: existing `get_user_clan_role`, `count_admins` (kept), `UserClanRole` model.
- Produces: `SqlAlchemyClanRepository.lock_admin_count(clan_id) -> int` — locks the clan's approved-admin rows `FOR UPDATE` and returns their count. Error codes: existing `clan.last_admin_cannot_demote` (demote path, now ANY target) + new `clan.last_admin_cannot_remove`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/integration/test_last_admin_race.py
"""C1: a clan must always keep >= 1 approved admin, even under concurrency."""

import asyncio
import pytest

pytestmark = pytest.mark.integration

# Fixtures: build a clan with exactly two approved admins (user A, user B) via
# raw-SQL inserts (mirror tests/integration/test_tenant_isolation.py helpers),
# plus two INDEPENDENT AsyncSession factories bound to the same migrated DB —
# copy the two-session pattern from tests/integration/test_claim_approval.py.


async def test_demote_other_admin_when_two_exist_succeeds(clan_handler_factory, two_admin_clan):
    clan_id, admin_a, admin_b = two_admin_clan
    handler = clan_handler_factory()
    await handler.change_role(make_change_role(clan_id, actor=admin_a, target=admin_b, new_role="viewer"))
    # fine: one admin remains


async def test_demote_last_admin_any_target_is_403(clan_handler_factory, one_admin_clan):
    clan_id, admin_a, other_admin_gone = one_admin_clan
    handler = clan_handler_factory()
    with pytest.raises(ForbiddenError) as exc:
        await handler.change_role(make_change_role(clan_id, actor=admin_a, target=admin_a, new_role="editor"))
    assert exc.value.code == "clan.last_admin_cannot_demote"


async def test_remove_last_admin_is_403(clan_handler_factory, two_admin_clan):
    clan_id, admin_a, admin_b = two_admin_clan
    handler = clan_handler_factory()
    await handler.remove_user(make_remove(clan_id, actor=admin_a, target=admin_b))  # ok, 2 -> 1
    handler2 = clan_handler_factory()
    with pytest.raises(ForbiddenError) as exc:
        # a (hypothetical) second admin path removing the survivor
        await handler2.remove_user(make_remove(clan_id, actor=admin_b, target=admin_a))
    assert exc.value.code == "clan.last_admin_cannot_remove"


async def test_concurrent_mutual_demotion_leaves_one_admin(two_sessions_two_admin_clan):
    """THE race: A demotes B while B demotes A. Exactly one must succeed."""
    clan_id, handler_a, handler_b, admin_a, admin_b = two_sessions_two_admin_clan
    results = await asyncio.gather(
        handler_a.change_role(make_change_role(clan_id, actor=admin_a, target=admin_b, new_role="viewer")),
        handler_b.change_role(make_change_role(clan_id, actor=admin_b, target=admin_a, new_role="viewer")),
        return_exceptions=True,
    )
    failures = [r for r in results if isinstance(r, Exception)]
    assert len(failures) == 1 and getattr(failures[0], "code", "") == "clan.last_admin_cannot_demote"
    # and the DB still has exactly one approved admin (assert via a fresh session count)
```

Write the helper constructors (`make_change_role`, `make_remove`) inline using `ChangeUserRole`/`RemoveUser` command dataclasses + `ActorInfo`.

- [ ] **Step 2: Run to verify failure** — the mutual-demotion test must FAIL on current code (both succeed → 0 failures). Expected: FAIL.
- [ ] **Step 3: Implement**

`clan_repository.py`:

```python
    async def lock_admin_count(self, clan_id: uuid.UUID) -> int:
        """Lock the clan's approved-admin rows and return their count.

        FOR UPDATE serializes every operation that could reduce the admin set;
        the second concurrent reducer re-reads post-commit state and sees the
        true remaining count (C1 last-admin race, ADR spec 2026-07-12)."""
        result = await self._session.execute(
            select(UserClanRole.id)
            .where(
                UserClanRole.clan_id == clan_id,
                UserClanRole.role == "admin",
                UserClanRole.is_approved.is_(True),
            )
            .with_for_update()
        )
        return len(result.scalars().all())
```

`handlers.py::change_role` — replace the self-only guard block with:

```python
        # Invariant: a clan always keeps >= 1 approved admin (any target, not
        # just self-demotion). lock_admin_count takes FOR UPDATE row locks so
        # concurrent demotions serialize instead of both passing the count.
        if ucr.role == "admin" and cmd.new_role != "admin":
            admin_count = await self._repo.lock_admin_count(cmd.clan_id)
            if admin_count <= 1:
                raise ForbiddenError("clan.last_admin_cannot_demote")
```

`handlers.py::remove_user` — after the `user_not_found` check:

```python
        if ucr.role == "admin":
            admin_count = await self._repo.lock_admin_count(cmd.clan_id)
            if admin_count <= 1:
                raise ForbiddenError("clan.last_admin_cannot_remove")
```

i18n ×4: `"error.clan.last_admin_cannot_remove"` — vi: `"Không thể xóa quản trị viên cuối cùng của dòng họ."`; en: `"Cannot remove the clan's last admin."`; fr/zh equivalents.

- [ ] **Step 4: Sabotage check (manual, then revert)** — temporarily change `.with_for_update()` to a plain select and confirm `test_concurrent_mutual_demotion_leaves_one_admin` FAILS; restore. Note the result in the task report.
- [ ] **Step 5: Run tests + full gate, commit**

```bash
git add backend/app backend/tests
git commit -m "fix(backend): last-admin invariant under FOR UPDATE — any demote/remove path (C1)"
```

---

### Task 5: Re-validate relationship updates (H2) + spouse_order validator (M3)

**Files:**
- Modify: `backend/app/domain/relationship/validator.py` (port protocol + validator methods)
- Modify: `backend/app/infrastructure/persistence/relationship_repository.py:195-257` (`SqlAlchemyRelationshipQueryPort`: exclusion params + new `has_spouse_order_conflict`)
- Modify: `backend/app/application/relationship/handlers.py` (marriage create/update + parent-child update wiring)
- Modify: `backend/app/i18n/{vi,en,fr,zh}.json` (`error.relationship.duplicate_spouse_order`)
- Test: `backend/tests/integration/test_relationship_update_validation.py`

**Interfaces:**
- Consumes: validator/query-port shapes shown above; Task 3's `expected_version` threading (update handlers already modified there — this task adds validation BEFORE `entity.update(...)`).
- Produces:
  - `validate_parent_child(parent_id, child_id, relationship_type, clan_id, *, exclude_link_id: uuid.UUID | None = None, check_cycle: bool = True)`
  - `count_bio_parents(child_id, clan_id, exclude_link_id: uuid.UUID | None = None)`
  - `check_duplicate_marriage(person1_id, person2_id, clan_id, *, exclude_marriage_id: uuid.UUID | None = None)` / `has_active_marriage(..., exclude_marriage_id=None)`
  - `check_spouse_order(person1_id, spouse_order, clan_id, *, exclude_marriage_id=None)` raising `ConflictError("relationship.duplicate_spouse_order")` / port `has_spouse_order_conflict(...) -> bool`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/integration/test_relationship_update_validation.py
"""H2: PATCH must not bypass create-time rules. M3: spouse_order 409."""
import pytest

pytestmark = pytest.mark.integration

# HTTP-level fixtures: clan + editor auth + persons with exact birth dates.
# All PATCH bodies include the now-required expected_version (GET first).


async def test_patch_adopted_to_biological_blocked_by_bio_limit(client, editor_headers, child_with_two_bio_parents_and_one_adopted):
    link_id, v = child_with_two_bio_parents_and_one_adopted
    resp = await client.patch(
        f"/api/v1/relationships/parent-child/{link_id}",
        json={"relationship_type": "biological", "expected_version": v},
        headers=editor_headers,
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "relationship.too_many_biological_parents"


async def test_patch_adopted_to_biological_blocked_by_age_gap(client, editor_headers, adopted_link_age_gap_5y):
    link_id, v = adopted_link_age_gap_5y
    resp = await client.patch(
        f"/api/v1/relationships/parent-child/{link_id}",
        json={"relationship_type": "biological", "expected_version": v},
        headers=editor_headers,
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "relationship.parent_too_young"


async def test_legitimate_type_correction_still_succeeds(client, editor_headers, bio_link_valid):
    link_id, v = bio_link_valid  # single bio parent, 30y gap
    resp = await client.patch(
        f"/api/v1/relationships/parent-child/{link_id}",
        json={"relationship_type": "adopted", "expected_version": v},
        headers=editor_headers,
    )
    assert resp.status_code == 200  # bio->adopted relaxes rules; and self-exclusion
                                     # means flipping back later doesn't count itself


async def test_divorced_to_married_blocked_when_duplicate_active(client, editor_headers, divorced_marriage_with_active_duplicate):
    marriage_id, v = divorced_marriage_with_active_duplicate
    resp = await client.patch(
        f"/api/v1/relationships/marriages/{marriage_id}",
        json={"status": "married", "expected_version": v},
        headers=editor_headers,
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "relationship.duplicate_marriage"


async def test_duplicate_spouse_order_create_is_409(client, editor_headers, father_with_wife_order_1):
    father_id, other_wife_id = father_with_wife_order_1
    resp = await client.post(
        "/api/v1/relationships/marriages",
        json={"person1_id": father_id, "person2_id": other_wife_id, "spouse_order": 1},
        headers=editor_headers,
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "relationship.duplicate_spouse_order"


async def test_spouse_order_update_collision_is_409(client, editor_headers, father_two_wives_orders_1_2):
    marriage2_id, v2 = father_two_wives_orders_1_2
    resp = await client.patch(
        f"/api/v1/relationships/marriages/{marriage2_id}",
        json={"spouse_order": 1, "expected_version": v2},
        headers=editor_headers,
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "relationship.duplicate_spouse_order"
```

- [ ] **Step 2: Run to verify failure** — all except `test_legitimate_type_correction_still_succeeds` must FAIL on current code.
- [ ] **Step 3: Implement**

Query port (`relationship_repository.py`):

```python
    async def count_bio_parents(
        self, child_id: uuid.UUID, clan_id: uuid.UUID,
        exclude_link_id: uuid.UUID | None = None,
    ) -> int:
        result = await self._session.execute(
            text("""
                SELECT COUNT(*) FROM public.parent_child
                WHERE child_id = :child_id
                  AND created_by_clan_id = :clan_id
                  AND relationship_type = 'biological'
                  AND is_deleted = false
                  AND (:exclude_id::uuid IS NULL OR id != :exclude_id)
            """),
            {"child_id": child_id, "clan_id": clan_id, "exclude_id": exclude_link_id},
        )
        return int(result.scalar() or 0)
```

`has_active_marriage` gains the same `AND (:exclude_id::uuid IS NULL OR id != :exclude_id)` clause + param. New method:

```python
    async def has_spouse_order_conflict(
        self, person1_id: uuid.UUID, spouse_order: int, clan_id: uuid.UUID,
        exclude_marriage_id: uuid.UUID | None = None,
    ) -> bool:
        result = await self._session.execute(
            text("""
                SELECT 1 FROM public.marriages
                WHERE person1_id = :p1 AND spouse_order = :so
                  AND created_by_clan_id = :clan_id
                  AND status = 'married' AND is_deleted = false
                  AND (:exclude_id::uuid IS NULL OR id != :exclude_id)
                LIMIT 1
            """),
            {"p1": person1_id, "so": spouse_order, "clan_id": clan_id,
             "exclude_id": exclude_marriage_id},
        )
        return result.first() is not None
```

Validator (`validator.py`): extend the Protocol signatures to match; `validate_parent_child` gains `*, exclude_link_id=None, check_cycle=True` (thread `exclude_link_id` into `count_bio_parents`; wrap the `is_ancestor` block in `if check_cycle:`). `check_duplicate_marriage` gains `*, exclude_marriage_id=None`. New:

```python
    async def check_spouse_order(
        self, person1_id: uuid.UUID, spouse_order: int | None, clan_id: uuid.UUID,
        *, exclude_marriage_id: uuid.UUID | None = None,
    ) -> None:
        """Active marriages of person1 must have distinct spouse_order (vợ cả/hai/ba)."""
        if spouse_order is None:
            return
        if await self._q.has_spouse_order_conflict(
            person1_id, spouse_order, clan_id, exclude_marriage_id
        ):
            raise ConflictError("relationship.duplicate_spouse_order")
```

Handlers (`handlers.py`):
- `MarriageCommandHandler.create`: after `check_duplicate_marriage`, add `if cmd.status == "married": await self._validator.check_spouse_order(cmd.person1_id, cmd.spouse_order, cmd.clan_id)`.
- `MarriageCommandHandler.update`: BEFORE `marriage.update(...)` compute effective values and re-validate:

```python
        new_status = cmd.changes.get("status", marriage.status)
        new_order = cmd.changes.get("spouse_order", marriage.spouse_order)
        if "status" in cmd.changes and new_status == "married" and marriage.status != "married":
            await self._validator.check_duplicate_marriage(
                marriage.person1_id, marriage.person2_id, cmd.clan_id,
                exclude_marriage_id=marriage.id,
            )
        if new_status == "married" and ("spouse_order" in cmd.changes or "status" in cmd.changes):
            await self._validator.check_spouse_order(
                marriage.person1_id, new_order, cmd.clan_id,
                exclude_marriage_id=marriage.id,
            )
```

- `ParentChildCommandHandler.update`: BEFORE `link.update(...)`:

```python
        new_type = cmd.changes.get("relationship_type", link.relationship_type)
        if new_type != link.relationship_type:
            # Same rules as create; exclude this edge from the bio count; cycle
            # check skipped — parent/child ids are immutable on update.
            await self._validator.validate_parent_child(
                link.parent_id, link.child_id, new_type, cmd.clan_id,
                exclude_link_id=link.id, check_cycle=False,
            )
```

i18n ×4: `"error.relationship.duplicate_spouse_order"` — vi: `"Thứ tự hôn nhân này đã tồn tại cho người này."`; en: `"This spouse order already exists for this person."`; fr/zh equivalents. The unique index remains the race backstop (23505 → 409 via the existing IntegrityError handler).

- [ ] **Step 4: Run tests + full suite.**
- [ ] **Step 5: Full gate, commit**

```bash
git add backend/app backend/tests
git commit -m "fix(backend): re-validate relationship updates + spouse_order uniqueness (H2, M3)"
```

---

### Task 6: Unbounded cycle detection (M1)

**Files:**
- Modify: `backend/app/infrastructure/persistence/relationship_repository.py:249-257` (`is_ancestor`)
- Test: `backend/tests/integration/test_cycle_detection_depth.py`

**Interfaces:**
- Consumes/Produces: `is_ancestor(descendant_id, ancestor_id, clan_id) -> bool` — same signature, no depth cap.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/integration/test_cycle_detection_depth.py
"""M1: cycle detection must work beyond 20 generations."""
import pytest

pytestmark = pytest.mark.integration


async def test_cycle_across_25_generations_is_blocked(client, editor_headers, chain_25_generations):
    """chain_25_generations: persons g[0] (thủy tổ) .. g[24], parent edges g[i]->g[i+1].
    Adding 'g[24] is parent of g[0]' closes a 25-generation loop and must be rejected."""
    top_id, bottom_id = chain_25_generations
    resp = await client.post(
        "/api/v1/relationships/parent-child",
        json={"parent_id": bottom_id, "child_id": top_id, "relationship_type": "adopted"},
        headers=editor_headers,
    )
    assert resp.status_code in (400, 422)
    assert resp.json()["error"]["code"] == "relationship.creates_cycle"


async def test_normal_deep_edge_still_allowed(client, editor_headers, chain_25_generations_with_extra_person):
    """A legitimate edge at depth 25 (new person as child of g[24]) still validates."""
    bottom_id, new_person_id = chain_25_generations_with_extra_person
    resp = await client.post(
        "/api/v1/relationships/parent-child",
        json={"parent_id": bottom_id, "child_id": new_person_id, "relationship_type": "biological"},
        headers=editor_headers,
    )
    assert resp.status_code == 201
```

Build `chain_25_generations` by looping 25 raw-SQL person+membership inserts + 24 parent_child edges (birth dates 25 years apart so the ≥12y rule passes; use `relationship_type='adopted'` on the cycle attempt so the age rule can't mask the cycle error).

- [ ] **Step 2: Run to verify failure** — the 25-gen cycle test FAILS on current code (edge accepted, 201).
- [ ] **Step 3: Implement** — replace `is_ancestor`:

```python
    async def is_ancestor(
        self, descendant_id: uuid.UUID, ancestor_id: uuid.UUID, clan_id: uuid.UUID
    ) -> bool:
        """Unbounded ancestor walk for cycle detection (M1).

        Deliberately NOT get_ancestors_flat: that is a display function with a
        depth cap. Cycle detection must see the whole chain — deep gia phả
        (>20 đời) previously slipped through. The path-array guard terminates
        traversal even on already-corrupt (cyclic) data.
        """
        result = await self._session.execute(
            text("""
                WITH RECURSIVE ancestors AS (
                    SELECT pc.parent_id AS person_id,
                           ARRAY[pc.child_id, pc.parent_id] AS path
                    FROM public.parent_child pc
                    WHERE pc.child_id = :descendant_id
                      AND pc.created_by_clan_id = :clan_id
                      AND pc.is_deleted = false
                    UNION ALL
                    SELECT pc.parent_id, a.path || pc.parent_id
                    FROM public.parent_child pc
                    JOIN ancestors a ON pc.child_id = a.person_id
                    WHERE pc.created_by_clan_id = :clan_id
                      AND pc.is_deleted = false
                      AND NOT pc.parent_id = ANY(a.path)
                )
                SELECT 1 FROM ancestors WHERE person_id = :ancestor_id LIMIT 1
            """),
            {"descendant_id": descendant_id, "ancestor_id": ancestor_id, "clan_id": clan_id},
        )
        return result.first() is not None
```

- [ ] **Step 4: Run tests + full suite.**
- [ ] **Step 5: Full gate, commit**

```bash
git add backend/app/infrastructure/persistence/relationship_repository.py backend/tests/integration/test_cycle_detection_depth.py
git commit -m "fix(backend): unbounded cycle detection — deep gia phả beyond 20 đời (M1)"
```

---

### Task 7: Docs, contracts, ADR-017

**Files:**
- Create: `docs/decisions/017-optimistic-concurrency.md`
- Modify: `docs/decisions/README.md` (add row 017)
- Modify: `docs/contracts/error-codes.md` (3 new codes), `docs/contracts/rest-persons-api.md`, `docs/contracts/rest-relationships-api.md` (version field + required `expected_version` + 409 `stale_write`), `docs/contracts/rest-clans-api.md` (last-admin 403s), `docs/architecture/data-model.md` (version cols + uq_marriages_spouse_order), `docs/contracts/frontend-integration-guide.md` (stale_write reload UX one-liner)
- Test: none (docs) — but run the full gate once more.

**Interfaces:** Consumes the shipped behavior of Tasks 1–6 (document exactly what landed, verify claims against the code).

- [ ] **Step 1: Write ADR-017** — house style of ADR-010..016: Status (Accepted 2026-07-12, shipped), Context (H1 silent lost updates + full-column apply_to_orm), Decision (required expected_version on 3 genealogy tables; conditional UPDATE `WHERE version=`; 409 `stale_write` + current_version; delete/restore also bump; events/documents deferred), Consequences (every PATCH needs a prior GET; clients implement reload-on-409; races impossible at DB level).
- [ ] **Step 2: Update the contract docs** listed above; error-codes.md rows: `stale_write | 409`, `clan.last_admin_cannot_remove | 403`, `relationship.duplicate_spouse_order | 409` with detail shapes and client handling.
- [ ] **Step 3: Full gate one final time** — `uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports` → all green.
- [ ] **Step 4: Commit**

```bash
git add docs
git commit -m "docs: ADR-017 optimistic concurrency + data-integrity contract updates"
```
