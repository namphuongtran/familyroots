# Tree Focus Data API — Design Spec

**Date:** 2026-07-11
**Sub-project:** #1 of the "Tree Visualization" feature (backend data contract). Web/mobile
rendering of the approved v4 interactive focus-tree are separate later sub-projects (track K).
**Owner approval:** direction v4 approved; API shape = consolidated `/tree/focus` endpoint;
computed generation (đời) in scope.

## Goal

Serve exactly the data the approved **v4 interactive focus-tree** consumes, in one round-trip
per refocus: a focus person's **ancestor breadcrumb** (up to thủy tổ), the focus person, and a
bounded window of **descendants** below — annotated with **computed đời (generation)**, **chi
(branch)**, **đa thê spouse order**, **dâu/rể role**, **sibling order**, and a **has-more-descendants**
drill flag.

## Why this is not over-engineered (verified current state)

Most of the shape already exists on `main` and is reused, not rebuilt:

- `get_family_tree_flat(root, clan, max)` (migration 005) — clan-scoped, cycle-guarded descendant
  walk; `build_descendants_tree()` (app/services/tree_builder.py) already nests it **with spouses
  (incl. `spouse_order`), `membership_role` (blood/spouse/adopted → dâu/rể), `is_founder`,
  `posthumous_name`, `birth_place`**.
- `get_ancestors_flat(person, clan, max)` (migration 005) — clan-scoped, cycle-guarded ancestor
  walk. **Already exists**; the buggy inline `get_ancestors` just needs to call it.
- Data model already has `parent_child.birth_order`, and a full `branches` table
  (`name`, `branch_order`, `parent_branch_id` → chi/phái/ngành hierarchy) linked via
  `clan_memberships.branch_id`.

So this sub-project is a thin **read-model composition** over hardened SQL, plus a Python
enrichment pass. **No new/altered SQL function → no `RETURNS TABLE` migration.** Existing
`/tree`, `/tree/subtree`, `/tree/path` endpoints are untouched except the shared `get_ancestors`
dedup fix.

## The five gaps this closes

| # | Gap (current) | Fix |
|---|---|---|
| 1 | `get_ancestors` inline recursive SQL fans out on the `parent_child` join → **duplicate ancestors** | Call existing `public.get_ancestors_flat(...)` |
| 2 | `generation` = hand-entered `clan_memberships.generation` (often NULL/wrong) | **Compute đời from the graph** (distance from thủy tổ) |
| 3 | No way to know a cut-off leaf has further descendants | `has_more_descendants: bool` on boundary nodes |
| 4 | Tree nodes carry no chi/branch | Surface `branch_id`, `branch_name`, `branch_order` |
| 5 | Siblings sorted by `birth_date`/name, ignoring explicit `birth_order` | Sort `birth_order` (NULLS last) → `birth_date` → name |

## API contract

```
GET /api/v1/tree/focus/{person_id}
```

Auth: `get_current_user`, `X-Current-Clan-Id` → `get_current_clan_id`, `RequireViewer`
(identical to the other `/tree` routes).

Query params:

| Param | Type | Default | Bounds | Meaning |
|---|---|---|---|---|
| `descendants` | int | `2` | `ge=1, le=6` | Generations below focus (default 2 = con + cháu → a 3-đời window) |
| `ancestors` | int | `50` | `ge=0, le=50` | Ancestor generations up for the breadcrumb (default = full chain to thủy tổ) |

Response (existing envelope `{"data": ...}`):

