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

`generation` (đời) is graph-computed on `GET /`, `GET /subtree/{person_id}` and
`GET /ancestors/{person_id}`: thủy tổ (clan founder) = 1, and `null` when the node
isn't descended from a founder (or the clan has no founder). It is computed from a
full ancestor-chain lookup, not read from `clan_memberships.generation` — that column
is no longer the display source for any tree endpoint.

## Versioning & Compatibility Rules
- Adding optional graph metadata is non-breaking.
- Changing node/edge identifiers or path semantics is breaking.
- Keep traversal responses compatible with visualization clients.
