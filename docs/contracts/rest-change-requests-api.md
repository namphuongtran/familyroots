# Contract: change-requests-api

## Type
REST API

## Owner
backend

## Consumers
- web
- mobile

## Schema

Base route: `/api/v1/change-requests`

A change request is a **proposal** to correct clan data, raised by a member who may
not be allowed to make the edit themselves. In practice a `viewer` reading the gia
phả spots a wrong birth date on an ancestor and reports it; a reviewer applies or
declines it.

**Scope of v1 (ADR-037): `action="update"` on `resource_type="person"` only.** The
request/response shapes already carry `action` and `resource_type`, and the stored
column set already covers create/delete and marriage / parent-child / event /
document, so widening the scope later is **additive** — no schema change, no contract
change, no new endpoint. Anything outside the executed combination returns
`422 change_request.unsupported_operation` today.

### Operations

| Method | Path | Role | Description |
|---|---|---|---|
| POST | `/change-requests` | viewer+ | Propose a correction (201) |
| GET | `/change-requests` | viewer+ | List — clan queue for reviewers, own proposals for viewers |
| GET | `/change-requests/{id}` | viewer+ | One proposal, with live target state |
| POST | `/change-requests/{id}/approve` | editor **or** admin | Apply the proposal and mark it approved |
| POST | `/change-requests/{id}/reject` | editor **or** admin | Decline it; the target is untouched |

All five are clan-scoped: they require `X-Current-Clan-Id` and act only within that
clan. A change request belongs to exactly one clan and is invisible, unfetchable and
unreviewable from any other — a cross-clan `GET`/`approve`/`reject` returns
`404 change_request_not_found`, never `403` (ADR-021: the queue is not an enumeration
oracle).

**Reviewer roles**: approve/reject accept **editor and admin**. An editor can already
make the identical edit unilaterally, so an admin-only gate would protect nothing and
would stall a clan whose single admin is busy. See ADR-037 and
[rbac.md](../architecture/rbac.md).

**Viewer read scoping**: a `viewer` sees only proposals they submitted, on both the
list and the detail endpoint. Editors and admins see the whole clan queue.

### `POST /change-requests` — request body

```json
{
  "action": "update",
  "resource_type": "person",
  "resource_id": "9b6cc869-0a10-491b-bfaa-b0eafb9cb857",
  "changes": { "birth_date": "1920-05-03", "birth_date_precision": "exact" },
  "note": "Gia phả cũ ghi năm Canh Thân"
}
```

- `action` / `resource_type` default to `"update"` / `"person"`.
- `resource_id` — required for `update`; the person being corrected. Must be a live
  (not soft-deleted) member of the acting clan, else `404 person_not_found`.
- `changes` — proposed field values. **Field names and value shapes are exactly the
  `PATCH /persons/{id}` body** minus `expected_version` (see
  [rest-persons-api.md](rest-persons-api.md)), and are validated by the same schema,
  so a client can render one form for both. Must be non-empty.
- `note` — optional free text from the requester (≤2000 chars).

