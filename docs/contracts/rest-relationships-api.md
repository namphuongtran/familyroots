# Contract: relationships-api

## Type
REST API

## Owner
backend

## Consumers
- web
- mobile

## Schema
Base route: /api/v1/relationships

Marriage endpoints:
- POST /marriages
- GET /marriages/{id}
- PATCH /marriages/{id}
- DELETE /marriages/{id}

Parent-child endpoints:
- POST /parent-child
- GET /parent-child/{id}
- PATCH /parent-child/{id}
- DELETE /parent-child/{id}

Validation rules (current behavior):
- prevent self-loops
- prevent duplicate active marriage relationships
- max biological parent constraints
- age-gap and cycle checks for parent-child edges
- `person1_id`/`person2_id` (marriage) and `parent_id`/`child_id` (parent-child)
  must each resolve to a live (non-soft-deleted) member of the active clan on
  create — a soft-deleted person is rejected the same as a nonexistent one
  (404 `person_not_found`; M3, review 2026-07-18). These fields are immutable
  on `PATCH` (not in either edge's updatable-fields set), so the guard only
  needs to run at create time.
- `spouse_order` uniqueness is **per-person, orientation-independent**
  (ADR-029): no person may hold two live (`status <> divorced` — married,
  widowed, or separated) marriages at the same `spouse_order`, checked across
  **both** `person1_id` and `person2_id` — a husband's vợ cả/vợ hai/vợ ba can't
  be duplicated regardless of which side of a given marriage row he lands in
  (`relationship.duplicate_spouse_order`, 409) — checked on create, and on
  update when `spouse_order` is set or the effective `status` is non-divorced;
  backstopped by the (person1-keyed) partial unique index
  `uq_marriages_spouse_order` for same-orientation concurrent races. Accepted
  consequence: a person cannot be the same-rank spouse in two *simultaneous
  live* marriages, which over-rejects the rare polyandry / dual-live-household
  case — see ADR-029.
- `divorce_date ≥ marriage_date` is enforced on **both** create and update
  (ADR-029). Create rejects a violating payload with the standard 422
  `validation_error` (Pydantic cross-field validator). `PATCH
  /marriages/{id}` re-derives the effective `marriage_date`/`divorce_date`
  (from the PATCH body, falling back to the stored value for whichever date
  wasn't sent) and rejects `divorce_date < marriage_date` with 422
  `relationship.divorce_before_marriage` — a pre-write domain check, run
  before any DB round-trip.
- re-validation on update (ADR spec 2026-07-12, H2): a `PATCH` that changes
  `relationship_type` (parent-child) or flips `status` away from `divorced`
  (marriage) re-runs the same rules `create` enforces, excluding the edge being
  updated itself

Response shapes (see [Response envelope](README.md#response-envelope)):
- All endpoints return the resource under `data`
  (`{"data": {...}}`); `DELETE` endpoints return a message envelope
  (`{"data": {"message": "...", "id": "..."}}`).
- `POST /parent-child` (201) additionally returns an **optional** `meta.warning`
  when the link is created despite a non-fatal advisory (e.g. an unusual age
  gap) — omitted entirely when there's nothing to warn about:
  ```json
  { "data": { "id": "...", "parent_id": "...", "child_id": "...", "...": "..." },
    "meta": { "warning": "..." } }
  ```

### Optimistic concurrency (ADR-017)

- Every marriage and parent-child response (`GET /{id}` and the `PATCH` response)
  carries `"version": <int>` (≥1), bumped by 1 on every successful write to that
  row — including `DELETE`.
- `PATCH /marriages/{id}` and `PATCH /parent-child/{id}` both require a **required**
  body field `expected_version: int (>=1)` — the `version` value read from a prior
  `GET`/create/PATCH response for this same resource. Missing it → standard 422
  Pydantic validation error (`validation_error`).
- If `expected_version` no longer matches the row's current `version` → **409**
  with code `stale_write` and `detail: {"current_version": <int>}`. Client flow:
  reload the resource, re-apply the edit on top of the fresh data, resubmit with the
  new version. See [error-codes.md](error-codes.md) and
  [frontend-integration-guide.md §6.1](frontend-integration-guide.md#61-handling-409-stale_write-optimistic-concurrency-adr-017).
- `DELETE /marriages/{id}` and `DELETE /parent-child/{id}` do **not** require
  `expected_version` (soft-delete only) but still bump `version`.

## Versioning & Compatibility Rules
- Any rule tightening that can reject previously accepted writes is a behavior-breaking change.
- Document behavior-breaking changes in a new ADR and release notes.
- Keep response and error envelopes stable across versions.
