# Đời Single Authority — Pedigree Collapse (A4) — Design

**Date:** 2026-07-18
**Source finding:** H4 in `docs/architecture/backend-review-2026-07-18.md`. When a
child descends from thủy tổ via BOTH parents (in-clan marriage — common in real
gia phả), the flat SQL (`get_family_tree_flat`, one row PER LINEAGE PATH) feeds
three consumers that disagree:
- `/tree` builder (`tree_builder.py` step 2): `nodes[id] = node` over depth-ASC
  rows → the **deepest** duplicate wins, overwriting `parent_id` → the child
  renders under only ONE parent (the other's branch silently loses them) with
  the deepest đời.
- `/tree/focus` `_base_generation` + export `generation_map`
  (`export_query_port.py:100-111` `setdefault` over depth-ASC rows) → the
  **shallowest** wins.
Same person: đời 4 on one endpoint, đời 5 on another; one parent childless.
**Owner decision:** canonical đời = **con theo đời cha** (patrilineal preference),
over min-depth.

## The canonical đời rule (ADR-027)

For a clan with founder F (đời 1), over live clan-scoped `parent_child` edges
(the same edge set the tree walks — all relationship types):

- đời(F) = 1 (base for /tree/focus subtrees comes from the same map).
- For every other person X reachable from F: pick X's **canonical parent** P
  among X's in-set parents by priority —
  1. father (male parent), `relationship_type` priority biological > adopted >
     step > foster;
  2. else mother (female parent), same type priority;
  3. else any in-set parent (unknown gender), same type priority;
  ties broken by `person_id` (deterministic).
  Then **đời(X) = đời(P) + 1**.
- Well-founded: the graph is acyclic (ADR-023/025 backstops) — computed by one
  pass over a topological traversal.
- Divergence from min-depth ONLY when the mother's line is closer to thủy tổ
  than the father's — the owner-decided case: con vẫn theo đời cha.
- Adopted sons carry the line (con nuôi lập tự) — hence type priority, not
  biological-only.

## Single authority implementation

One function — `compute_generation_map(...)` in `app/services/tree_builder.py`
(beside `find_clan_founder`; pure over data fetched by one query: live
clan-scoped edges joined with parent gender + relationship_type, starting set =
descendants of F, honoring the existing `_MAX_TREE_NODES` and max-generations
caps) → `dict[person_id, int]`.

Consumers (ALL of them — no other đời computation may remain):
1. **`build_descendants_tree`**: node dedup keeps ONE node per person; its
   `parent_id`/attachment = the canonical parent from the same rule; node
   `generation` = map value (offset for non-founder-rooted subtrees: when the
   requested root R ≠ F, generations still come from the map — no depth
   arithmetic).
2. **Tree handlers** (`application/tree/handlers.py`): `_base_generation` and
   the per-row generation stamping switch to map lookups (base = map[root]).
3. **Export** (`export_query_port.generation_map`): delegates to the shared
   function per founder (legacy multi-founder loop shape retained; live schema
   has one founder post-023). GEDCOM đời notes become consistent automatically.
4. `get_ancestors_flat` consumers: ancestor generations = map lookups, not
   `base − depth`.

Import-boundary note: application/tree already imports `app.services
.tree_builder` (existing, ratcheted reality); export_query_port (infrastructure)
gains the same import — verify against import-linter contracts; if the
services fence forbids it, hoist the pure computation into the services module
and have infrastructure pass rows in (implementation detail, decided by
lint-imports at build time — either wiring keeps ONE authority).

## Rendering: the child appears under BOTH parents

- Under the **canonical parent**: the full node (children, spouses — exactly as
  today).
- Under each **other** in-tree parent: a lightweight **reference stub** —
  `{id, full_name, gender, generation, pedigree_collapse_ref: true}` with NO
  children/spouses — so the branch shows the child without duplicating the
  whole subtree (full duplication would blow up nested collapse cases).
- New OPTIONAL field `pedigree_collapse_ref: bool` (default false/absent) on
  tree child nodes: additive, non-breaking. Schemas (`schemas/tree.py` TreeNode
  family) updated; the B1 journey's exact asserts remain valid (no collapse in
  its family).
- Child-sorting and đa-thê `mother_id` grouping apply to stubs too (a stub still
  carries `mother_id` so it groups under the right wife).

## What does NOT change

- `/tree/path` kinship descriptors (path-based, independent of đời).
- The flat SQL functions themselves (they correctly enumerate paths; the
  AUTHORITY dedups) — no migration.
- `clan_memberships.generation` stays deprecated/untouched.
- Founder designation semantics (A3/ADR-026).

## Error/perf notes

- No new error codes. Map computation is O(nodes + edges) per request on data
  already capped by `_MAX_TREE_NODES`; one extra query fetching edge
  gender/type. Acceptable; no caching in this PR (revisit with the perf net B3).

## Docs

- `docs/architecture/tree-read-model.md`: the canonical rule (con theo đời
  cha, priority list, both-parents rendering, stub semantics).
- `docs/contracts/rest-tree-api.md` + `tree-focus.md`: `pedigree_collapse_ref`
  field; đời consistency guarantee across endpoints.
- **ADR-027** (+ decisions README): the rule, the rejected min-depth
  alternative, the stub-vs-duplication rendering choice.
- Grep sweep: `generation|đời|doi|depth + 1|pedigree` across docs/contracts +
  docs/architecture; per-hit dispositions.

## Tests (real-DB; RED-first)

1. **The H4 family** (asymmetric collapse), RED against main: founder F đời 1;
   son S đời 2; S's son GS đời 3 (cha-side); F's daughter D đời 2 (mẹ-side);
   GS marries D... simpler concrete: father line F→S→GS (GS đời 3), mother
   line F→D (D đời 2); GS + D's child C. Con theo đời cha: đời(C) = 4.
   Min-depth would say 3. Assert đời(C) == 4 on `/tree` (node under GS), on
   `/tree/focus/{C}` (`generation_of_focus == 4`), AND in the export
   generation_map — three consumers, one answer. RED today: /tree gives 4-or-3
   nondeterministically-by-order (deepest wins = 4 here… construct so the
   CURRENT behaviors demonstrably disagree: /tree deepest = 4, focus/export
   shallowest = 3 — the test asserts all-4, so it's RED on focus/export).
2. **Both-parents rendering**: C appears fully under GS (canonical) AND as a
   stub under D (`pedigree_collapse_ref is True`, no children key content);
   D's branch is no longer childless. RED today (child under one parent only).
3. **Symmetric collapse** (same-đời marriage): both paths agree; no divergence;
   stub still present under the non-canonical parent; canonical parent = father.
4. **No-father fallback**: child with only an in-tree mother → đời(mẹ) + 1
   (unchanged behavior, pinned).
5. **Adoptive father priority**: in-tree adoptive father (no in-tree bio
   father) → đời follows him (con nuôi lập tự pinned).
6. **Coherence**: tree schema validates a real collapse response
   (documentation-only responses= discipline); B1 journeys + A3 đời tests
   stay green untouched.
