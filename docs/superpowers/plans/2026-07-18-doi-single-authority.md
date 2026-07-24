# Đời Single Authority — Pedigree Collapse (A4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One canonical đời authority (con theo đời cha — ADR-027) consumed by `/tree`, `/tree/focus`, ancestors/subtree, and the export; pedigree-collapse children render under BOTH parents (full node under the canonical parent, `pedigree_collapse_ref` stub under the other). Closes review finding H4. Spec: `docs/superpowers/specs/2026-07-18-doi-single-authority-design.md`.

**Architecture:** New pure-ish `compute_generation_map(db, clan_id)` in `app/services/tree_builder.py` (beside `find_clan_founder`) returning `{person_id: DoiEntry(generation, canonical_parent_id)}`; exposed through the `TreeRepository` port for handlers; called directly by the export query port (both infrastructure — verify lint-imports allows, else hoist the pure computation and pass rows in). No migration — the flat SQL correctly enumerates paths; the AUTHORITY dedups.

**Tech Stack:** SQLAlchemy async raw SQL fetch + pure-Python BFS/topological computation; real-PG integration tests following `tests/integration/test_tree_focus.py`'s handler-level pattern.

## Global Constraints

- **The rule (ADR-027), verbatim:** đời(founder) = 1. For every other reachable person X: canonical parent = the in-set parent chosen by priority `(gender_rank, type_rank, person_id)` where gender_rank = 0 male / 1 female / 2 other-unknown and type_rank = biological 0 > adopted 1 > step 2 > foster 3; đời(X) = đời(canonical parent) + 1. "In-set" = descends from the founder — a married-in father (not descended) NEVER captures the child's đời; the child follows the mother's line then. Deterministic ties by `person_id`.
- **No other đời computation may survive**: `base + depth`, `depth + 1`, and ancestor-walk arithmetic all get replaced by map lookups. Grep for them at the end (`grep -rn "depth + 1\|base_generation\|base + " backend/app` and justify every remaining hit).
- No founder / disconnected root → map lacks entries → `generation: None` (current behavior preserved); attachment falls back to FIRST-seen parent per row order (deterministic — today's last-wins is replaced, never kept).
- `pedigree_collapse_ref: bool = False` is ADDITIVE on tree child schemas — B1 journey and A3 đời tests must pass UNTOUCHED.
- Stubs carry `{id, full_name, gender, generation, mother_id, pedigree_collapse_ref: True}` and EMPTY children/spouses — never the subtree (nested-collapse blowup).
- No new error codes; no migration; `clan_memberships.generation` untouched.
- RED-first; full gate before done: `cd backend && uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports`.

---

### Task 1: RED — the H4 disagreement family + rendering + fallback tests

**Files:**
- Create: `backend/tests/integration/test_doi_authority.py`

**Interfaces:**
- Consumes: `migrated_db_url`; handler-level pattern from `tests/integration/test_tree_focus.py` (build handlers/repos over a real session — copy its fixture wiring); export port from `app/infrastructure/persistence/export_query_port.py`.
- Produces: the executable spec for Tasks 2–3. Every H4 test FAILS today; fallback pins PASS.

- [ ] **Step 1: Write the test file.** Seed helper (mirror `test_tree_focus.py`'s seeding): clan; persons with EXPLICIT gender; `clan_memberships` rows (founder row `is_founder=true` — one, per 023); live biological `parent_child` edges (+ one adoptive where the scenario needs it); marriages where relevant. Scenarios (full code in the file; each names its family in the docstring):

```python
# THE H4 FAMILY (asymmetric collapse):
#   F (male, founder, đời 1)
#   ├─ S (male, F's son, đời 2)
#   │   └─ GS (male, S's son, đời 3)          ← cha line
#   └─ D (female, F's daughter, đời 2)         ← mẹ line
#   GS + D → child C.
#   Con theo đời cha: đời(C) = đời(GS) + 1 = 4.
#   Min-depth (old focus/export) would say đời(D) + 1 = 3 → those tests are RED today.

async def test_h4_family_all_consumers_agree_on_doi_4(...):
    # /tree (get_full_tree handler): find C's node → generation == 4
    # /tree/focus (get_focus_view for C): generation_of_focus == 4
    # export generation_map: generations[C] == 4
    # ONE authority, THREE consumers, one answer.

async def test_h4_child_renders_under_both_parents(...):
    # /tree: full C node under GS (canonical, has real children list);
    # stub under D: pedigree_collapse_ref is True, no children, id == C, generation == 4.
    # D's branch is NOT childless anymore.

async def test_symmetric_collapse_same_doi(...):
    # F → S1 (m) → H (m, đời 3); F → S2 (m) → W (f, đời 3); H+W → C2.
    # đời(C2) == 4 everywhere; canonical parent == H (father); stub under W.

async def test_no_father_fallback_follows_mother(...):
    # child with ONLY an in-tree mother (father married-in, no membership/descent):
    # đời(child) == đời(mother) + 1. Pins existing correct behavior.

async def test_adoptive_father_carries_the_line(...):
    # child whose only in-tree FATHER edge is relationship_type='adopted'
    # (bio father married-in/not descended); in-tree bio MOTHER exists with a
    # SHORTER line. Con nuôi lập tự: đời follows the ADOPTIVE FATHER, not the mother.

async def test_mother_shorter_line_does_not_capture_doi(...):
    # the divergence case isolated: cha đời 3, mẹ đời 2 → child đời 4 (NOT 3).
```

Assert generations by id-matched node lookup (`next(n for n in ... if n["id"] == ...)`), never positionally.

- [ ] **Step 2: Run — record RED.** `uv run pytest tests/integration/test_doi_authority.py -v`. Expected: the H4 all-consumers test FAILS (focus/export report 3), the rendering test FAILS (child under one parent; no `pedigree_collapse_ref` field), mother-shorter test FAILS on focus/export; fallback pins (no-father, and possibly symmetric) may PASS today — record exactly which.
- [ ] **Step 3: Commit** — `git commit -m "test: RED — pedigree-collapse đời disagreement across /tree, focus, export (H4)"`.

---

### Task 2: The authority + tree consumers

**Files:**
- Modify: `backend/app/services/tree_builder.py` (new `DoiEntry` + `compute_generation_map`; rewrite dedup/attach/stamping in `build_descendants_tree`)
- Modify: `backend/app/domain/tree/repository.py` (port: `get_generation_map`)
- Modify: `backend/app/infrastructure/persistence/tree_repository.py` (impl delegating to the services function)
- Modify: `backend/app/application/tree/handlers.py` (`_base_generation` → map; ancestors/subtree stamping → map)
- Modify: `backend/app/schemas/tree.py` (`pedigree_collapse_ref: bool = False` on ALL tree child-node models — the four classes with `birth_date: HistoricalDate` defaults)

- [ ] **Step 1: The authority** (complete code; adjust imports to the module):

```python
@dataclass(frozen=True)
class DoiEntry:
    generation: int
    canonical_parent_id: uuid.UUID | None  # None only for the founder


_GENDER_RANK = {"male": 0, "female": 1}
_TYPE_RANK = {"biological": 0, "adopted": 1, "step": 2, "foster": 3}


async def compute_generation_map(
    db: AsyncSession, clan_id: uuid.UUID
) -> dict[uuid.UUID, DoiEntry]:
    """Single đời authority (ADR-027): con theo đời cha.

    đời(founder) = 1; đời(X) = đời(canonical parent) + 1 where the canonical
    parent is X's highest-priority parent AMONG THOSE DESCENDED FROM THE
    FOUNDER: father first (biological > adopted > step > foster), then mother,
    then unknown-gender; person_id tiebreak. A married-in parent (not descended
    from the founder) never captures the child's đời. Every tree/export surface
    MUST read đời from this map — no depth arithmetic anywhere else (H4).
    Returns {} when the clan has no designated founder.
    """
    founder_id = await find_clan_founder(db, clan_id)
    if founder_id is None:
        return {}
    rows = (
        await db.execute(
            text(
                "SELECT pc.parent_id, pc.child_id, pc.relationship_type, "
                "       par.gender AS parent_gender "
                "FROM public.parent_child pc "
                "JOIN public.persons par ON par.id = pc.parent_id AND par.is_deleted = false "
                "JOIN public.persons ch  ON ch.id  = pc.child_id  AND ch.is_deleted  = false "
                "WHERE pc.created_by_clan_id = :clan AND pc.is_deleted = false"
            ),
            {"clan": clan_id},
        )
    ).all()

    children_of: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    parents_of: dict[uuid.UUID, list[tuple[int, int, uuid.UUID]]] = defaultdict(list)
    for r in rows:
        children_of[r.parent_id].append(r.child_id)
        parents_of[r.child_id].append(
            (
                _GENDER_RANK.get(r.parent_gender, 2),
                _TYPE_RANK.get(r.relationship_type, 4),
                r.parent_id,
            )
        )

    # Reachable set (descendants of the founder) — bounded; graph is acyclic
    # (ADR-023/025 DB backstops), belt-and-braces visit guard anyway.
    reachable: set[uuid.UUID] = {founder_id}
    frontier = [founder_id]
    while frontier:
        nxt: list[uuid.UUID] = []
        for pid in frontier:
            for child in children_of.get(pid, ()):
                if child not in reachable:
                    reachable.add(child)
                    nxt.append(child)
        frontier = nxt

    # Kahn topological order over in-set edges, then one pass computes đời.
    indeg: dict[uuid.UUID, int] = {n: 0 for n in reachable}
    for child in reachable:
        indeg[child] = sum(1 for _, _, p in parents_of.get(child, ()) if p in reachable)
    queue = [n for n, d in indeg.items() if d == 0]  # the founder (+ any in-set orphans)
    result: dict[uuid.UUID, DoiEntry] = {founder_id: DoiEntry(1, None)}
    while queue:
        node = queue.pop()
        for child in children_of.get(node, ()):
            if child not in reachable:
                continue
            indeg[child] -= 1
            if indeg[child] == 0:
                queue.append(child)
                in_set = sorted(p for p in parents_of[child] if p[2] in reachable and p[2] in result)
                if in_set:
                    canon = in_set[0][2]
                    result[child] = DoiEntry(result[canon].generation + 1, canon)
    return result
```

NOTE the `p[2] in result` guard: an in-set parent always resolves by topo order, but an in-set node unreachable-through-result (multi-root in-set orphan seeded out-of-band) must not KeyError — if you find that guard can drop a legitimate parent, restructure (e.g., compute canonical parent from `reachable` and read its DoiEntry after topo completes) and prove it with the symmetric test. Verify with the Task-1 file.

- [ ] **Step 2: Port + impl** — `TreeRepository.get_generation_map(clan_id) -> dict[uuid.UUID, DoiEntry]` (port returns `Any`-typed like siblings if the port style demands framework-free types — check `app/domain/tree/repository.py`'s existing signatures and match); infrastructure delegates to `compute_generation_map`.
- [ ] **Step 3: Builder rewrite** (`build_descendants_tree`): accept `doi_map: dict[uuid.UUID, DoiEntry] | None = None` (replacing `base_generation` — check every call site). Step-2 dedup: FIRST row wins for node data (deterministic); `node.generation = doi_map[id].generation if id in doi_map else None`. Step-4 wiring: attach under `doi_map[id].canonical_parent_id` when mapped AND that parent is in `nodes`; else first-seen `parent_id`. Collect ALL distinct (child, parent) pairs from the flat rows; for every extra in-nodes parent, append a STUB (new lightweight TreeNode with `pedigree_collapse_ref=True`, empty children/spouses, same generation/mother_id) to that parent's children. Add `pedigree_collapse_ref: bool = False` to the `TreeNode` dataclass + `node_to_dict` emits it. Stubs participate in child sorting.
- [ ] **Step 4: Handlers** — `_base_generation` becomes a map lookup (`(await self._repo.get_generation_map(clan_id)).get(root_id)`); fetch the map ONCE per request and reuse for base + ancestor stamping (`gen = entry.generation if (entry := doi.get(row_id)) else None` — ancestors rows use str ids, convert); pass the map into `build_descendants_tree`. Delete the ancestor-walk depth arithmetic.
- [ ] **Step 5: Schemas** — `pedigree_collapse_ref: bool = False` on the four tree child-node classes in `app/schemas/tree.py`; the tree coherence guard in `tests/integration/test_tree_focus.py` (schema `model_validate` of a real wire dict) must still pass — extend its seeded family with a collapse if needed to sabotage-verify the new field (report what you did).
- [ ] **Step 6: Run** — Task-1 file: H4 + rendering + mother-shorter now GREEN (export test still RED — Task 3); `test_tree_focus.py`, `test_founder_designation.py`, `test_e2e_journeys.py` all green (B1/A3 asserts untouched). Grep-verify no stray đời arithmetic: `grep -rn "depth + 1\|base_generation" backend/app` — justify every hit in the report.
- [ ] **Step 7: Commit** — `git commit -m "fix(tree): single đời authority — con theo đời cha; collapse children render under both parents (H4, ADR-027)"`.

---

### Task 3: Export consumer

**Files:**
- Modify: `backend/app/infrastructure/persistence/export_query_port.py` (`generation_map` delegates to `compute_generation_map`; keep the legacy multi-founder loop shape ONLY if the shared function can't express it — post-023 there is one founder, so a single call suffices; document the legacy note in the docstring)
- Possibly: `backend/tests/integration/test_clan_export_json.py` (the single-founder determinism pin re-verified against the new authority — update ONLY if its seeded expectations used min-depth semantics on an asymmetric family; report)

- [ ] **Step 1:** Delegate; check import-linter (`uv run lint-imports`) — if infrastructure→services is forbidden, hoist per the spec note (pure function taking rows) and say so.
- [ ] **Step 2:** Task-1's export assertion goes GREEN; `test_clan_export_json.py` + GEDCOM tests green (đời notes now theo-cha).
- [ ] **Step 3:** Commit — `git commit -m "fix(export): generation_map reads the shared đời authority"`.

---

### Task 4: Docs — ADR-027 + contracts (grep-verified)

**Files:**
- Modify: `docs/architecture/tree-read-model.md` (the canonical rule: priority list verbatim from Global Constraints; both-parents rendering + stub semantics; divergence-from-min-depth example)
- Modify: `docs/contracts/rest-tree-api.md` + `docs/contracts/tree-focus.md` (`pedigree_collapse_ref` field — additive; đời consistency guarantee across /tree, focus, ancestors, export)
- Create: `docs/decisions/027-doi-single-authority.md` (format of ADR-026: Context = H4 with the concrete two-path family; Decision = con theo đời cha + priority + one authority function + stub rendering; Consequences = three consumers now agree, GEDCOM đời notes theo-cha, stubs additive, disconnected/undesignated → generation null, per-request O(edges) computation (perf net B3 revisits caching); Alternatives rejected = min-depth (reckons through the mother when her line is shorter), full-subtree duplication (nested-collapse blowup))
- Modify: `docs/decisions/README.md` (027 row)

- [ ] **Step 1:** Grep first: `grep -rn "generation\|đời\|depth + 1\|pedigree" docs/contracts docs/architecture --include='*.md' | grep -v "review-2026-07-18\|superpowers"` — disposition EVERY hit (stale "founder distance + 1"-style definitions must become the canonical-parent rule or reference ADR-027). Also update the repo-root/backend `CLAUDE.md` đời bullet if it states plain "founder distance + 1" (check both CLAUDE.md files — the contract line must not contradict ADR-027).
- [ ] **Step 2:** Write; re-run grep; zero stale statements. Commit — `git commit -m "docs: ADR-027 con theo đời cha — đời single authority + collapse rendering"`.

---

### Task 5: Full gate + verification (controller-run)

- [ ] `cd backend && uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports` — all five green.
- [ ] Confirm Task 1's RED record shows the original three-consumer disagreement (the negative control for the whole change).
