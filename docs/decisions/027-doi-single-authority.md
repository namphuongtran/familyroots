# ADR-027: Con Theo Đời Cha — đời Single Authority + Pedigree-Collapse Rendering

## Status
Accepted, shipped (2026-07-18, review finding H4).

## Context

The 2026-07-18 backend review (`docs/architecture/backend-review-2026-07-18.md`)
identified **H4**: when a person descends from the clan founder (thủy tổ) via **both**
parents — pedigree collapse, e.g. two of thủy tổ's descendants marry and have a child
— the three tree-reading consumers computed đời (generation) **independently** and
**disagreed** on the same person:

- **`GET /tree`** derived `generation = base_generation + node.depth` from whichever
  row of the pedigree-collapsed child the flat SQL result (`get_family_tree_flat`)
  happened to dedupe first. In practice this picked the **deepest** occurrence, and —
  because the builder wired each node under a single `parent_id` taken from that same
  row — the child **silently disappeared** from the other parent's `children`
  entirely (no stub, no marker, just a childless-looking branch).
- **`GET /tree/focus`** and the **clan export** both derived đời from
  `get_ancestors_flat`, which is per-lineage-edge and not deduplicated; both consumers
  kept the **shallowest** (minimum-depth) occurrence of a repeated ancestor.
- **Concrete evidence** (the H4 family): thủy tổ F has a son S → GS (GS is đời 3, the
  "cha" line) and a daughter D (đời 2, the "mẹ" line). GS and D marry and have child
  C. `/tree` reported `generation(C) == 4` (via the deeper GS path); `/tree/focus` and
  the export both reported `generation(C) == 3` (via the shallower D path). **One
  person, one clan, one request each — three different answers**, and D's branch was
  missing C altogether on `/tree`.

No consumer implemented a *rule* for which parent should count when paths diverge;
each independently reached for whatever traversal was cheapest to compute from its own
SQL shape. Min-depth (whichever path is shorter) is not a defensible tree-reading rule
for a Vietnamese gia phả: patrilineal reckoning follows the father's line by
convention, regardless of whether the mother's line to thủy tổ happens to be shorter.

## Decision

