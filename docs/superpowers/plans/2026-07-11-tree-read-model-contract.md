# Tree Read-Model Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Freeze two frontend-facing tree contracts: `generation` (đời) is graph-computed on EVERY tree endpoint (not hand-entered `clan_memberships.generation`), and each child node carries derived `mother_id` + `mother_spouse_order` so đa thê children group under the right wife.

**Architecture:** Read-model only. Unify đời stamping in `build_descendants_tree` driven by a `base_generation` the handlers compute (founder-distance of the root); derive `mother_id` from each child's female parent edge + `mother_spouse_order` from the father's already-fetched spouses. No schema/migration change; additive Pydantic schema fields.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic v2, pytest-asyncio (real-DB).

## Global Constraints
- **đời rule:** thủy tổ = 1; `generation = base_generation + node.depth`; `null` when the root isn't descended from a founder. Applied on `/tree`, `/tree/subtree`, `/tree/focus`. `clan_memberships.generation` is no longer a display source (column kept).
- **mother_id:** the child's female parent among its `parent_child` edges (clan-scoped); `null` when no mother edge recorded. `mother_spouse_order` = the `spouse_order` of that mother's marriage to the father; `null` if unmatched.
- No schema/migration change; new schema fields are additive; behavior otherwise unchanged.
- Clan isolation preserved (all lookups clan-scoped by `created_by_clan_id` / `clan_id`).
- **Quality gate (full, every task)** from `backend/`: `uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports` (use `uv run mypy`). All pass before commit.

---

## Task 1: đời graph-computed on all tree endpoints

**Files:** `app/services/tree_builder.py`, `app/infrastructure/persistence/tree_repository.py`, `app/domain/tree/repository.py`, `app/application/tree/handlers.py`; tests `tests/integration/test_tree_focus.py` (append) + `tests/test_tree.py` if it asserts generation.

**Interfaces:**
- `build_descendants_tree(db, root_id, clan_id, max_generations, base_generation: int | None = None) -> dict` — stamps `generation = base_generation + depth` (or `None` when `base_generation is None`) instead of surfacing `cm.generation`.
- `TreeRepository.build_descendants_tree(..., base_generation: int | None = None)` (port + impl pass-through).
- `TreeQueryHandler._base_generation(root_id, clan_id) -> int | None` (shared by get_full_tree/get_subtree/get_focus_view).

- [ ] **Step 1: Write the failing test** — append to `tests/integration/test_tree_focus.py`:

```python
async def test_full_tree_generation_is_graph_computed(async_session: AsyncSession) -> None:
    """GET /tree computes đời from the graph (thủy tổ=1), ignoring a wrong hand-entered
    clan_memberships.generation."""
    from app.application.tree.handlers import TreeQueryHandler
    from app.application.tree.queries import GetFullTree

    creator = uuid.uuid4()
    clan_id = await _clan(async_session)
    to = await _person(async_session, clan_id, creator, "To")
    son = await _person(async_session, clan_id, creator, "Con")
    grand = await _person(async_session, clan_id, creator, "Chau")
    await _member(async_session, to, clan_id, is_founder=True)
    # Seed a WRONG hand-entered generation to prove it's ignored.
    await async_session.execute(
        sa.text("UPDATE clan_memberships SET generation = 99 WHERE person_id = :p"), {"p": son}
    )
    await _member(async_session, son, clan_id)
    await _member(async_session, grand, clan_id)
    await _pc(async_session, to, son, clan_id, creator)
    await _pc(async_session, son, grand, clan_id, creator)
    await async_session.commit()

    handler = TreeQueryHandler(SqlAlchemyTreeRepository(async_session))
    result = await handler.get_full_tree(GetFullTree(clan_id=clan_id))
    tree = result["tree"]
    assert tree["generation"] == 1                         # thủy tổ
    assert tree["children"][0]["generation"] == 2          # not 99
    assert tree["children"][0]["children"][0]["generation"] == 3
```

- [ ] **Step 2: Run → FAIL** — `cd backend && uv run pytest tests/integration/test_tree_focus.py -k full_tree_generation -xvs` (generation is 99 / cm-sourced).

- [ ] **Step 3: Stamp đời in `build_descendants_tree`.** In `app/services/tree_builder.py`, add the `base_generation` parameter and use it in `node_to_dict`:

```python
async def build_descendants_tree(
    db: AsyncSession,
    root_id: uuid.UUID,
    clan_id: uuid.UUID,
    max_generations: int = 10,
    base_generation: int | None = None,
) -> dict[str, Any]:
```
In `node_to_dict`, replace `"generation": node.generation,` with:
```python
            "generation": (
                base_generation + node.depth if base_generation is not None else None
            ),
```

