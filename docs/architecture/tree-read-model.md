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

## đời (generation) — graph-computed, one authority (ADR-027)

`generation` in every tree response is **always computed from the graph**, by a
**single authority function**, `compute_generation_map(db, clan_id)`
(`tree_builder.py`) — never read from `clan_memberships.generation` (deprecated as a
display source; ADR-012) and never derived by per-endpoint depth arithmetic. The
per-endpoint depth arithmetic this section used to describe (`base_generation +
node.depth`) is exactly what produced [H4](#h4-the-defect-this-replaces) below and no
longer exists in the code — every consumer now calls the same map.

### The rule: con theo đời cha (ADR-027)

- **đời(thủy tổ / founder) = 1.**
- For every other person X, the **canonical parent** is X's highest-priority parent
  **among those descended from the founder**, in this fixed priority order:
  1. father (male parent) — `relationship_type` **biological > adopted > step > foster**
  2. mother (female parent)
  3. unknown-gender parent
  — **`person_id` tiebreak** when priority is otherwise equal.
  A parent who is **not** descended from the founder (a married-in spouse with no
  ancestry of their own in this clan) is never eligible as canonical and **never
  captures the child's đời**, no matter how the priority list would otherwise rank
  their gender/relationship_type.
- **đời(X) = đời(canonical parent) + 1.**
- **Deterministic always** — same graph, same result, every call, regardless of
  row/traversal order.
- **No founder, or X disconnected from the founder → `generation` is `null`.**
  Clients must render "đời ?" honestly, never guess.

### Implementation: two-pass topological

The canonical-parent choice above is **static** — it only depends on each child's
fixed set of in-tree parents, not on any other node's đời — so `compute_generation_map`
splits the work into two passes over the clan's `parent_child` edges:

1. **BFS from the founder** to find the reachable set (everyone descended from thủy
   tổ; unreachable persons get no map entry → `generation: null`).
2. **Kahn topological order** over that reachable set resolves each node's canonical
   parent (from the priority list, restricted to in-set parents) as soon as its
   indegree hits zero; a single linear pass over that topo order then computes
   `đời(child) = đời(canonical parent) + 1`. Because the canonical choice never reads
   another node's đời, a same-generation tie or an out-of-dependency-order visit can
   never silently pick the wrong parent or KeyError.

Cost is **O(edges) per request** — see Performance guards below (a caching revisit is
tracked as future work, not built).

### Divergence-from-min-depth example

Con theo đời cha can diverge from "shortest path to founder" (min-depth), and by
design **must**:

```
F (founder, đời 1)
├─ Y (đời 2) ── Cha (đời 3)      ← cha's line, longer
└─ Me (đời 2)                     ← mẹ's line, shorter
Cha + Me → Child.
```

Con theo đời cha: `đời(Child) = đời(Cha) + 1 = 4`. Min-depth would instead reckon
through Mẹ's shorter line and say `đời(Me) + 1 = 3` — **wrong**: a patrilineal gia
phả reckons đời through the father even when the mother's line to thủy tổ happens to
be shorter. (Pinned by `test_mother_shorter_line_does_not_capture_doi`,
`backend/tests/integration/test_doi_authority.py`.)

### Both-parents rendering (pedigree collapse)

When a child is reachable from the founder via **more than one in-tree parent**
(pedigree collapse — e.g. two of the founder's descendants marry each other and have
a child), `/tree`, `/tree/subtree` and `/tree/focus` render:

- The **canonical parent**'s branch gets the child's **full node** — real
  `children`/`spouses`, participates in further descent, no
  `pedigree_collapse_ref` marker.
- **Every other in-tree parent** gets a **`pedigree_collapse_ref` stub** for that
  same child instead: the SAME full node shape (every standard field populated —
  built by `dataclasses.replace` from the canonical node) with
  `pedigree_collapse_ref: true` and **empty** `children: []` / `spouses: []` — so
  that parent's branch is never silently rendered childless, but the subtree is
  never duplicated in full under both parents. One schema, no reduced stub variant.
- Stubs participate in the normal children sort (birth_date, then name) alongside
  real siblings — they carry the same sort key as the canonical node they mirror, so
  they appear in correct birth order, not appended at the end.
- A stub's `children`/`spouses` are always forced empty (only the canonical branch
  continues descent). Its `has_more_descendants` (`/tree/focus` only) is **not**
  hard-coded false: `build_focus_view` computes it the same way for every boundary
  node — from whether the underlying person has real children in the database —
  so a stub that lands at the descendant-depth boundary alongside its canonical
  mirror can legitimately report `has_more_descendants: true` even though its own
  `children` array is empty. Don't assume the two fields agree.

