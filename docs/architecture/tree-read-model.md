# Tree Read-Model Design

How the family-tree endpoints assemble their responses. This is a pure **read-model**
(CQRS query side): nothing here writes; all genealogy facts come from `persons`,
`marriages`, `parent_child`, `clan_memberships`, `branches`.

Code: `backend/app/application/tree/handlers.py` (orchestration, đời stamping),
`backend/app/services/tree_builder.py` (node assembly, batched lookups),
`backend/app/infrastructure/persistence/tree_repository.py` (SQL),
SQL functions in migrations `003 → 005 → 011 → 013`.

## Data sources

- **SQL functions** `get_family_tree_flat(root, clan, depth)` and
  `get_ancestors_flat(person, clan, depth)` (recursive CTEs, `SECURITY INVOKER`)
  return flat `(person, depth, …)` rows. Both are **clan-scoped** (only persons in the
  clan's `clan_memberships`, only edges with the clan's `created_by_clan_id`) and
  carry **cycle guards** (path-array check). Since migration 013 they return
  `birth/death_date_precision` + `_display` for HistoricalDate serialization.
- **Edges are per-clan**: each tree only reads marriages/parent-child rows the clan
  created (see migration 007 and `data-model.md`).

## đời (generation) — graph-computed, one authority

`generation` in every tree response is **always computed from the graph**, never read
from `clan_memberships.generation` (that column is deprecated as a display source —
kept only as data; ADR-012).

- Convention: **thủy tổ (clan founder) = đời 1**.
- `_base_generation(root_id, clan_id)`: distance from the root to the clan founder
  via `get_ancestors_flat(root_id, clan_id, 50)` + 1. The fixed 50 is the intrinsic
  `ancestor_depth` bound, independent of the request's `max_generations`.
- Descendant nodes: `generation = base_generation + node.depth`.
- Ancestor rows (`/tree/ancestors`): `generation = base - depth`, guarded to `null`
  when `< 1`.
- `null` when the node isn't descended from a founder or the clan has no founder —
  clients must render "đời ?" honestly, not guess.

## đa thê (polygamy) mother attribution — derived, no schema change

Child nodes carry `mother_id` + `mother_spouse_order` so clients can group a father's
children under each wife (vợ cả / vợ hai / …):

- `_mother_map(child_ids, clan_id)`: for each child, its **female parent** among the
  clan's `parent_child` edges → `mother_id` (`null` when no mother edge is recorded —
  the child renders ungrouped).
- `mother_spouse_order` = `spouse_order` of the marriage `(father, mother)` from the
  batched spouse lookup; `null` when no matching marriage record.
- Assumption: at most one female-parent edge per child; if data ever has more, the
  last one seen wins (read-model tolerance, not a domain invariant).
- Deliberately **derived** — no `parent_role`/`via_spouse_id` columns (ADR-012).
  Revisit storage only if derivation proves lossy on real data.

## Endpoints and their assembly

| Endpoint | Shape | Notes |
|---|---|---|
| `GET /tree` | recursive `TreeNode` from founder/root | `max_generations` 1–50 (default 10) |
| `GET /tree/subtree/{id}` | same, rooted at person | default depth 5 |
| `GET /tree/ancestors/{id}` | flat ancestor chain | đời = base − depth |
| `GET /tree/focus/{id}` | breadcrumb `ancestors[]` + bounded `focus_subtree` | `descendants` 1–6 (default 2), `ancestors` 0–50; adds branch info, `has_more_descendants`, membership_role |
| `GET /tree/path` | shortest kinship path + Vietnamese descriptor | age-based terms only when both `birth_date_precision == 'exact'` |

All node dates serialize as HistoricalDate objects. `SpouseNode.marriage_date` /
`divorce_date` intentionally stay scalar dates.

## Performance guards

- Batched lookups in `tree_builder` (spouses, mothers, branches) — no per-node N+1.
- Node cap in the builder (50k) and depth caps per endpoint bound worst-case clans.
- `profile=summary|detail|full` controls node width; tree endpoints do **not**
  support `fields`/`include`.

## Testing expectations

Changes here need real-DB integration tests (see `backend/CLAUDE.md`): a đa thê
fixture (father + 2 wives, children under each) asserting `mother_id`/`mother_spouse_order`;
a wrong hand-entered `cm.generation` still yielding correct computed đời; two-sided
clan isolation (clan A sees its edges, clan B doesn't).