```jsonc
{
  "data": {
    "focus_person_id": "uuid",
    "generation_of_focus": 3,          // computed đời; null if focus not descended from a founder
    "ancestors": [                     // strict ancestors, ordered thủy-tổ-first (breadcrumb)
      {
        "id": "uuid", "full_name": "…", "gender": "male",
        "birth_date": "1900-01-01", "death_date": null,
        "avatar_url": null, "generation": 1, "is_founder": true
      }
      // … up to parent-of-focus
    ],
    "focus_subtree": {                 // nested TreeNode, focus at root (depth 0)
      "id": "uuid", "full_name": "…", "gender": "…",
      "birth_date": "…", "death_date": "…", "birth_date_approx": false,
      "posthumous_name": null, "avatar_url": null,
      "membership_role": "blood", "is_founder": false,
      "generation": 3,                 // COMPUTED (base_gen + depth), overrides raw cm.generation
      "depth": 0,
      "branch_id": "uuid|null", "branch_name": "Chi Hai|null", "branch_order": 2,
      "has_more_descendants": false,
      "spouses": [
        { "id": "uuid", "full_name": "…", "spouse_order": 1, "status": "married",
          "membership_role": "spouse", /* dâu/rể */ "marriage_date": "…", "…": "…" }
      ],
      "children": [ /* recursive TreeNode, sorted by birth_order → birth_date → name */ ]
    }
  }
}
```

Notes:
- `ancestors` excludes the focus person itself (the client renders focus from `focus_subtree` root).
- Each ancestor's `generation` is `generation_of_focus - depth_from_focus`; null when
  `generation_of_focus` is null.
- `branch_*` and `has_more_descendants` are additive fields present **only** on `/tree/focus`
  nodes; they are not retro-added to `/tree` or `/tree/subtree` (no contract change there).

## Computed đời (generation) — rule and derivation

- **Rule:** thủy tổ (`is_founder = true`) = **đời 1**. A person's đời = (shortest `parent_child`
  distance from the founder) + 1. Not reachable from a founder → đời = **null** (honest "unknown",
  no guess).
- **Derivation without per-node queries** (one anchor propagates arithmetically):
  1. `founder_id = find_clan_founder(clan)` (existing repo method; single founder, `LIMIT 1`).
  2. From `get_ancestors_flat(focus, clan, 50)` (already fetched for the breadcrumb), find the row
     where `person_id == founder_id`; its `depth` = `D`. `generation_of_focus = D + 1`.
     If `founder_id` is null or absent from the chain → `generation_of_focus = null`.
  3. Descendants: `generation = generation_of_focus + node.depth` (each `parent_child` step is +1 đời).
  4. Ancestors: `generation = generation_of_focus - depth_from_focus`.
- **Diamond edge case** (a node reachable via two parents at different depths, e.g. adoption +
  blood): đời follows the traversed `parent_child` path as returned by the flat walk. Documented,
  acceptable for MVP; not resolved to a canonical patriline in this sub-project.
- `clan_memberships.generation` column is **kept** (no destructive migration) but is no longer the
  display source for `/tree/focus`.

## Architecture (hexagonal boundaries preserved)

Layer placement follows the existing tree stack:

- **API** `app/api/v1/tree.py` — add thin `get_focus` route delegating to the handler.
- **Application** `app/application/tree/`
  - `queries.py`: add `@dataclass(frozen=True) GetFocusView(person_id, clan_id, ancestor_depth, descendant_depth)`.
  - `handlers.py`: add `TreeQueryHandler.get_focus_view(query)` — orchestration only:
    membership check (→ `EntityNotFoundError("person_not_found")` = 404), then compose repo
    calls + `build_focus_view` service, apply đời arithmetic, assemble the response dict.
- **Domain** `app/domain/tree/repository.py` — extend the `TreeRepository` port with the new
  read methods (below). Port stays framework-agnostic.
- **Infrastructure** `app/infrastructure/persistence/tree_repository.py`
  - **Fix** `get_ancestors` to call `public.get_ancestors_flat(:person_id, :clan_id, :max)`
    (kills the dup; also gains cycle-guard + `path`). Preserves its current output dict shape.
  - Add `get_ancestors_flat(person_id, clan_id, max) -> list[dict]` (raw rows incl. `depth`,
    `child_id`) for the focus handler's breadcrumb + anchor.
  - Add batched enrichment reads: `branch_map(person_ids, clan_id)`,
    `birth_order_map(person_ids, clan_id)`, `persons_with_children(person_ids, clan_id) -> set`.
    All clan-scoped by `created_by_clan_id` (edge ownership) exactly like the existing joins.
- **Service** `app/services/tree_builder.py` — add `build_focus_view(...)` (or enrich helper)
  that reuses `build_descendants_tree()` for the descendant window, then applies the Python
  enrichment pass: attach `branch_*`, re-sort children by `birth_order → birth_date → name`,
  set `has_more_descendants` on nodes at `depth == descendant_depth`, and stamp computed
  `generation`. Follows the existing service pattern (loose services layer, per backend CLAUDE.md).