> **`changes` keeps the WRITE date shape, not `HistoricalDate`.** Dates inside
> `changes` are the scalar `birth_date` + `birth_date_precision` +
> `birth_date_display` triple, **not** the `{date, precision, display, lunar}`
> response object used everywhere else (see
> [README.md — HistoricalDate](README.md#historicaldate-canonical-date-shape)). This
> is deliberate and is the one documented exception: `changes` is a *proposed request
> body*, not a rendered record. Wrapping it would mean a reviewer's client could not
> feed it straight back into `PATCH /persons/{id}` as a manual fallback. The `target`
> block's `conflicts` echo values in the same write shape for the same reason.

#### Proposable fields

`changes` accepts the person content fields — names, gender, birth/death dates with
precision and display, lunar dates, places, religion, nationality, occupation,
education, title, biography, notes.

**Not** proposable (`422 change_request.field_not_submittable`, `detail.fields` lists
the offenders):

- `phone`, `email` — contact PII. The `target` block echoes the record's *current*
  value for every proposed field, so allowing PII here would leak an ordinary
  member's contact details into the review queue, bypassing the redaction on the
  person read path. Contact details are not gia phả content.
- `avatar_url` — set by the document/avatar flow, not typed by a human.
- Anything the `Person` aggregate never allows (`created_by_clan_id`, `is_deleted`,
  audit columns), and any unknown field name. Unknown keys are **rejected**, never
  silently dropped.

### `GET /change-requests` — query params

| Param | Type | Default | Notes |
|---|---|---|---|
| `status` | `pending` \| `approved` \| `rejected` | — | Filter by review state |
| `cursor` | opaque string | — | From the previous page's `meta.cursor` |
| `limit` | int 1..100 | 20 | Page size |

Cursor-paginated `(created_at, id)` ASC — the single clan-facing pagination scheme
(ADR-010). A malformed cursor returns `400 invalid_cursor`.

### Response shape

Single resource (`POST`, `GET /{id}`, approve, reject):

```json
{
  "data": {
    "id": "ad78f9cf-c787-4396-9bc0-96175d92b866",
    "clan_id": "ef5a54f3-4d58-41ba-90b7-8ed9c037ea48",
    "requester_id": "d95c1ee7-ce5a-4982-8bd7-3d2a4e00bb30",
    "action": "update",
    "resource_type": "person",
    "resource_id": "9b6cc869-0a10-491b-bfaa-b0eafb9cb857",
    "changes": { "birth_date": "1920-05-03" },
    "note": "Gia phả cũ ghi năm Canh Thân",
    "status": "pending",
    "reviewed_by": null,
    "reviewed_at": null,
    "review_notes": null,
    "created_at": "2026-08-02T12:44:59.071608Z",
    "target": {
      "resource_type": "person",
      "resource_id": "9b6cc869-0a10-491b-bfaa-b0eafb9cb857",
      "exists": true,
      "is_deleted": false,
      "base_version": 1,
      "current_version": 3,
      "is_stale": true,
      "conflicts": [
        {
          "field": "birth_date",
          "base": "1919-01-01",
          "current": "1921-12-31",
          "proposed": "1920-05-03"
        }
      ]
    }
  }
}
```

`GET /change-requests` returns the same objects under `data` plus the standard
`meta: {cursor, has_more, limit}`.

### The `target` block — staleness, made visible

A proposal can sit for a week while somebody else edits the same person, so every
response carries the live state of what it points at. **The client must render this
before offering an Approve button.**

| Field | Meaning |
|---|---|
| `exists` | The target is still a member of this clan |
| `is_deleted` | The target is currently soft-deleted — approval will be refused |
| `base_version` | The target's `version` when the proposal was submitted |
| `current_version` | The target's `version` right now (`null` when `exists` is false) |
| `is_stale` | `current_version != base_version` — the record moved *somehow* |
| `conflicts` | The proposed fields that moved to a value that is **neither** what the requester saw **nor** what they proposed |

`is_stale: true` with `conflicts: []` is the normal, harmless case: somebody edited a
*different* field (or the record was deleted and restored). **Approval still
succeeds** and both edits survive. Only a non-empty `conflicts` blocks approval.

`conflicts` is computed for `pending` proposals only; on a reviewed one it is `[]`.

### Approval semantics

`POST /{id}/approve` applies the proposal through the ordinary person write path —
same aggregate, same field whitelist, same `death_date >= birth_date` invariant, same
`expected_version` conditional UPDATE (ADR-017) — and flips the status **in the same
transaction**. Consequences a client can rely on:

- A `200` means the target now holds the proposed values. There is no path where a
  reviewer is told "approved" and the data did not change.
- The target's `version` advances exactly as a `PATCH /persons/{id}` would, so any
  client holding the old version correctly sees `409 stale_write` on its next edit.
- Approval is **all-or-nothing**: if any proposed field conflicts, nothing is
  written — never a partly-applied proposal.
- Two audit-log rows are written: `change_request.approve` (actor: the reviewer) and
  `person.update` (actor: the reviewer — they authorized the write; the requester is
  recorded on the earlier `change_request.submit` row).

`POST /{id}/reject` has **no** target preconditions: a proposal against a deleted or
heavily-edited record must always be clearable out of the queue.

### Errors

Full detail shapes in [error-codes.md](error-codes.md).

| code | HTTP | when |
|---|---|---|
| `change_request_not_found` | 404 | Unknown id, another clan's, or a viewer asking for someone else's |
| `change_request.not_pending` | 409 | Approving/rejecting an already-reviewed proposal |
| `change_request.target_conflict` | 409 | A proposed field moved since submission |
| `change_request.target_deleted` | 409 | The target person is soft-deleted |
| `change_request.unsupported_operation` | 422 | Any `action`/`resource_type` outside `update`+`person` |
| `change_request.no_changes` | 422 | Empty `changes` |
| `change_request.field_not_submittable` | 422 | A non-proposable or unknown field name |
| `person_not_found` | 404 | Target person absent from the acting clan, or soft-deleted at submit time |
| `validation_error` | 422 | A malformed value in `changes`, or `resource_id` missing on an update |
| `stale_write` | 409 | A concurrent writer committed between the merge check and the write |
| `insufficient_permissions` | 403 | A viewer calling approve/reject |
| `invalid_cursor` | 400 | Malformed `cursor` |

### Recommended client flow on `change_request.target_conflict`

`detail.conflicts` carries `base` / `current` / `proposed` per field — enough to
render a side-by-side diff without another request. Offer the reviewer:

1. **Reject** the proposal (the newer value stands), or
2. Apply a merged value directly with `PATCH /persons/{id}`, then reject the
   proposal with a note. `changes` is already in the PATCH body shape, so this needs
   no reshaping.

There is deliberately no "force approve": overriding another member's edit is a
decision a person makes explicitly on the persons endpoint, not a flag on a queue.

## Versioning & Compatibility Rules

- Adding a new `resource_type` / `action` combination to the executed set is
  **additive and non-breaking**: the request and response shapes, the endpoints and
  the storage all already carry them. Clients that only submit person updates are
  unaffected.
- Adding fields to the proposable set is additive. **Removing** one is breaking —
  pending proposals referencing it would become unapprovable.
- Changing the merge rule (which movements block approval) is a **breaking behavioural
  change**: it changes when a reviewer sees `target_conflict`. It requires an ADR.
- The `target` block is part of the contract, not a debugging aid — clients gate the
  Approve affordance on `conflicts` and `is_deleted`.
- `changes` staying in the write date shape (not `HistoricalDate`) is a deliberate,
  frozen exception; changing it would break the PATCH-fallback flow above.
- Error `code` strings are frozen; see [error-codes.md](error-codes.md) versioning
  rules.