- [ ] **Step 4: Thread `base_generation` through the repo + port.** In `app/domain/tree/repository.py` add `base_generation: int | None = None` to the `build_descendants_tree` Protocol signature; in `app/infrastructure/persistence/tree_repository.py` pass it through to the service call.

- [ ] **Step 5: Compute the anchor in the handlers.** In `app/application/tree/handlers.py` add a shared helper and use it in all three read paths:

```python
    async def _base_generation(self, root_id: uuid.UUID, clan_id: uuid.UUID) -> int | None:
        """đời of ``root_id`` (thủy tổ = 1) = founder distance + 1, or None if the root
        is not descended from a founder / the clan has no founder."""
        chain = await self._repo.get_ancestors_flat(root_id, clan_id, 50)
        founder_id = await self._repo.find_clan_founder(clan_id)
        if founder_id is None:
            return None
        founder_str = str(founder_id)
        for row in chain:
            if row["id"] == founder_str:
                return int(row["depth"]) + 1
        return None
```
- `get_full_tree`: after resolving `root_id`, `base = await self._base_generation(root_id, query.clan_id)` and pass `base_generation=base` to `build_descendants_tree`.
- `get_subtree`: same with `query.person_id`.
- `get_focus_view`: replace its inline founder-depth loop (the `base_generation` computation, lines ~92-97) with `base_generation = await self._base_generation(query.person_id, query.clan_id)` (behavior identical; keep the rest — breadcrumb dedup, the `< 1` guard, `build_focus_view(...)` call — unchanged).

- [ ] **Step 6: Unify focus stamping.** In `app/services/tree_builder.py::build_focus_view`, pass `base_generation` into its internal `build_descendants_tree(...)` call and REMOVE its own generation-stamping (the line that sets `node["generation"]` in its walk) so đời is stamped in exactly one place. Keep its branch / has_more / birth_order enrichment. Verify the focus tests still pass (generation unchanged).

- [ ] **Step 7: Run tests green** — `uv run pytest tests/integration/test_tree_focus.py -v` (new full-tree test + all existing focus tests).
- [ ] **Step 8: Full gate.**
- [ ] **Step 9: Commit** — `git add app/services/tree_builder.py app/infrastructure/persistence/tree_repository.py app/domain/tree/repository.py app/application/tree/handlers.py tests/integration/test_tree_focus.py` ; `"feat(backend): compute đời from the graph on all tree endpoints (contract-freeze)"`.

---

## Task 2: derived `mother_id` + `mother_spouse_order` on child nodes

**Files:** `app/services/tree_builder.py`, `app/schemas/tree.py`; tests `tests/integration/test_tree_focus.py` (append).

**Interfaces:**
- `build_descendants_tree` output nodes gain `mother_id: str | None` and `mother_spouse_order: int | None`.
- `TreeNode`/`TreeNodeSummary`/`TreeNodeDetail`/`FocusTreeNode` gain the two optional fields.

- [ ] **Step 1: Write the failing test** — append to `tests/integration/test_tree_focus.py` (uses `_marriage`/`_branch` helpers already in the file):

```python
async def test_child_nodes_carry_mother_attribution(async_session: AsyncSession) -> None:
    """đa thê: each child node names its mother (which wife) + her spouse_order."""
    from app.application.tree.handlers import TreeQueryHandler
    from app.application.tree.queries import GetSubtree

    creator = uuid.uuid4()
    clan_id = await _clan(async_session)
    father = await _person(async_session, clan_id, creator, "Cha")
    w1 = await _person(async_session, clan_id, creator, "Vo Ca")
    w2 = await _person(async_session, clan_id, creator, "Vo Hai")
    c1 = await _person(async_session, clan_id, creator, "Con Ba Ca")
    c2 = await _person(async_session, clan_id, creator, "Con Ba Hai")
    for p in (father, w1, w2, c1, c2):
        await _member(async_session, p, clan_id)
    await _marriage(async_session, father, w1, clan_id, creator, spouse_order=1)
    await _marriage(async_session, father, w2, clan_id, creator, spouse_order=2)
    # father→child (paternal descent) AND mother→child (attribution edge)
    await _pc(async_session, father, c1, clan_id, creator)
    await _pc(async_session, w1, c1, clan_id, creator)
    await _pc(async_session, father, c2, clan_id, creator)
    await _pc(async_session, w2, c2, clan_id, creator)
    await async_session.commit()

    handler = TreeQueryHandler(SqlAlchemyTreeRepository(async_session))
    result = await handler.get_subtree(GetSubtree(person_id=father, clan_id=clan_id))
    kids = {c["full_name"]: c for c in result["tree"]["children"]}
    assert kids["Con Ba Ca"]["mother_id"] == str(w1)
    assert kids["Con Ba Ca"]["mother_spouse_order"] == 1
    assert kids["Con Ba Hai"]["mother_id"] == str(w2)
    assert kids["Con Ba Hai"]["mother_spouse_order"] == 2


async def test_child_without_mother_edge_has_null_mother(async_session: AsyncSession) -> None:
    from app.application.tree.handlers import TreeQueryHandler
    from app.application.tree.queries import GetSubtree

    creator = uuid.uuid4()
    clan_id = await _clan(async_session)
    father = await _person(async_session, clan_id, creator, "Cha")
    child = await _person(async_session, clan_id, creator, "Con")
    await _member(async_session, father, clan_id)
    await _member(async_session, child, clan_id)
    await _pc(async_session, father, child, clan_id, creator)   # no mother edge
    await async_session.commit()

    handler = TreeQueryHandler(SqlAlchemyTreeRepository(async_session))
    result = await handler.get_subtree(GetSubtree(person_id=father, clan_id=clan_id))
    kid = result["tree"]["children"][0]
    assert kid["mother_id"] is None and kid["mother_spouse_order"] is None
```

