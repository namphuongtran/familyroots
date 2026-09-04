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
- **`parent_too_young` is precision-gated (ADR-011; M5, review 2026-07-18):** a
  biological parent-child edge with a computed age gap <12 years is a hard
  **422** `relationship.parent_too_young` only when **both** the parent's and
  child's birth dates have `precision == "exact"`. If either birth date is an
  estimate (`year`, `month`, `circa`, or `unknown`), the same <12y gap does
  **not** block the write — the edge is created and the response carries a
  non-fatal `meta.warning` instead, because an estimated date can't justify a
  hard block. The **>80y age-gap advisory** (`meta.warning`, never a hard
  error) and **cycle detection** (`relationship.creates_cycle`, always a hard
  422) both still run independently of this precision gate — cycle detection
  in particular is unconditional: it is checked even when the age check only
  produced a warning (a prior bug where the >80y-warning path skipped cycle
  detection entirely was fixed as part of M5; see
  [domain-rules.md](../architecture/domain-rules.md#relationship-rules)).
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

Read visibility (2026-08-22; [ADR-051](../decisions/051-edge-visibility-derived-not-cascaded.md)):
- `GET /marriages/{id}` and `GET /parent-child/{id}` answer **404**
  (`marriage_not_found` / `parent_child_not_found`) when the edge row is
  soft-deleted **or** when either person it points at is soft-deleted. The second
  half is derived at read time: nothing cascades a person's delete onto its edge
  rows, so the edge keeps `is_deleted: false` and is hidden anyway. This matches
  the four edge reads under `/persons` (see
  [rest-persons-api.md](rest-persons-api.md)) and the tree.
- **`PATCH` and `DELETE` on the same id still succeed.** An admin must be able to
  repair or remove an edge whose endpoint person was deleted, so the write paths
  do not carry the second predicate. A client that holds an edge id can therefore
  get `404` from `GET` and `200` from `DELETE` for that id, and that is deliberate.
- Restoring the person (clearing `is_deleted`) makes the same `GET` answer `200`
  again. No edge data is lost while the person is deleted.

Response shapes (see [Response envelope](README.md#response-envelope)):
- All endpoints return the resource under `data`
  (`{"data": {...}}`); `DELETE` endpoints return a message envelope
  (`{"data": {"message": "...", "id": "..."}}`).
- `POST /parent-child` (201) additionally returns an **optional** `meta.warning`
  when the link is created despite a non-fatal advisory (e.g. an unusually
  large >80y age gap, or a <12y biological age gap where either birth date is
  not `precision == "exact"` — see the `parent_too_young` precision gate
  above) — omitted entirely when there's nothing to warn about:
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
- **2026-08-22, behaviour change, no schema change**: `GET
  /marriages/{id}` and `GET /parent-child/{id}` began answering `404` for an edge
  whose endpoint person is soft-deleted. No field was added, removed, or renamed.
  A client will notice one thing: an id that returned `200` can now return `404`
  without the edge being deleted. That old `200` was a defect — it handed back an
  edge naming a person the same API answered `404` for — so there is no behaviour
  worth preserving and no compatibility period. `PATCH` and `DELETE` on that id
  are unchanged, on purpose.
- Any rule tightening that can reject previously accepted writes is a behavior-breaking change.
- Document behavior-breaking changes in a new ADR and release notes.
- Keep response and error envelopes stable across versions.
