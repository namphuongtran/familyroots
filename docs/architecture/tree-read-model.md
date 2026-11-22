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
  `children` array is empty. Don't assume the two fields agree. The converse
  asymmetry also holds: a stub NOT at the boundary reports
  `has_more_descendants: false` with empty children while its canonical mirror
  visibly carries them — `pedigree_collapse_ref` is the client's cue that descent
  happens at the canonical occurrence, never at the stub.

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

### Pedigree-collapse fan-out, measured 2026-11-22 (#398)

`get_family_tree_flat` (migration 013, not redefined since) guards cycles **per path**
only, so a person reachable through two in-tree parents comes back once per lineage
path, with every descendant below them. `build_descendants_tree` keeps the first row
per person, but checks `_MAX_TREE_NODES` against the **row** count and reports rows as
`actual_nodes`.

- **Benchmark:** `backend/tests/integration/test_tree_pedigree_collapse_benchmark.py`,
  marked `slow` and skipped unless `FAMILYROOTS_BENCH_TREE` is set. Command, from
  `backend/`:
  `FAMILYROOTS_BENCH_TREE=1 uv run pytest -s -q -m slow tests/integration/test_tree_pedigree_collapse_benchmark.py`
- **Machine:** the local Postgres 18.6 container (aarch64, musl), 10 vCPU, 7 GiB RAM,
  with the test client on the same host. Not production hardware.
- **Clan:** 5,246 persons: a 12-generation blood line of 3,323 descendants
  (generation sizes 1, 2, 4 … 512, 900, 1,400), and one married-in spouse for each of
  the 1,923 descendants who have children. 6,644 live `parent_child` edges. A cousin
  marriage pairs a man and a woman of the same generation, with different parents and
  the same grandparent, and makes her the mother of his children. Marriages are spread
  over generations 5 to 11, so some collapses sit inside others. The person count is
  the same at every level.
- **Times** are medians of 5 runs. "SQL" is the exact `SELECT * FROM
  get_family_tree_flat(...)` with every row fetched. "Edge read" is the one statement
  `compute_generation_map` issues when the founder is passed. `GET /tree` uses the
  default `max_generations=10`, which reaches depth 10 (11 generations, 1,923 persons),
  through the RS256 harness with `get_db` on the privileged maker, so it leaves out
  the RLS seam.

| Cousin marriages | Rows, depth 10 | Persons, depth 10 | Rows − persons | Rows, depth 50 | Persons, depth 50 | Rows − persons | SQL d10 / d50 (ms) | Edge read (ms) | `compute_generation_map` (ms) | `GET /tree` (ms) |
|---|---|---|---|---|---|---|---|---|---|---|
| 0  | 1,923 | 1,923 | 0   | 3,323 | 3,323 | 0     | 59.0 / 71.8 | 48.6 | 65.2 | 272.3 |
| 5  | 2,148 | 1,923 | 225 | 3,722 | 3,323 | 399   | 61.6 / 74.0 | 51.6 | 69.9 | 275.4 |
| 20 | 2,714 | 1,923 | 791 | 4,731 | 3,323 | 1,408 | 65.0 / 81.6 | 9.6  | 26.6 | 236.0 |

The `GET /tree` and edge-read times are noisy at this scale. An earlier run on the same
machine read `GET /tree` at 207.4, 244.0 and 282.4 ms and the edge read at 48.6, 51.0
and 50.3 ms. The row counts are the same on every run. `total_persons` in the response
is 1,923 at every level, so the dedup works. Only the database's work and the cap
check see the duplicates.

**Reading.**

- At this size the fan-out costs little: 1.41× rows at depth 10 and 1.42× at depth 50
  with 20 cousin marriages. SQL time grows by about 10 %, and `GET /tree` stays inside
  its run-to-run noise.
- **Yes, the 50,000-row cap can be reached before 50,000 distinct persons.** At the
  worst ratio measured, 1.424, it trips at about 35,100 persons, and the error then
  reports rows as `actual_nodes`. The ratio is not bounded by clan size. Every
  collapse multiplies the subtree under it, and collapses inside collapses multiply
  each other, so a deep clan with many intermarriages high in the tree can reach the
  cap at a much smaller size. A clan of several thousand people, the roadmap's M2 size,
  is more than an order of magnitude under the cap at the ratios measured here.
- No follow-up issue was filed. At the roadmap's size the numbers show no latency or
  cap problem. If a change is chosen later, the options are counting distinct persons
  for the cap, or a global visited set in the CTE (as migration 019 did for
  `find_relationship_path`). Either one should cite this table.

## Testing expectations

Changes here need real-DB integration tests (see `backend/CLAUDE.md`): a đa thê
fixture (father + 2 wives, children under each) asserting `mother_id`/`mother_spouse_order`;
a wrong hand-entered `cm.generation` still yielding correct computed đời; two-sided
clan isolation (clan A sees its edges, clan B doesn't); pedigree-collapse fixtures
(`backend/tests/integration/test_doi_authority.py`) proving `/tree`, `/tree/focus`,
and the export all agree on đời for the same person (ADR-027, H4), the
divergence-from-min-depth case, and the adoptive-father-carries-the-line case (con
nuôi lập tự).
