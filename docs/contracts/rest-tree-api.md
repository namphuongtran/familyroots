# Contract: tree-api

## Type
REST API

## Owner
backend

## Consumers
- web
- mobile

## Schema
Base route: /api/v1/tree

Core operations:
- GET /
- GET /subtree/{person_id}
- GET /ancestors/{person_id}
- GET /path?from_id=&to_id=
- GET /focus/{person_id} — documented separately in [tree-focus.md](tree-focus.md)

Query parameters:
- root_person_id — GET / only
- max_generations — GET / and GET /subtree/{person_id} (subtree default 5)
- profile (summary|detail|full) — all node-returning endpoints

Tree endpoints do NOT accept `fields` or `include` (those are person-list semantics).

Behavior:
- Returns graph-oriented responses for family tree exploration.
- Used by web tree visualization and mobile tree interactions.

## Node response shape
`GET /`, `GET /subtree/{person_id}` and `GET /ancestors/{person_id}` nodes carry, in
addition to the standard person/spouse fields:
- `mother_id` (str uuid | null) — the node's female parent (which wife), derived from
  this clan's `parent_child` edges. `null` when no mother edge is recorded for that
  child.
- `mother_spouse_order` (int | null) — that mother's `spouse_order` in her marriage to
  the father (đa thê "con bà cả/hai/ba"). `null` for the root node or when the
  mother/father pair has no matching marriage record.
- `mother_id`/`mother_spouse_order` are populated on `GET /` and `GET /subtree/{person_id}`
  tree nodes. `GET /ancestors/{person_id}` rows do **not** carry these fields (the
  ancestor chain has no per-edge mother concept).
- Assumption: at most one female-parent edge per child is expected; if data ever
  records more than one, the mother map keeps the last one seen (acceptable for this
  read-model, not enforced as a domain invariant here).
- `pedigree_collapse_ref` (bool, default `false`) — **additive**. On `GET /` and
  `GET /subtree/{person_id}` (not `GET /ancestors/{person_id}`), `true` marks a stub
  node: a child reachable from the founder via more than one in-tree parent renders
  its **full** node once, under its **canonical parent** (`pedigree_collapse_ref:
  false`/absent), and a stub under **every other** in-tree parent. A stub carries
  the SAME full node shape (all standard fields populated — names, dates, avatar,
  generation, mother_id, …) with `pedigree_collapse_ref: true` and `children: []`
  and `spouses: []` forced empty, so that parent's branch is never silently
  rendered childless and clients need no stub-specific null-guards — render it
  like any node, just don't descend. Stubs sort into `children` alongside real
  siblings (same birth_date/name key as the canonical node). See
  [tree-read-model.md](../architecture/tree-read-model.md#both-parents-rendering-pedigree-collapse)
  and [ADR-027](../decisions/027-doi-single-authority.md).

- `depth` (int) — **NOT** the node's nesting level in the response tree; it is a
  path-enumeration artifact of the underlying SQL traversal (`get_family_tree_flat`),
  carried over from whichever row the tree builder's row-dedup pass happened to see
  first for that person — which, because rows arrive ordered shallowest-first, is
  always that person's **shallowest** lineage path to the root, independent of where
  they end up nested. Nesting instead follows the đời-authority **canonical**
  parent (ADR-027), which can be a **longer** path than the shallowest one `depth`
  reports. Under pedigree collapse a node can therefore be nested one or more levels
  deeper in the response than its own `depth` value says, and — because
  `max_generations` bounds the SQL traversal's (shallowest) row depth, not the
  canonical nesting position — a node can end up nested deeper than
  `max_generations` in the rendered tree. Don't use `depth` to infer nesting level,
  row count, or generation; use `generation` for đời and count actual `children`
  nesting for rendering depth.
- A `pedigree_collapse_ref` stub's `children: []` and `spouses: []` are always
  forced empty — descent only continues from the canonical node. `has_more_descendants`
  (`GET /focus/{person_id}` only — see `tree-focus.md`) is **not** forced false on a
  stub: it is computed identically to any other boundary node, from whether the
  underlying person genuinely has children in the database, so a stub whose
  canonical mirror also lands at the descendant-depth boundary can legitimately
  report `has_more_descendants: true` even though its own `children` array is empty.

`generation` (đời) is graph-computed on `GET /`, `GET /subtree/{person_id}` and
`GET /ancestors/{person_id}` by a **single authority function**,
`compute_generation_map` (ADR-027): thủy tổ (clan founder) = 1; đời(X) = đời(canonical
parent) + 1, where the canonical parent is X's highest-priority in-tree parent
(father — biological > adopted > step > foster — then mother, then unknown-gender,
person_id tiebreak); `null` when the node isn't descended from a founder (or the clan
has no founder). It is **never** read from `clan_memberships.generation`, and never
computed independently per endpoint — `GET /`, `GET /subtree/{person_id}`,
`GET /ancestors/{person_id}`, `GET /focus/{person_id}` (see `tree-focus.md`) and the
clan export all read the SAME map for the same clan, so đời for a given person is
identical across every one of these surfaces (ADR-027 closes H4, where `/tree` and
`/tree/focus`/export previously disagreed on pedigree-collapsed persons).

## Versioning & Compatibility Rules
- Adding an optional field is schema-additive: `pedigree_collapse_ref` is one such
  addition, and existing clients that ignore unknown fields see no shape change.
  **But it is not consequence-free for every client**: a pedigree-collapsed child's
  person id now appears **more than once in the same payload** (the full node under
  its canonical parent, plus a `pedigree_collapse_ref` stub under every other
  in-tree parent — both full-shape person nodes with `children`/`spouses` empty on
  the stub, not a reduced schema). Any client that de-duplicates elements or keys
  state by the **bare node id** must instead key by `id` + parent (or otherwise
  exempt stubs from dedup), or it can silently drop the canonical subtree or
  collide two render slots for the same id. The web tree canvas
  (`web/src/lib/utils/tree-transform.ts`) hit exactly this and was fixed in this
  same PR — see ADR-027 Consequences for the failure mode and the fix.
- Changing node/edge identifiers or path semantics is breaking.
- Keep traversal responses compatible with visualization clients.