**Con theo đời cha** (the child follows the father's đời) is the single đời rule,
implemented by **one authority function**, `compute_generation_map(db, clan_id)`
(`backend/app/services/tree_builder.py`), that every consumer calls — no consumer may
compute đời independently again.

- **đời(thủy tổ) = 1.**
- For every other person X, the **canonical parent** is X's highest-priority parent
  **among those descended from the founder**, in this fixed priority order:
  1. father (male parent) — `relationship_type` **biological > adopted > step > foster**
  2. mother (female parent)
  3. unknown-gender parent
  — **`person_id` tiebreak** when priority is otherwise equal.
  A parent who is **not** reachable from the founder (a married-in spouse with no
  ancestry of their own in this clan) is never eligible as canonical and never
  captures the child's đời.
- **đời(X) = đời(canonical parent) + 1.**
- **Deterministic always** — the same graph always yields the same result,
  independent of row order, traversal order, or which endpoint asked.
- **No founder for the clan, or X disconnected from the founder → `generation` is
  `null`.** Clients must render "đời ?" honestly, never guess.

**One authority, every surface.** `GET /tree`, `GET /tree/subtree/{id}`,
`GET /tree/ancestors/{id}`, `GET /tree/focus/{id}`
(`app/application/tree/handlers.py::TreeQueryHandler`), and the clan export
(`ExportQueryPort.generation_map`,
`app/infrastructure/persistence/export_query_port.py`) all call
`compute_generation_map` (directly or via `TreeRepository.get_generation_map`) for the
same clan and read đời from its result — never from row depth, never independently.

**Both-parents rendering (pedigree collapse).** When a child has more than one
in-tree parent, the tree-shaped endpoints (`/tree`, `/tree/subtree`, `/tree/focus`)
render the child's **full node** once, under its **canonical parent**, and a
**`pedigree_collapse_ref` stub** — the SAME full node shape (every standard field:
names, HistoricalDates, avatar, generation, mother_id, …) with
`pedigree_collapse_ref: true` and `children`/`spouses` forced empty — under
**every other** in-tree parent, so no parent's branch silently loses a child,
without duplicating the full subtree under both parents. (One schema, no reduced
stub variant: clients render stubs exactly like any node and simply don't descend.)

## Consequences

- **All three surfaces now agree.** `/tree`, `/tree/focus`, and the export report the
  identical đời for the same person, always — the H4 family above now reports `4`
  everywhere, and `backend/tests/integration/test_doi_authority.py` pins this with
  real-DB fixtures for the asymmetric case, the symmetric-collapse case, the
  no-father-fallback-to-mother case, and the adoptive-father case.
- **GEDCOM đời notes follow theo-cha.** The GEDCOM export's structured NOTE
  (`doi=N`, see `rest-exports-api.md`) is fed by the same `generation_map`, so its
  `đời` value reflects con theo đời cha, not the old base-generation/min-depth
  behavior.
- **Pedigree-collapse rendering adds a field, but is NOT consequence-free for every
  client.** `pedigree_collapse_ref` is a new, default-`false` field on tree/focus
  child nodes — additive in the schema sense (existing clients that ignore unknown
  fields see no shape change). But the REAL caveat: a pedigree-collapsed child's
  person id now appears **more than once in the same payload** — once as the full
  node under its canonical parent, once (or more) as a `pedigree_collapse_ref` stub
  under every other in-tree parent (full-shape person nodes with `children`/`spouses`
  forced empty, not a reduced schema). Any renderer that de-duplicates elements or
  keys state by the **bare node id** (e.g. a `Map<id, Node>`, a "seen ids" `Set`, or
  a React key of just `id`) can silently drop the canonical subtree or collide two
  distinct render slots for the same id — it must key by `id` **plus its parent**
  (or otherwise exempt stubs from dedup) instead. The web tree canvas
  (`web/src/lib/utils/tree-transform.ts`) hit exactly this failure mode and was
  fixed in this same PR: it now only adds a node's id to its "visited" set when the
  node is NOT a stub, and gives each stub a synthetic id+parent React-Flow key so it
  never collides with (or masks) its canonical node.
- **`GET /persons/search` still reads the deprecated `clan_memberships.generation`
  column**, not this authority — a pre-existing gap (2026-07-18 review, Low #11,
  tracked for the lows remediation batch), not introduced or closed by this ADR. A
  person can therefore show a different đời on a search result than on `/tree`,
  `/tree/focus`, or the export for the exact same person until that endpoint is
  migrated to `compute_generation_map`.
- **Disconnected or undesignated-founder clans still get `null` đời** — con theo đời
  cha does not change the "no founder / unreachable → null, never guess" contract
  from ADR-012/ADR-026.
- **Per-request O(edges) computation.** `compute_generation_map` recomputes over the
  clan's `parent_child` edges on every call (no caching layer). This is acceptable at
  current clan sizes; a caching revisit is tracked as future work (remediation
  backlog item "B3"), not required by this ADR.
- **Two-pass topological implementation.** Because the canonical-parent choice is
  **static** (it depends only on each child's own fixed set of in-tree parents, never
  on any other node's đời), `compute_generation_map` splits into (1) a BFS from the
  founder to find the reachable set, and (2) a Kahn topological pass over that set
  that resolves each node's canonical parent and đời together, in dependency order —
  so a same-generation tie or an out-of-order visit can never silently pick the wrong
  parent or KeyError.
- **Adopted sons carry the line (con nuôi lập tự).** The father-priority list ranks
  `relationship_type` biological > adopted > step > foster, but adopted still
  outranks the mother — an adoptive father who is descended from the founder captures
  the child's đời over a biological mother with a shorter line, matching the
  Vietnamese custom of an adopted son continuing the patriline (`lập tự`). See
  `test_adoptive_father_carries_the_line`.

## Alternatives considered

- **Min-depth (shortest path to founder wins)** — rejected: this is what
  `/tree/focus` and the export already did, and it reckons đời through the **mother**
  whenever her line to thủy tổ happens to be shorter than the father's — directly
  contradicting the patrilineal convention a Vietnamese gia phả expects (cha's line
  determines đời regardless of length). It also gave no rule for the tree-rendering
  side (which parent's branch keeps the full node), leaving that to accidental SQL row
  order, which is exactly what caused the `/tree` vs `/tree/focus` disagreement in the
  first place.
- **Full-subtree duplication under both parents** — rejected: rendering a
  pedigree-collapsed child's **entire** subtree (all descendants, recursively) under
  every in-tree parent blows up combinatorially the moment collapse nests more than
  one generation deep (a collapsed descendant of a collapsed descendant duplicates
  again under each of ITS multiple parents, and so on), and produces a tree payload
  that no longer represents a tree at all — clients would need their own
  dedup/canonicalization logic to avoid double-counting persons. The
  `pedigree_collapse_ref` stub (full node once, minimal stub elsewhere) avoids both
  problems: bounded payload size, and a single canonical location for descent to
  continue from.
