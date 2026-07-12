# ADR-012: Graph-Computed đời + Derived đa thê Mother Attribution

## Status
Accepted (2026-07-11 contract freeze — shipped)

## Context
`clan_memberships.generation` was hand-entered and drifted from graph reality, while
different tree endpoints disagreed on where đời came from. Separately, đa thê
(polygamous) families need children grouped under the correct wife (vợ cả/hai/ba),
but `parent_child` has no explicit mother-of-this-marriage link.

## Decision
- **đời is always graph-computed** on every tree endpoint: thủy tổ = 1,
  `founder-distance + 1`; `null` when the node isn't descended from a founder.
  `clan_memberships.generation` is deprecated as a display source (column kept as
  data, not dropped).
- **Mother attribution is derived in the read-model**, not stored: a child's
  `mother_id` is its female parent among the clan's `parent_child` edges;
  `mother_spouse_order` comes from the (father, mother) marriage's `spouse_order`.
  `null` stays `null` — no guessing. No `parent_role`/`via_spouse_id` columns unless
  real data proves derivation lossy.

## Consequences
Easier: one đời authority (no drift, wrong hand-entered values self-heal); đa thê
grouping with zero migration; honest `null` semantics.
Harder: đời costs an extra ancestor lookup per tree request (bounded, batched);
mother derivation assumes ≤1 female-parent edge per child (last-seen wins otherwise).

Design detail: `docs/architecture/tree-read-model.md`.