- **Schemas** `app/schemas/tree.py` — add a `FocusView` response model (and `branch_*` /
  `has_more_descendants` on a focus-node schema). Additive only.

Data flow (one refocus):
```
route → handler.get_focus_view
  → repo.person_in_clan (404 gate)
  → repo.get_ancestors_flat(focus)         # breadcrumb rows + anchor
  → repo.find_clan_founder(clan)           # anchor id
  → base_gen = (founder depth in chain)+1  # arithmetic, in handler
  → service.build_focus_view(focus, descendants):
        build_descendants_tree(focus)      # existing nested walk
        repo.branch_map / birth_order_map / persons_with_children  # 3 batched queries
        enrich + re-sort + stamp generation
  → assemble {focus_person_id, generation_of_focus, ancestors, focus_subtree}
```

## Error handling

- Focus person not a member of `X-Current-Clan-Id` → `EntityNotFoundError` → 404 (same as
  `/tree/subtree`). Never leak existence across clans.
- Focus with no descendants → `focus_subtree` = lone focus node, `children: []`,
  `has_more_descendants: false`.
- No founder in clan → `generation_of_focus: null`, all node/ancestor generations null; the tree
  still renders (breadcrumb + subtree intact).
- All enrichment queries are clan-scoped by `created_by_clan_id`; a person/edge owned by another
  clan is never surfaced (reuses the C6/C7 isolation rule).

## Testing (real-DB integration; per project verification discipline)

Seed one clan with: thủy tổ (`is_founder`), 3 blood generations, one man with **≥2 marriages**
(`spouse_order` 1/2), one **dâu** (`membership_role='spouse'`), **2 branches** (chi) via
`branch_id`, and explicit `birth_order` on some siblings. Plus a **second clan** sharing no edges.

Cases:
1. **Focus = thủy tổ, descendants=2** → `ancestors: []`, `generation_of_focus == 1`; subtree has
   con (đời 2) + cháu (đời 3); a cháu with children has `has_more_descendants == true`; a
   childless leaf `false`.
2. **Focus = a gen-3 person** → breadcrumb ordered thủy-tổ-first with generations 1,2; each
   ancestor's `generation` correct; `generation_of_focus == 3`.
3. **Ancestor dedup regression** — a person reachable via a fan-out → `get_ancestors` /
   breadcrumb returns each ancestor **once** (guards the fixed bug).
4. **đa thê / dâu-rể** — spouses carry `spouse_order`; a `membership_role='spouse'` node is
   distinguishable.
5. **Sibling order** — children returned ordered by `birth_order` (NULLS last), then birth_date,
   then name.
6. **Branch surfaced** — nodes carry correct `branch_id` / `branch_name` / `branch_order`.
7. **Clan isolation (two-sided)** — focus person of clan A via clan B header → 404; no clan-B
   edge/branch leaks into a clan-A focus view, and vice-versa.
8. **Negatives** — unknown/soft-deleted focus → 404; focus with no descendants → lone node;
   clan with no founder → `generation_of_focus: null` and view still returned.

Quality gate (full, not subset): `uv run pytest`, `uvx ruff check .`, `uvx ruff format --check .`,
`uvx mypy app/ tests/`, import-linter.

## Out of scope (explicit YAGNI)

- Rendering the tree (SVG/Flutter) — separate web/mobile sub-projects.
- Exact "+N đời sau" **count/depth** on the drill chip — a boolean `has_more_descendants` is
  enough for the affordance; precise remaining-depth deferred (fetch-on-expand later if needed).
- Migrating `/tree` and `/tree/subtree` to computed đời — deliberate future task; not silently
  changing existing contracts here.
- Materializing đời into a column with triggers — the on-read graph derivation is the single
  source of truth; materialization only if a future writer needs it.
- Multiple founders / merged-clan apical resolution.
- The other PR-J items (`platform_admin total_users=0`, include-swallow) — unrelated to the tree;
  remain a small separate PR.
```