### `depth` is a path artifact, not the node's nesting level

Every node carries `depth` (int), inherited unchanged from whichever row of
`get_family_tree_flat` the builder's step-2 dedup pass kept for that person — and
because that dedup keeps the FIRST-seen row and rows arrive `ORDER BY depth ASC`,
`depth` is always that person's **shallowest** lineage distance to the tree root,
regardless of where the node is actually nested in the response.

Nesting instead follows the đời-authority **canonical parent** (ADR-027), which for
a pedigree-collapsed person can be reached by a **longer** path than the shallowest
one `depth` reports. Concretely: a person whose shallowest path is `F → D → C`
(`depth` 2) but whose canonical (father-line) path is `F → S → GS → C` nests three
levels deep under `GS`, while `depth` still reads 2 — nesting level can exceed
`depth`. Because `max_generations` bounds the SQL traversal's row depth (the
shallowest path), not the canonical nesting position, a node can end up nested
**deeper than `max_generations`** in the response tree. `depth` must not be used to
infer nesting level, row count, or đời — use `generation` for đời, and the actual
`children` structure for rendering depth.

### Consistency guarantee — one authority, all surfaces agree

`compute_generation_map` is the **sole** source of both `generation` and the
canonical-parent attach point for **every** consumer: `GET /tree`,
`GET /tree/subtree/{id}`, `GET /tree/ancestors/{id}`, `GET /tree/focus/{id}`, and the
clan JSON/GEDCOM export (`ExportQueryPort.generation_map`,
`backend/app/infrastructure/persistence/export_query_port.py`). No consumer computes
đời independently, from row depth, or from a different traversal. One graph, one
authority function, one answer per person — regardless of which endpoint asked.

#### H4: the defect this replaces

Before ADR-027, `/tree` computed `generation = base_generation + node.depth` from
whichever row of a pedigree-collapsed child the flat SQL result saw first (in
practice, deepest-wins — plus the child silently disappeared from the OTHER parent's
`children`, no stub existed), while `/tree/focus` and the export both derived đời from
`get_ancestors_flat`'s **shallowest** occurrence of an ancestor. For the same person
in the same family this produced `/tree` = 4 vs `/tree/focus` = export = 3 — three
consumers, three different answers, for one person. See
[ADR-027](../decisions/027-doi-single-authority.md) for the full analysis and
`backend/tests/integration/test_doi_authority.py` for the real-DB proof (now GREEN
against the single-authority implementation).

### Thủy tổ (founder) designation — exactly one live founder (ADR-026)

- `find_clan_founder(db, clan_id)` (`tree_builder.py`) resolves the root: the
  `clan_memberships` row with `is_founder = true` for the clan, joined to a
  **non-soft-deleted** person (`persons.is_deleted = false`). Migration `023`'s
  partial unique index `uq_clan_memberships_one_founder` on
  `clan_memberships (clan_id) WHERE is_founder = true` makes more than one live
  founder per clan impossible going forward; the query still carries an
  `ORDER BY joined_at ASC NULLS LAST, person_id` tiebreak so it stays
  deterministic against already-corrupt legacy (pre-023) data.