- [ ] **Step 2: Run → FAIL** (`KeyError`/missing `mother_id`).

- [ ] **Step 3: Add the batched mother lookup** to `app/services/tree_builder.py`:

```python
async def _mother_map(
    db: AsyncSession, child_ids: list[uuid.UUID], clan_id: uuid.UUID
) -> dict[uuid.UUID, uuid.UUID]:
    """child_id → female-parent (mother) id, via this clan's parent_child edges."""
    if not child_ids:
        return {}
    result = await db.execute(
        text(
            "SELECT pc.child_id, p.id AS mother_id "
            "FROM public.parent_child pc "
            "JOIN public.persons p ON p.id = pc.parent_id "
            "  AND p.gender = 'female' AND p.is_deleted = false "
            "WHERE pc.child_id = ANY(:ids) AND pc.created_by_clan_id = :clan_id "
            "  AND pc.is_deleted = false"
        ),
        {"ids": child_ids, "clan_id": clan_id},
    )
    # One mother per child (a child has at most one female parent in practice); if data
    # records more than one, the last row wins — acceptable for this read-model.
    return {row["child_id"]: row["mother_id"] for row in result.mappings().all()}
```

- [ ] **Step 4: Wire attribution into `build_descendants_tree`.** After the spouse fetch (Step 3 of the existing function), build a `(father_id, wife_id) -> spouse_order` map from the same spouse rows, e.g. while populating `nodes[for_id].spouses` also record `spouse_order_map[(for_id, uuid.UUID(row["spouse_id"]))] = row["spouse_order"]`. After the nodes dict is built, `mothers = await _mother_map(db, list(nodes.keys()), clan_id)`. In `node_to_dict`, add:

```python
            "mother_id": (str(mothers[node.id]) if node.id in mothers else None),
            "mother_spouse_order": (
                spouse_order_map.get((node.parent_id, mothers[node.id]))
                if node.id in mothers and node.parent_id is not None
                else None
            ),
```
(`spouse_order_map` and `mothers` are closed over by `node_to_dict`; the root node has `parent_id=None` so its `mother_spouse_order` is `None`.)

- [ ] **Step 5: Add the schema fields.** In `app/schemas/tree.py`, add to `TreeNodeSummary` (inherited by `TreeNodeDetail`), `TreeNode`, and `FocusTreeNode`:

```python
    mother_id: str | None = None
    mother_spouse_order: int | None = None
```
Keep `model_rebuild()` calls intact.

- [ ] **Step 6: Run tests green** — `uv run pytest tests/integration/test_tree_focus.py -k "mother" -v`.
- [ ] **Step 7: Full gate.**
- [ ] **Step 8: Commit** — `git add app/services/tree_builder.py app/schemas/tree.py tests/integration/test_tree_focus.py` ; `"feat(backend): derive mother_id + mother_spouse_order on tree child nodes (contract-freeze)"`.

---

## Self-Review
- **đời-everywhere** → Task 1 (base_generation computed per root, stamped in one place; cm.generation deprecated; wrong-cm test proves it). ✅
- **mother_id/mother_spouse_order** → Task 2 (derived female-parent + spouse-order match; đa thê + null-mother tests). ✅
- Read-model only, no migration; schema fields additive; clan-scoped lookups. ✅
- Type consistency: `base_generation: int | None` identical across service/repo/port/handler; `mother_id: str | None`, `mother_spouse_order: int | None` identical across builder output + all tree schemas. ✅
