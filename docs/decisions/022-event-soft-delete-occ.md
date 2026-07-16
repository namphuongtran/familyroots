# ADR-022: Events — Soft Delete + Optimistic Concurrency + person FK SET NULL

## Status
Accepted, shipped (2026-07-17, migration 020)

## Context

Events (giỗ / death anniversaries, birthdays, ceremonies) were the one
aggregate left with **destructive delete and no concurrency guard**:

- `DELETE /events/{id}` hard-deleted the row. A misclick permanently
  destroyed a giỗ record — exactly the data-loss class ADR-019 eliminated
  for documents. Giỗ dates are core gia-phả heritage data.
- Events had no `version` column: concurrent PATCHes silently
  last-write-wins'd — the lost-update gap ADR-017 closed for
  persons/marriages/parent_child.
- `events.person_id` was `ON DELETE CASCADE`. The app never hard-deletes
  persons, but a manual `DELETE FROM persons` would silently cascade away
  every giỗ record referencing them (documents already use SET NULL for the
  same reason).

## Decision

Bring events into line with the platform's existing conventions (migration
`020_event_soft_delete_occ`):

1. **Soft delete with restore** — `is_deleted`/`deleted_at`/`deleted_by`
   columns; `DELETE` flags the row; new `POST /events/{id}/restore` brings it
   back (404 when not deleted). Every read path filters live rows: get, list,
   upcoming (solar CTE + lunar branch), the scheduler's two event queries,
   and the person timeline/events projections. Restore uses the same role as
   delete (**editor** — events are deliberately editor-deletable, unlike the
   admin-deletable aggregates; F-5 documented policy).
2. **Optimistic concurrency (ADR-017 contract)** — `version` column;
   `PATCH` requires `expected_version` (422 missing), stale → 409
   `stale_write` + `detail.current_version`, success echoes `version + 1`;
   delete/restore bump version unconditionally so a concurrent PATCH holding
   the old token conflicts.
3. **`events.person_id` → ON DELETE SET NULL** — a person hard-delete (which
   only a manual operation can perform) de-references, never destroys, the
   clan's event records.

## Consequences

- **Breaking (pre-golive)**: `PATCH /events/{id}` now requires
  `expected_version`; event responses carry `version` and `is_deleted`.
  Contract updated in `docs/contracts/rest-events-api.md`.
- No retention purge for events (unlike documents' 30-day blob purge —
  events have no storage cost worth reclaiming): a deleted giỗ record is
  recoverable indefinitely. Revisit only if soft-deleted rows ever become a
  volume problem.
- Clan exports (`SELECT *`) now include the soft-delete columns — archives
  remain lossless, consistent with ADR-020's flagged-soft-deleted persons.

## Alternatives considered

- **Keep hard delete, add an "are you sure" client contract** — rejected:
  ADR-019 already established that irreplaceable heritage data gets
  recoverable deletion at the storage layer, not UX-layer promises.
- **Admin-only delete instead of soft delete** — rejected: tightening the
  role does not fix destructiveness, and events are deliberately
  editor-managed (documented F-5 policy).