- **Only write path:** `PUT /clans/me/founder` (admin-only) — see
  [rest-clans-api.md](../contracts/rest-clans-api.md#founder-designation-thủy-tổ).
  Person creation has no founder field; nothing else in the API can set
  `is_founder`.
- **Swap, not accumulate:** designating a different person clears the current
  founder membership and sets the target as founder in two explicitly ordered
  statements (`ClanRepository.swap_founder`) rather than relying on ORM flush
  ordering, because the backing index is an immediate partial unique index
  (Postgres cannot `DEFERRABLE` a partial unique — only constraints, not
  indexes, support deferral). See [ADR-026](../decisions/026-single-founder-designation.md)
  for the concurrency story.
- **Undesignated clan = onboarding state, not a bug.** `GET /tree` without an
  explicit `root_person_id` calls `find_clan_founder` and 404s
  `clan_founder_not_found` when it returns `None` — this is the expected state
  for any clan before its first `PUT /clans/me/founder` call. See
  [frontend-integration-guide.md](../contracts/frontend-integration-guide.md#51-founder-designation-thủy-tổ--tree-onboarding).
- **Soft-deleting the founder re-404s the tree.** Because `find_clan_founder`
  filters `persons.is_deleted = false`, soft-deleting the currently-designated
  founder person makes the clan founder-less again — `GET /tree` 404s
  `clan_founder_not_found`. `is_founder` on the membership row is untouched by
  delete/restore, so the tree re-404s until the founder is **restored**
  (`POST /persons/{id}/restore` alone re-roots the tree — no re-designation
  needed, since the membership's `is_founder` flag never went away) **or** an
  admin **designates someone else** via `PUT /clans/me/founder`.

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
| `GET /tree` | recursive `TreeNode` from founder/root | `max_generations` 1–50 (default 10); pedigree-collapse children render as full node (canonical parent) + `pedigree_collapse_ref` stub (every other in-tree parent) |
| `GET /tree/subtree/{id}` | same, rooted at person | default depth 5; same collapse rendering as `GET /tree` |
| `GET /tree/ancestors/{id}` | flat ancestor chain | đời from `compute_generation_map` (single authority); no per-edge stub concept here |
| `GET /tree/focus/{id}` | breadcrumb `ancestors[]` + bounded `focus_subtree` | `descendants` 1–6 (default 2), `ancestors` 0–50; adds branch info, `has_more_descendants`, membership_role; `focus_subtree` gets the same collapse rendering |
| `GET /tree/path` | shortest kinship path + Vietnamese descriptor | age-based terms only when both `birth_date_precision == 'exact'` |

All node dates serialize as HistoricalDate objects. `SpouseNode.marriage_date` /
`divorce_date` intentionally stay scalar dates.

## Performance guards

- Batched lookups in `tree_builder` (spouses, mothers, branches) — no per-node N+1.
- Node cap in the builder (50k) and depth caps per endpoint bound worst-case clans.
- `profile=summary|detail|full` controls node width; tree endpoints do **not**
  support `fields`/`include`.
- `compute_generation_map` is **O(edges) per request** (ADR-027) — no caching layer
  yet; a caching revisit is tracked as future work (see remediation backlog "B3"),
  not a correctness concern today.

## Testing expectations

Changes here need real-DB integration tests (see `backend/CLAUDE.md`): a đa thê
fixture (father + 2 wives, children under each) asserting `mother_id`/`mother_spouse_order`;
a wrong hand-entered `cm.generation` still yielding correct computed đời; two-sided
clan isolation (clan A sees its edges, clan B doesn't); pedigree-collapse fixtures
(`backend/tests/integration/test_doi_authority.py`) proving `/tree`, `/tree/focus`,
and the export all agree on đời for the same person (ADR-027, H4), the
divergence-from-min-depth case, and the adoptive-father-carries-the-line case (con
nuôi lập tự).
