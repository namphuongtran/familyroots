# Tree Focus Data API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a consolidated `GET /api/v1/tree/focus/{person_id}` read model that serves the v4 interactive focus-tree in one round-trip: ancestor breadcrumb + focus + N-generation descendant window, annotated with computed đời, chi/branch, đa thê spouse order, dâu/rể role, sibling order, and a has-more-descendants drill flag.

**Architecture:** A thin read-model composition over the existing hardened clan-scoped SQL functions (`get_ancestors_flat`, `get_family_tree_flat`) plus a Python enrichment pass. No new/altered SQL function (no `RETURNS TABLE` migration). Existing `/tree`, `/tree/subtree`, `/tree/path` are untouched except a dedup fix to the shared `get_ancestors`. Layering follows the existing tree stack: route → `TreeQueryHandler` → `TreeRepository` port → SQLAlchemy repo + `tree_builder` service.

**Tech Stack:** FastAPI, SQLAlchemy 2 async (psycopg), PostgreSQL, Pydantic v2, pytest-asyncio (real-DB integration via `migrated_db_url`), uv/uvx toolchain.

## Global Constraints

- **đời (generation) rule:** thủy tổ (`is_founder = true`) = **đời 1**; a person's đời = (shortest `parent_child` distance from the founder) + 1; not reachable from a founder → **null** (never guessed).
- **No new/altered SQL function; no migration.** Reuse `public.get_ancestors_flat` and `public.get_family_tree_flat` (migration 005).
- **Additive only:** `branch_id`, `branch_name`, `branch_order`, `has_more_descendants` appear only on `/tree/focus` nodes; do **not** retro-add them to `/tree` or `/tree/subtree`, and do not change those endpoints' `generation` semantics.
- **Clan isolation (Never Do #1):** every read is clan-scoped — persons via `clan_memberships.clan_id`, edges via `created_by_clan_id`; a person/edge owned by another clan is never surfaced. Cross-clan focus → 404.
- **Hexagonal boundaries:** domain port stays framework-agnostic; SQL lives in infrastructure/`app/services/tree_builder.py`; the handler orchestrates only. No FastAPI/SQLAlchemy in `app/domain`.
- **Default focus window:** `descendants=2` (con + cháu → 3-đời window), bounds `ge=1, le=6`; `ancestors=50` (full chain), bounds `ge=0, le=50`.
- **Response envelope:** `{"data": ...}` (unchanged project convention).
- **Quality gate (full, every task):** `uv run pytest`, `uvx ruff check .`, `uvx ruff format --check .`, `uvx mypy app/ tests/`, and import-linter must all pass before commit.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `app/domain/tree/repository.py` | `TreeRepository` port | Add `get_ancestors_flat`, `build_focus_view` methods |
| `app/infrastructure/persistence/tree_repository.py` | SQLAlchemy repo | Add `get_ancestors_flat`; **fix** `get_ancestors` to use it; add `build_focus_view` delegation |
| `app/services/tree_builder.py` | Tree assembly service | Add `build_focus_view` + 3 batched enrichment helpers |
| `app/application/tree/queries.py` | Query DTOs | Add `GetFocusView` |
| `app/application/tree/handlers.py` | `TreeQueryHandler` | Add `get_focus_view` (anchor arithmetic + breadcrumb + orchestration) |
| `app/schemas/tree.py` | Pydantic DTOs | Add `FocusTreeNode`, `FocusAncestor`, `FocusView` |
| `app/api/v1/tree.py` | Route | Add `GET /focus/{person_id}` |
| `docs/contracts/tree-focus.md` | Contract doc | New; linked from `docs/contracts/README.md` |
| `tests/integration/test_tree_focus.py` | Real-DB tests (Tasks 1–3) | New |
| `tests/unit/api/test_tree_focus_endpoint.py` | Route-level test (Task 4) | New |

---

## Task 1: Fix `get_ancestors` dedup + add `get_ancestors_flat` repo method

**Files:**
- Modify: `backend/app/domain/tree/repository.py`
- Modify: `backend/app/infrastructure/persistence/tree_repository.py:45-90`
- Test: `backend/tests/integration/test_tree_focus.py` (new)

**Interfaces:**
- Consumes: existing SQL function `public.get_ancestors_flat(p_person_id UUID, p_clan_id UUID, p_max_generations INT)` returning `(person_id, full_name, gender, birth_date, death_date, generation, avatar_url, child_id, depth, path)`.
- Produces:
  - `SqlAlchemyTreeRepository.get_ancestors_flat(person_id, clan_id, max_generations) -> list[dict[str, Any]]` — rows ordered `depth ASC` (self at depth 0), each: `{"id": str, "full_name": str, "gender": str, "birth_date": str|None, "death_date": str|None, "avatar_url": str|None, "generation": int|None, "child_id": str|None, "depth": int}`.
  - `get_ancestors(person_id, clan_id) -> list[dict]` output shape unchanged: `{"id","full_name","gender","birth_date","death_date","avatar_url","generation","depth"}` (no `child_id`).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/integration/test_tree_focus.py`:

```python
"""Real-DB tests for the tree focus data API (get_ancestors dedup, enrichment, handler)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.infrastructure.persistence.tree_repository import SqlAlchemyTreeRepository

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
        sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :s)"),
        {"id": cid, "s": f"c{cid.hex[:8]}"},
    )
    return cid


async def _person(
    s: AsyncSession, clan_id: uuid.UUID, creator: uuid.UUID, name: str = "P"
) -> uuid.UUID:
    pid = uuid.uuid4()
    await s.execute(
        sa.text(
            "INSERT INTO persons (id, full_name, gender, created_by_clan_id, created_by) "
            "VALUES (:id, :n, 'male', :c, :cb)"
        ),
        {"id": pid, "n": name, "c": clan_id, "cb": creator},
    )
    return pid


async def _member(
    s: AsyncSession,
    person_id: uuid.UUID,
    clan_id: uuid.UUID,
    *,
    is_founder: bool = False,
    branch_id: uuid.UUID | None = None,
) -> None:
    await s.execute(
        sa.text(
            "INSERT INTO clan_memberships (person_id, clan_id, is_founder, branch_id) "
            "VALUES (:p, :c, :f, :b)"
        ),
        {"p": person_id, "c": clan_id, "f": is_founder, "b": branch_id},
    )


async def _pc(
    s: AsyncSession,
    parent: uuid.UUID,
    child: uuid.UUID,
    clan_id: uuid.UUID,
    creator: uuid.UUID,
    *,
    birth_order: int | None = None,
) -> None:
    await s.execute(
        sa.text(
            "INSERT INTO parent_child "
            "(id, parent_id, child_id, created_by_clan_id, relationship_type, birth_order, "
            " created_by) "
            "VALUES (:id, :p, :c, :cl, 'biological', :bo, :cb)"
        ),
        {"id": uuid.uuid4(), "p": parent, "c": child, "cl": clan_id, "bo": birth_order,
         "cb": creator},
    )


async def test_get_ancestors_no_duplicates_on_fan_out(async_session: AsyncSession) -> None:
    """A child with TWO parents must not duplicate shared grandparents in the ancestor list."""
    creator = uuid.uuid4()
    clan_id = await _clan(async_session)
    gp = await _person(async_session, clan_id, creator, "GP")      # shared grandparent
    dad = await _person(async_session, clan_id, creator, "Dad")
    mom = await _person(async_session, clan_id, creator, "Mom")
    child = await _person(async_session, clan_id, creator, "Child")
    for p in (gp, dad, mom, child):
        await _member(async_session, p, clan_id)
    # gp is the parent of BOTH dad and mom → fan-out at the grandparent level.
    await _pc(async_session, gp, dad, clan_id, creator)
    await _pc(async_session, gp, mom, clan_id, creator)
    await _pc(async_session, dad, child, clan_id, creator)
    await _pc(async_session, mom, child, clan_id, creator)
    await async_session.commit()

    ancestors = await SqlAlchemyTreeRepository(async_session).get_ancestors(child, clan_id)

    ids = [a["id"] for a in ancestors]
    assert len(ids) == len(set(ids)), ids  # the old inline SQL fanned gp out twice
    assert str(gp) in ids and str(child) in ids
    # shape preserved: no child_id key leaked into the public /tree/ancestors output
    assert "child_id" not in ancestors[0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/integration/test_tree_focus.py::test_get_ancestors_no_duplicates_on_fan_out -xvs`
Expected: FAIL — the current inline recursive SQL joins `parent_child` in both terms and duplicates the shared grandparent (assertion `len(ids) == len(set(ids))` fails).

- [ ] **Step 3: Replace `get_ancestors` and add `get_ancestors_flat`**

In `backend/app/infrastructure/persistence/tree_repository.py`, replace the entire `get_ancestors` method (lines 45-90) with:

```python
    async def get_ancestors_flat(
        self, person_id: uuid.UUID, clan_id: uuid.UUID, max_generations: int = 50
    ) -> list[dict[str, Any]]:
        """Ancestor chain via the cycle-guarded, clan-scoped SQL function (no fan-out dup).

        Rows are ordered by depth ASC (the person itself is depth 0). Includes ``child_id``
        and raw ``generation`` for callers that need them (the focus handler)."""
        result = await self._session.execute(
            text(
                "SELECT person_id, full_name, gender, birth_date, death_date, "
                "       generation, avatar_url, child_id, depth "
                "FROM public.get_ancestors_flat(:person_id, :clan_id, :max_generations) "
                "ORDER BY depth ASC"
            ),
            {"person_id": person_id, "clan_id": clan_id, "max_generations": max_generations},
        )
        return [
            {
                "id": str(row["person_id"]),
                "full_name": row["full_name"],
                "gender": row["gender"],
                "birth_date": row["birth_date"].isoformat() if row["birth_date"] else None,
                "death_date": row["death_date"].isoformat() if row["death_date"] else None,
                "avatar_url": row["avatar_url"],
                "generation": row["generation"],
                "child_id": str(row["child_id"]) if row["child_id"] else None,
                "depth": row["depth"],
            }
            for row in result.mappings().all()
        ]

    async def get_ancestors(self, person_id: uuid.UUID, clan_id: uuid.UUID) -> list[dict[str, Any]]:
        """Public ancestor list for /tree/ancestors. Delegates to the deduplicated flat
        walk and drops the internal ``child_id`` so the endpoint contract is unchanged."""
        rows = await self.get_ancestors_flat(person_id, clan_id)
        return [{k: v for k, v in row.items() if k != "child_id"} for row in rows]
```

- [ ] **Step 4: Add the port methods**

In `backend/app/domain/tree/repository.py`, inside the `TreeRepository` Protocol (after `get_ancestors`), add:

```python
    async def get_ancestors_flat(
        self, person_id: uuid.UUID, clan_id: uuid.UUID, max_generations: int = 50
    ) -> list[dict[str, Any]]:
        """Deduplicated ancestor chain (depth ASC, self at 0) incl. child_id + raw generation."""
        ...
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/integration/test_tree_focus.py::test_get_ancestors_no_duplicates_on_fan_out -xvs`
Expected: PASS.

- [ ] **Step 6: Run the full gate**

Run: `cd backend && uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uvx mypy app/ tests/`
Expected: all green (existing `/tree/ancestors` behavior preserved — the shape is unchanged).

- [ ] **Step 7: Commit**

```bash
git add app/domain/tree/repository.py app/infrastructure/persistence/tree_repository.py tests/integration/test_tree_focus.py
git commit -m "fix(backend): get_ancestors dedup via get_ancestors_flat + add flat repo method (tree-focus)"
```

---

## Task 2: `build_focus_view` enrichment service (đời stamping, branch, birth_order sort, has_more)

**Files:**
- Modify: `backend/app/services/tree_builder.py`
- Test: `backend/tests/integration/test_tree_focus.py` (append)

**Interfaces:**
- Consumes: existing `build_descendants_tree(db, root_id, clan_id, max_generations) -> dict` (nested node dict with keys incl. `id: str`, `depth: int`, `children: list`, `birth_date: str|None`, `full_name: str`, `generation`).
- Produces: `build_focus_view(db, focus_id, clan_id, descendant_depth, base_generation) -> dict` — the focus subtree dict where every node additionally carries `generation` (= `base_generation + depth`, or `None` when `base_generation is None`), `branch_id: str|None`, `branch_name: str|None`, `branch_order: int|None`, `has_more_descendants: bool`, and each node's `children` re-sorted by `(birth_order NULLS last, birth_date, full_name)`. Returns `{}` if the focus person yields no rows.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/integration/test_tree_focus.py`:

```python
async def _marriage(
    s: AsyncSession, p1: uuid.UUID, p2: uuid.UUID, clan_id: uuid.UUID, creator: uuid.UUID,
    *, spouse_order: int,
) -> None:
    await s.execute(
        sa.text(
            "INSERT INTO marriages "
            "(id, person1_id, person2_id, created_by_clan_id, status, spouse_order, created_by) "
            "VALUES (:id, :p1, :p2, :c, 'married', :so, :cb)"
        ),
        {"id": uuid.uuid4(), "p1": p1, "p2": p2, "c": clan_id, "so": spouse_order, "cb": creator},
    )


async def _branch(s: AsyncSession, clan_id: uuid.UUID, name: str, order: int) -> uuid.UUID:
    bid = uuid.uuid4()
    await s.execute(
        sa.text("INSERT INTO branches (id, clan_id, name, branch_order) VALUES (:id,:c,:n,:o)"),
        {"id": bid, "c": clan_id, "n": name, "o": order},
    )
    return bid


async def test_build_focus_view_enriches_generation_branch_sort_hasmore(
    async_session: AsyncSession,
) -> None:
    from app.services.tree_builder import build_focus_view

    creator = uuid.uuid4()
    clan_id = await _clan(async_session)
    chi1 = await _branch(async_session, clan_id, "Chi Nhất", 1)
    chi2 = await _branch(async_session, clan_id, "Chi Hai", 2)

    root = await _person(async_session, clan_id, creator, "Root")       # focus, đời anchor = 3
    son_b = await _person(async_session, clan_id, creator, "Bình")      # birth_order 2
    son_a = await _person(async_session, clan_id, creator, "An")        # birth_order 1
    grand = await _person(async_session, clan_id, creator, "Cháu")      # under An
    ggrand = await _person(async_session, clan_id, creator, "Chắt")     # under Cháu (cut off)
    for p in (root, grand, ggrand):
        await _member(async_session, p, clan_id)
    await _member(async_session, son_a, clan_id, branch_id=chi1)
    await _member(async_session, son_b, clan_id, branch_id=chi2)
    await _pc(async_session, root, son_b, clan_id, creator, birth_order=2)
    await _pc(async_session, root, son_a, clan_id, creator, birth_order=1)
    await _pc(async_session, son_a, grand, clan_id, creator)
    await _pc(async_session, grand, ggrand, clan_id, creator)  # depth 2 → cut when descendants=2
    await async_session.commit()

    tree = await build_focus_view(
        async_session, root, clan_id, descendant_depth=2, base_generation=3
    )

    assert tree["generation"] == 3                       # focus stamped with base
    # children sorted by birth_order → An (1) before Bình (2), not alphabetical/birth_date
    assert [c["full_name"] for c in tree["children"]] == ["An", "Bình"]
    an = tree["children"][0]
    assert an["generation"] == 4                          # base + depth 1
    assert an["branch_name"] == "Chi Nhất" and an["branch_order"] == 1
    chau = an["children"][0]
    assert chau["generation"] == 5 and chau["depth"] == 2
    assert chau["has_more_descendants"] is True           # Chắt exists below the cutoff
    assert tree["children"][1]["has_more_descendants"] is False  # Bình is childless


async def test_build_focus_view_null_base_generation(async_session: AsyncSession) -> None:
    from app.services.tree_builder import build_focus_view

    creator = uuid.uuid4()
    clan_id = await _clan(async_session)
    root = await _person(async_session, clan_id, creator, "Root")
    await _member(async_session, root, clan_id)
    await async_session.commit()

    tree = await build_focus_view(async_session, root, clan_id, 2, None)
    assert tree["generation"] is None                     # unknown đời stays null
    assert tree["has_more_descendants"] is False
    assert tree["children"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/integration/test_tree_focus.py -k build_focus_view -xvs`
Expected: FAIL with `ImportError: cannot import name 'build_focus_view'`.

- [ ] **Step 3: Implement `build_focus_view` + helpers**

In `backend/app/services/tree_builder.py`, add at the end of the file:

```python
_BIRTH_ORDER_LAST = 32767  # SmallInteger max — NULL birth_order sorts after all set values


async def _branch_map(
    db: AsyncSession, person_ids: list[uuid.UUID], clan_id: uuid.UUID
) -> dict[uuid.UUID, dict[str, Any]]:
    """Chi/branch per member (clan-scoped). Members with no branch are simply absent."""
    if not person_ids:
        return {}
    result = await db.execute(
        text(
            "SELECT cm.person_id, b.id AS branch_id, b.name, b.branch_order "
            "FROM public.clan_memberships cm "
            "JOIN public.branches b ON b.id = cm.branch_id "
            "WHERE cm.person_id = ANY(:ids) AND cm.clan_id = :clan_id"
        ),
        {"ids": person_ids, "clan_id": clan_id},
    )
    return {
        row["person_id"]: {
            "id": str(row["branch_id"]),
            "name": row["name"],
            "order": row["branch_order"],
        }
        for row in result.mappings().all()
    }


async def _birth_order_map(
    db: AsyncSession, person_ids: list[uuid.UUID], clan_id: uuid.UUID
) -> dict[uuid.UUID, int]:
    """Smallest set birth_order per child among this clan's blood edges (NULLs ignored)."""
    if not person_ids:
        return {}
    result = await db.execute(
        text(
            "SELECT pc.child_id, MIN(pc.birth_order) AS birth_order "
            "FROM public.parent_child pc "
            "WHERE pc.child_id = ANY(:ids) AND pc.created_by_clan_id = :clan_id "
            "  AND pc.is_deleted = false AND pc.birth_order IS NOT NULL "
            "GROUP BY pc.child_id"
        ),
        {"ids": person_ids, "clan_id": clan_id},
    )
    return {row["child_id"]: row["birth_order"] for row in result.mappings().all()}


async def _persons_with_children(
    db: AsyncSession, person_ids: list[uuid.UUID], clan_id: uuid.UUID
) -> set[uuid.UUID]:
    """Subset of ``person_ids`` that have at least one non-deleted child via a clan-owned edge."""
    if not person_ids:
        return set()
    result = await db.execute(
        text(
            "SELECT DISTINCT pc.parent_id "
            "FROM public.parent_child pc "
            "JOIN public.persons ch ON ch.id = pc.child_id AND ch.is_deleted = false "
            "WHERE pc.parent_id = ANY(:ids) AND pc.created_by_clan_id = :clan_id "
            "  AND pc.is_deleted = false"
        ),
        {"ids": person_ids, "clan_id": clan_id},
    )
    return {row["parent_id"] for row in result.mappings().all()}


async def build_focus_view(
    db: AsyncSession,
    focus_id: uuid.UUID,
    clan_id: uuid.UUID,
    descendant_depth: int,
    base_generation: int | None,
) -> dict[str, Any]:
    """Focus subtree (focus + ``descendant_depth`` generations below), enriched with computed
    đời, chi/branch, birth_order sibling order, and a has-more-descendants drill flag."""
    subtree = await build_descendants_tree(db, focus_id, clan_id, descendant_depth)
    if not subtree:
        return {}

    node_ids: list[uuid.UUID] = []
    boundary_ids: list[uuid.UUID] = []

    def collect(node: dict[str, Any]) -> None:
        pid = uuid.UUID(node["id"])
        node_ids.append(pid)
        node["generation"] = (
            base_generation + node["depth"] if base_generation is not None else None
        )
        if node["depth"] == descendant_depth:
            boundary_ids.append(pid)
        for child in node["children"]:
            collect(child)

    collect(subtree)

    branches = await _branch_map(db, node_ids, clan_id)
    birth_orders = await _birth_order_map(db, node_ids, clan_id)
    have_children = await _persons_with_children(db, boundary_ids, clan_id)

    def enrich(node: dict[str, Any]) -> None:
        pid = uuid.UUID(node["id"])
        branch = branches.get(pid)
        node["branch_id"] = branch["id"] if branch else None
        node["branch_name"] = branch["name"] if branch else None
        node["branch_order"] = branch["order"] if branch else None
        node["has_more_descendants"] = pid in have_children
        node["children"].sort(
            key=lambda c: (
                birth_orders.get(uuid.UUID(c["id"]), _BIRTH_ORDER_LAST),
                c["birth_date"] or "9999",
                c["full_name"],
            )
        )
        for child in node["children"]:
            enrich(child)

    enrich(subtree)
    return subtree
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/integration/test_tree_focus.py -k build_focus_view -xvs`
Expected: PASS (both `test_build_focus_view_enriches_...` and `test_build_focus_view_null_base_generation`).

- [ ] **Step 5: Run the full gate**

Run: `cd backend && uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uvx mypy app/ tests/`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add app/services/tree_builder.py tests/integration/test_tree_focus.py
git commit -m "feat(backend): build_focus_view enrichment — đời/branch/birth_order/has_more (tree-focus)"
```

---

## Task 3: `GetFocusView` DTO + repo delegation + `TreeQueryHandler.get_focus_view`

**Files:**
- Modify: `backend/app/application/tree/queries.py`
- Modify: `backend/app/application/tree/handlers.py`
- Modify: `backend/app/domain/tree/repository.py`
- Modify: `backend/app/infrastructure/persistence/tree_repository.py`
- Test: `backend/tests/integration/test_tree_focus.py` (append)

**Interfaces:**
- Consumes: `get_ancestors_flat` (Task 1), `build_focus_view` service (Task 2), existing `person_in_clan`, `find_clan_founder`.
- Produces:
  - `GetFocusView(person_id: uuid.UUID, clan_id: uuid.UUID, ancestor_depth: int = 50, descendant_depth: int = 2)` (frozen dataclass).
  - `SqlAlchemyTreeRepository.build_focus_view(focus_id, clan_id, descendant_depth, base_generation) -> dict[str, Any]` (delegates to the service).
  - `TreeQueryHandler.get_focus_view(query: GetFocusView) -> dict[str, Any]` returning `{"focus_person_id": str, "generation_of_focus": int|None, "ancestors": list[dict], "focus_subtree": dict}`. Each breadcrumb ancestor: `{"id","full_name","gender","birth_date","death_date","avatar_url","generation": int|None,"is_founder": bool}`, ordered thủy-tổ-first (depth DESC), excluding the focus person. Raises `EntityNotFoundError("person_not_found")` (→ 404) when the focus person is not a clan member.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/integration/test_tree_focus.py`:

```python
async def _handler(session: AsyncSession):
    from app.application.tree.handlers import TreeQueryHandler
    return TreeQueryHandler(SqlAlchemyTreeRepository(session))


async def test_focus_view_at_founder(async_session: AsyncSession) -> None:
    from app.application.tree.queries import GetFocusView
    from app.domain.shared.exceptions import EntityNotFoundError

    creator = uuid.uuid4()
    clan_id = await _clan(async_session)
    to = await _person(async_session, clan_id, creator, "Thủy Tổ")
    son = await _person(async_session, clan_id, creator, "Con")
    grand = await _person(async_session, clan_id, creator, "Cháu")
    await _member(async_session, to, clan_id, is_founder=True)
    await _member(async_session, son, clan_id)
    await _member(async_session, grand, clan_id)
    await _pc(async_session, to, son, clan_id, creator)
    await _pc(async_session, son, grand, clan_id, creator)
    await async_session.commit()

    handler = await _handler(async_session)
    view = await handler.get_focus_view(
        GetFocusView(person_id=to, clan_id=clan_id, descendant_depth=2)
    )

    assert view["focus_person_id"] == str(to)
    assert view["generation_of_focus"] == 1
    assert view["ancestors"] == []                              # founder has no breadcrumb
    assert view["focus_subtree"]["generation"] == 1
    assert view["focus_subtree"]["children"][0]["generation"] == 2

    # focus at the grandchild → breadcrumb thủy-tổ-first with correct đời
    view2 = await handler.get_focus_view(GetFocusView(person_id=grand, clan_id=clan_id))
    assert view2["generation_of_focus"] == 3
    crumbs = view2["ancestors"]
    assert [c["full_name"] for c in crumbs] == ["Thủy Tổ", "Con"]
    assert [c["generation"] for c in crumbs] == [1, 2]
    assert crumbs[0]["is_founder"] is True and crumbs[1]["is_founder"] is False

    with pytest.raises(EntityNotFoundError):
        await handler.get_focus_view(GetFocusView(person_id=uuid.uuid4(), clan_id=clan_id))


async def test_focus_view_no_founder_null_generation(async_session: AsyncSession) -> None:
    from app.application.tree.queries import GetFocusView

    creator = uuid.uuid4()
    clan_id = await _clan(async_session)
    a = await _person(async_session, clan_id, creator, "A")
    b = await _person(async_session, clan_id, creator, "B")
    await _member(async_session, a, clan_id)   # no is_founder anywhere
    await _member(async_session, b, clan_id)
    await _pc(async_session, a, b, clan_id, creator)
    await async_session.commit()

    handler = await _handler(async_session)
    view = await handler.get_focus_view(GetFocusView(person_id=b, clan_id=clan_id))
    assert view["generation_of_focus"] is None
    assert view["focus_subtree"]["generation"] is None
    assert all(c["generation"] is None for c in view["ancestors"])  # view still returned


async def test_focus_view_clan_isolation(async_session: AsyncSession) -> None:
    """A person of clan A must be invisible through clan B (404), both directions."""
    from app.application.tree.queries import GetFocusView
    from app.domain.shared.exceptions import EntityNotFoundError

    creator = uuid.uuid4()
    clan_a = await _clan(async_session)
    clan_b = await _clan(async_session)
    pa = await _person(async_session, clan_a, creator, "A-only")
    await _member(async_session, pa, clan_a)
    await async_session.commit()

    handler = await _handler(async_session)
    with pytest.raises(EntityNotFoundError):
        await handler.get_focus_view(GetFocusView(person_id=pa, clan_id=clan_b))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/integration/test_tree_focus.py -k focus_view -xvs`
Expected: FAIL — `GetFocusView` does not exist / `TreeQueryHandler` has no `get_focus_view`.

- [ ] **Step 3: Add the `GetFocusView` query DTO**

In `backend/app/application/tree/queries.py`, append:

```python
@dataclass(frozen=True)
class GetFocusView:
    person_id: uuid.UUID
    clan_id: uuid.UUID
    ancestor_depth: int = 50
    descendant_depth: int = 2
```

- [ ] **Step 4: Add repo delegation + port method**

In `backend/app/infrastructure/persistence/tree_repository.py`, add this method to `SqlAlchemyTreeRepository` (import the service function at the top: change `from app.services.tree_builder import build_descendants_tree, find_clan_founder` to also import `build_focus_view`):

```python
    async def build_focus_view(
        self,
        focus_id: uuid.UUID,
        clan_id: uuid.UUID,
        descendant_depth: int,
        base_generation: int | None,
    ) -> dict[str, Any]:
        return await build_focus_view(
            self._session, focus_id, clan_id, descendant_depth, base_generation
        )
```

In `backend/app/domain/tree/repository.py`, add to the Protocol:

```python
    async def build_focus_view(
        self,
        focus_id: uuid.UUID,
        clan_id: uuid.UUID,
        descendant_depth: int,
        base_generation: int | None,
    ) -> dict[str, Any]:
        """Enriched focus subtree (computed đời, branch, birth_order sort, has_more)."""
        ...
```

- [ ] **Step 5: Implement `get_focus_view` on the handler**

In `backend/app/application/tree/handlers.py`, update the import line to include `GetFocusView`:

```python
from app.application.tree.queries import FindPath, GetAncestors, GetFocusView, GetFullTree, GetSubtree
```

Then add this method to `TreeQueryHandler` (after `get_ancestors`):

```python
    async def get_focus_view(self, query: GetFocusView) -> dict[str, Any]:
        """Assemble the focus view: breadcrumb ancestors + focus + descendant window,
        with đời computed from the graph (thủy tổ = đời 1)."""
        if not await self._repo.person_in_clan(query.person_id, query.clan_id):
            raise EntityNotFoundError("person_not_found")

        chain = await self._repo.get_ancestors_flat(
            query.person_id, query.clan_id, query.ancestor_depth
        )
        founder_id = await self._repo.find_clan_founder(query.clan_id)
        founder_str = str(founder_id) if founder_id is not None else None

        base_generation: int | None = None
        if founder_str is not None:
            for row in chain:
                if row["id"] == founder_str:
                    base_generation = row["depth"] + 1
                    break

        ancestors: list[dict[str, Any]] = []
        for row in sorted((r for r in chain if r["depth"] >= 1), key=lambda r: -r["depth"]):
            gen = base_generation - row["depth"] if base_generation is not None else None
            ancestors.append(
                {
                    "id": row["id"],
                    "full_name": row["full_name"],
                    "gender": row["gender"],
                    "birth_date": row["birth_date"],
                    "death_date": row["death_date"],
                    "avatar_url": row["avatar_url"],
                    "generation": gen,
                    "is_founder": row["id"] == founder_str,
                }
            )

        focus_subtree = await self._repo.build_focus_view(
            query.person_id, query.clan_id, query.descendant_depth, base_generation
        )

        return {
            "focus_person_id": str(query.person_id),
            "generation_of_focus": base_generation,
            "ancestors": ancestors,
            "focus_subtree": focus_subtree,
        }
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/integration/test_tree_focus.py -k focus_view -xvs`
Expected: PASS (founder/grandchild/404, no-founder-null, clan isolation).

- [ ] **Step 7: Run the full gate**

Run: `cd backend && uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uvx mypy app/ tests/`
Expected: all green.

- [ ] **Step 8: Commit**

```bash
git add app/application/tree/queries.py app/application/tree/handlers.py app/domain/tree/repository.py app/infrastructure/persistence/tree_repository.py tests/integration/test_tree_focus.py
git commit -m "feat(backend): TreeQueryHandler.get_focus_view — đời anchor + breadcrumb (tree-focus)"
```

---

## Task 4: `GET /tree/focus/{person_id}` route + `FocusView` schema + contract doc

**Files:**
- Modify: `backend/app/schemas/tree.py`
- Modify: `backend/app/api/v1/tree.py`
- Create: `backend/../docs/contracts/tree-focus.md` (repo path `docs/contracts/tree-focus.md`)
- Modify: `docs/contracts/README.md`
- Test: `backend/tests/unit/api/test_tree_focus_endpoint.py` (new)

**Interfaces:**
- Consumes: `TreeQueryHandler.get_focus_view` (Task 3), `GetFocusView` (Task 3), existing `get_tree_query_handler`, `get_current_user`, `get_current_clan_id`, `RequireViewer`.
- Produces: `GET /api/v1/tree/focus/{person_id}` → `{"data": FocusView}`; query params `descendants` (default 2, `ge=1 le=6`), `ancestors` (default 50, `ge=0 le=50`).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/api/test_tree_focus_endpoint.py`:

```python
"""Request-level tests for GET /api/v1/tree/focus/{person_id}."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.tree import router as tree_router
from app.application.tree.queries import GetFocusView
from app.core.database import get_db
from app.core.security import get_current_clan_id, get_current_user
from app.infrastructure.dependencies import get_tree_query_handler


class _RoleRow:
    role = "viewer"
    is_approved = True


class _RoleResult:
    def first(self) -> _RoleRow:
        return _RoleRow()


class _FakeDb:
    async def execute(self, *_a: Any, **_k: Any) -> _RoleResult:
        return _RoleResult()


class _FakeHandler:
    def __init__(self) -> None:
        self.last_query: GetFocusView | None = None

    async def get_focus_view(self, query: GetFocusView) -> dict[str, Any]:
        self.last_query = query
        return {
            "focus_person_id": str(query.person_id),
            "generation_of_focus": 1,
            "ancestors": [],
            "focus_subtree": {"id": str(query.person_id), "full_name": "P", "children": []},
        }


def _client(handler: _FakeHandler) -> TestClient:
    app = FastAPI()
    app.include_router(tree_router, prefix="/api/v1/tree")
    app.dependency_overrides[get_current_user] = lambda: {"sub": str(uuid.uuid4())}
    app.dependency_overrides[get_current_clan_id] = lambda: uuid.uuid4()
    app.dependency_overrides[get_db] = lambda: _FakeDb()
    app.dependency_overrides[get_tree_query_handler] = lambda: handler
    return TestClient(app)


def test_focus_defaults_and_envelope() -> None:
    handler = _FakeHandler()
    pid = uuid.uuid4()
    resp = _client(handler).get(f"/api/v1/tree/focus/{pid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["focus_person_id"] == str(pid)
    assert handler.last_query.descendant_depth == 2      # default window
    assert handler.last_query.ancestor_depth == 50


def test_focus_param_bounds_rejected() -> None:
    handler = _FakeHandler()
    pid = uuid.uuid4()
    client = _client(handler)
    assert client.get(f"/api/v1/tree/focus/{pid}?descendants=0").status_code == 422
    assert client.get(f"/api/v1/tree/focus/{pid}?descendants=7").status_code == 422
    assert client.get(f"/api/v1/tree/focus/{pid}?ancestors=51").status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/api/test_tree_focus_endpoint.py -xvs`
Expected: FAIL — the `/focus/{person_id}` route does not exist (404 on the request, so assertions fail).

- [ ] **Step 3: Add the `FocusView` schemas**

In `backend/app/schemas/tree.py`, append:

```python
class FocusAncestor(BaseModel):
    """One breadcrumb ancestor above the focus person (thủy-tổ-first)."""

    id: str
    full_name: str
    gender: str
    birth_date: date | None = None
    death_date: date | None = None
    avatar_url: str | None = None
    generation: int | None = None
    is_founder: bool = False


class FocusTreeNode(BaseModel):
    """A node in the focus subtree, with focus-only enrichment fields."""

    id: str
    full_name: str
    gender: str
    birth_name: str | None = None
    posthumous_name: str | None = None
    birth_date: date | None = None
    birth_date_approx: bool = False
    death_date: date | None = None
    death_date_approx: bool = False
    birth_place: str | None = None
    avatar_url: str | None = None
    membership_role: str | None = None
    is_founder: bool = False
    generation: int | None = None
    depth: int = 0
    branch_id: str | None = None
    branch_name: str | None = None
    branch_order: int | None = None
    has_more_descendants: bool = False
    spouses: list[SpouseNode] = []
    children: list[FocusTreeNode] = []

    model_config = {"from_attributes": True}


FocusTreeNode.model_rebuild()


class FocusView(BaseModel):
    """Consolidated payload for the interactive focus-tree screen."""

    focus_person_id: str
    generation_of_focus: int | None = None
    ancestors: list[FocusAncestor] = []
    focus_subtree: FocusTreeNode | None = None

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Add the route**

In `backend/app/api/v1/tree.py`, update the schema import to add the focus model:

```python
from app.schemas.tree import FocusView, TreeNodeDetail, TreeNodeSummary
```

Update the queries import to add `GetFocusView`:

```python
from app.application.tree.queries import FindPath, GetAncestors, GetFocusView, GetFullTree, GetSubtree
```

Add this route (place it before `find_path`, after `get_ancestors`):

```python
@router.get("/focus/{person_id}")
async def get_focus(
    person_id: uuid.UUID,
    descendants: int = Query(2, ge=1, le=6),
    ancestors: int = Query(50, ge=0, le=50),
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: TreeQueryHandler = Depends(get_tree_query_handler),
    _role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """Focus view: breadcrumb ancestors + focus + descendant window, with computed đời."""
    result = await handler.get_focus_view(
        GetFocusView(
            person_id=person_id,
            clan_id=clan_id,
            ancestor_depth=ancestors,
            descendant_depth=descendants,
        )
    )
    # Validate/normalize the handler output against the published contract before returning.
    return {"data": FocusView.model_validate(result).model_dump()}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/unit/api/test_tree_focus_endpoint.py -xvs`
Expected: PASS (defaults captured, envelope correct, out-of-bounds → 422).

- [ ] **Step 6: Write the contract doc**

Create `docs/contracts/tree-focus.md`:

```markdown
# Contract: GET /api/v1/tree/focus/{person_id}

Consolidated read model for the interactive focus-tree UI (web/mobile). One round-trip per refocus.

**Auth:** Bearer JWT + `X-Current-Clan-Id`; role ≥ viewer.

**Query params:**
- `descendants` (int, default 2, 1–6) — generations below the focus person.
- `ancestors` (int, default 50, 0–50) — ancestor generations for the breadcrumb.

**Response** `{"data": FocusView}`:
- `focus_person_id` (str)
- `generation_of_focus` (int|null) — đời computed from the graph; thủy tổ = 1; null if the focus is not descended from a founder.
- `ancestors` (list) — strict ancestors, thủy-tổ-first, excluding focus; each `{id, full_name, gender, birth_date, death_date, avatar_url, generation, is_founder}`.
- `focus_subtree` (node|null) — nested node; each node adds `generation` (computed), `branch_id`/`branch_name`/`branch_order` (chi), `has_more_descendants` (bool, drill affordance) to the standard person/spouse fields (`spouses[].spouse_order`, `membership_role` = blood/spouse/adopted). Children ordered by `birth_order` → `birth_date` → name.

**Errors:** focus person not in the clan (or soft-deleted / unknown) → 404 `person_not_found` (envelope). Never reveals cross-clan existence.

**Notes:** đời is derived on read from the graph; `clan_memberships.generation` is not the source here. `branch_*`/`has_more_descendants` are focus-only — the older `/tree` and `/tree/subtree` responses are unchanged.
```

Then add a link line under the endpoints/contracts list in `docs/contracts/README.md`:

```markdown
- [Tree Focus view](tree-focus.md) — `GET /tree/focus/{person_id}` (breadcrumb + focus + descendant window, computed đời)
```

- [ ] **Step 7: Run the full gate**

Run: `cd backend && uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uvx mypy app/ tests/`
Expected: all green.

- [ ] **Step 8: Commit**

```bash
git add app/schemas/tree.py app/api/v1/tree.py tests/unit/api/test_tree_focus_endpoint.py ../docs/contracts/tree-focus.md ../docs/contracts/README.md
git commit -m "feat(backend): GET /tree/focus route + FocusView schema + contract doc (tree-focus)"
```

---

## Self-Review

**1. Spec coverage:**
- Gap 1 (ancestors dedup) → Task 1. ✅
- Gap 2 (computed đời) → Task 2 (stamping) + Task 3 (anchor arithmetic). ✅
- Gap 3 (`has_more_descendants`) → Task 2. ✅
- Gap 4 (chi/branch surfacing) → Task 2. ✅
- Gap 5 (birth_order sibling sort) → Task 2. ✅
- Consolidated `/tree/focus` endpoint + params + envelope → Task 4. ✅
- Response shape (`focus_person_id`, `generation_of_focus`, `ancestors`, `focus_subtree`) → Task 3 (assembly) + Task 4 (schema/validation). ✅
- đời rule (thủy tổ = 1; null when unreachable) → Task 3 tests `test_focus_view_at_founder`, `test_focus_view_no_founder_null_generation`. ✅
- Clan isolation two-sided + 404 negatives → Task 3 `test_focus_view_clan_isolation`, 404 assertion. ✅
- No SQL-function migration → confirmed: only existing functions called. ✅
- Existing endpoints unchanged → Task 1 preserves `get_ancestors` output shape (asserted); focus-only fields never touch `/tree`/`/tree/subtree`. ✅
- Out-of-scope items (render, exact +N count, materialized đời, other PR-J items) → not in any task. ✅

**2. Placeholder scan:** No TBD/TODO/"handle edge cases"; every code step shows complete code and exact commands. ✅

**3. Type consistency:** `build_focus_view(db, focus_id, clan_id, descendant_depth, base_generation)` identical in Task 2 (service), Task 3 (repo delegation + port). `GetFocusView(person_id, clan_id, ancestor_depth=50, descendant_depth=2)` identical in Task 3 + Task 4 route. `get_ancestors_flat(person_id, clan_id, max_generations=50)` identical in Task 1 (repo + port) and consumed in Task 3. Breadcrumb dict keys match between handler assembly (Task 3) and `FocusAncestor` schema (Task 4). Node enrichment keys (`branch_id/branch_name/branch_order/has_more_descendants/generation`) match between Task 2 and `FocusTreeNode` (Task 4). ✅
```
