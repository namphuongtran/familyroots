# Contract: persons-api

## Type
REST API

## Owner
backend

## Consumers
- web
- mobile

## Schema
Base route: /api/v1/persons

Headers:
- Authorization: Bearer <jwt>
- X-Current-Clan-Id: <uuid>
- Accept-Language: vi|en|zh|fr

Core operations:
- GET /persons
  - Query params: cursor, limit, generation, gender, profile, fields, include
- GET /persons/search
  - Query params: q (required, min length 1), limit
- POST /persons
- POST /persons/batch
  - Body: ids (1–100), profile, include, fields, include_by_id (per-person include map)
- GET /persons/{id}
- PATCH /persons/{id}
- DELETE /persons/{id}
- POST /persons/{id}/restore
- POST /persons/{id}/claim
- GET /persons/{id}/marriages
- GET /persons/{id}/parent-child
- GET /persons/{id}/documents
- GET /persons/{id}/events
- GET /persons/{id}/timeline

Response shapes (see [Response envelope](README.md#response-envelope)):

`GET /persons` — cursor-paginated list. **No `total`** — `meta` carries the
cursor triplet only:
```json
{
  "data": [ { "id": "...", "full_name": "...", "...": "..." } ],
  "meta": { "cursor": "opaque-string-or-null", "has_more": false, "limit": 20 }
}
```

`POST /persons/batch` — always 200 even on partial failure; unresolved ids are
reported under `meta.errors`, never mixed into `data`:
```json
{
  "data": [ { "id": "...", "full_name": "...", "...": "..." } ],
  "meta": { "errors": [ { "id": "...", "code": "person_not_found" } ] }
}
```

`POST /persons/{id}/claim` (201):
```json
{ "data": { "id": "...", "status": "PENDING", "...": "..." } }
```

`POST /persons`, `GET /persons/{id}`, `PATCH /persons/{id}` — single resource
under `data`. `DELETE /persons/{id}`, `POST /persons/{id}/restore` — a message
envelope (`{"data": {"message": "...", "id": "..."}}`). `GET
/persons/{id}/{marriages,parent-child,documents,events,timeline}` — a plain
array under `data` (no `meta` — these are not cursor-paginated).

- NOTE: `created_by_clan_id` is **not** accepted on create/update — it is provenance,
  always stamped from the active clan (see the 2026-06-28 design review, C5).

### An edge is returned only when both of its persons are live (2026-08-22)

A relationship edge is hidden when the person on its other end is soft-deleted,
even though the edge row itself is not deleted. This applies to:

| Read | What it omits now |
|---|---|
| `GET /persons/{id}/marriages` | a marriage whose spouse is soft-deleted |
| `GET /persons/{id}/parent-child` | a link whose parent or child is soft-deleted |
| `POST /persons/batch`, `include=marriages` / `include=parent_child` | the same edges |
| `POST /persons/batch`, `include=stats` | those edges are not counted in `spouse_count` or `child_count` |

`GET /persons/{id}/timeline` and every tree endpoint already behaved this way.
Before this change the four reads above did not, so a client could be handed an
edge pointing at a person the same API answered `404` for, and a person card
could render `spouse_count: 2` for someone with one live spouse.

**What a client can rely on.** No list under `/persons` contains a person id
that `GET /persons/{that_id}` answers `404` for, and `stats` agrees with the
list it summarises. **Deleting a person is still soft and still reversible**:
`POST /persons/{id}/restore` brings the person back, and the edges reappear with
them, because the edge rows were never changed.

**What is not part of this.** Deleting the edge itself
(`DELETE /relationships/marriages/{marriage_id}`,
`DELETE /relationships/parent-child/{link_id}` — see
[rest-relationships-api.md](rest-relationships-api.md)) is a separate operation
and hides that one edge on its own. Nothing about the response schema changed:
`MarriageResponse` and `ParentChildResponse` carry the same fields as before.

### `phone` and `email` are redacted by role (ADR-049)

`phone` and `email` are the **only** two fields on a person whose value depends on who is
asking. Every other field, including names, dates, places, lineage, `occupation`, `religion`,
`biography` and `notes`, is the same for every member of the clan. The set is fixed: it is not
configurable per clan, per person, or per branch, and no endpoint changes it.

**Who gets the real value:**

| Caller | Sees `phone` and `email` of |
|---|---|
| `admin` of the active clan | every person in the clan |
| `editor` | their own linked person only |
| `viewer` | their own linked person only |
| a caller whose account is not linked to a person | nobody |

"Their own linked person" is the person the caller's account is linked to. A caller who has not
been linked yet, or whose claim is still pending, is in the last row.

**Everyone else gets `null`.**

**A `null` does not mean the person has no phone number.** This is the one thing a client has to
get right. The response carries **no** marker distinguishing "redacted because of your role" from
"this field is empty". Both are JSON `null`, both come back with `200`, and there is no `403` on a
per-field basis. That is deliberate: a marker would tell any member exactly which relatives have a
contact number on file, which is the same information the rule exists to protect. Three
consequences for a client:

- Do **not** render "chưa có số điện thoại" / "no phone number on file" from a `null`. Render the
  field as unavailable, not as absent.
- Do **not** cache a person read by one user and serve it to another. A cached `null` from a
  `viewer` would hide the number from an `admin`; a cached number from an `admin` would leak it.
  Key any person cache by the viewer, or do not cache these two fields.
- Do **not** treat a `null` as permission to write. `PATCH` with `phone: null` clears the stored
  value for real.

**Where the rule applies:**

| Route | Behaviour |
|---|---|
| `GET /persons` | redacted |
| `GET /persons/{id}` | redacted |
| `POST /persons/batch` | redacted |
| `PATCH /persons/{id}` | the echoed person in the response is redacted, so editing a stranger's record does not reveal their contact details |
| `POST /persons` | **not** redacted. The response echoes the values the creator just sent in the same request |
| `DELETE /persons/{id}`, `POST /persons/{id}/restore` | no person fields in the response at all |
| `GET /persons/search` | `PersonSearchResult` carries no contact field, for any caller |

The fields are declared only on the **full** person projection. `profile=summary` and
`profile=detail` never carry `phone` or `email`, whoever is asking. `profile=full` is the default,
and `fields=` cannot widen what the role allows: redaction runs before the projection is built, so
it cannot be bypassed through `profile`, `fields`, or `include`.

**Writing them is a separate rule, and it is narrower.** `PATCH /persons/{id}` accepts `phone` and
`email`. An `editor` or `admin` may write them on any person in the clan. A `viewer` may write them
on their **own** linked person only, and gets `403 field_not_updatable` otherwise.

**Two other surfaces, for completeness:**

- **Change requests never carry them.** `phone` and `email` are not proposable, so neither the
  proposal nor the `target` block that echoes current values can contain one. See
  [rest-change-requests-api.md](rest-change-requests-api.md).
- **The clan archive carries them unredacted.** `GET /exports/clan` is admin-only and returns both
  fields whole. See the PII note in [rest-exports-api.md](rest-exports-api.md).

### `avatar_url` is read-only (ADR-036) — **breaking for writers**

`avatar_url` is returned on every person projection (`PersonResponse`, `PersonSummary`,
`PersonMini`, `PersonDetail`, search results) and is **rejected on write**:

- `POST /persons` or `PATCH /persons/{id}` carrying an `avatar_url` key — any value,
  including `null` and `""` — returns **422** `validation_error` with
  `detail.fields` containing `body.avatar_url`. It is *not* silently ignored: a silent
  drop would leave a client believing it had set an avatar.
- This applies to every role. There is no admin or self-edit carve-out.

Set an avatar with **`PATCH /documents/{document_id}/set-avatar`** instead
([rest-documents-api.md](rest-documents-api.md)); that endpoint publishes the image and
returns the permanent URL, which is the same value subsequently echoed here.

The value is a **permanent, unauthenticated public URL** — no expiry, no token,
fetchable by anyone who has it, regardless of clan or login. Safe to cache and persist
on the client. Never construct or guess one; only ever render what the API returned.

Migration for clients that were writing this field: drop `avatar_url` from person
create/update payloads (leaving it in will now fail the whole request), and move the
avatar-setting UI onto the document upload → set-avatar flow.

### Optimistic concurrency (ADR-017)

- Every person response (`GET /persons/{id}`, list/search/batch items, and the
  `PATCH` response) carries `"version": <int>` (≥1), bumped by 1 on every successful
  write to that row — including `DELETE`/`restore`.
- `PATCH /persons/{id}` requires a **required** body field
  `expected_version: int (>=1)` — the `version` value read from a prior
  `GET`/create/PATCH response for this same person. Missing it → standard 422
  Pydantic validation error (`validation_error`).
- If `expected_version` no longer matches the row's current `version` (someone else
  updated/deleted/restored it since your last read) → **409** with code
  `stale_write` and `detail: {"current_version": <int>}`. Client flow: reload the
  person, re-apply the edit on top of the fresh data, resubmit with the new version.
  See [error-codes.md](error-codes.md) and
  [frontend-integration-guide.md §6.1](frontend-integration-guide.md#61-handling-409-stale_write-optimistic-concurrency-adr-017).
- `DELETE /persons/{id}` and `POST /persons/{id}/restore` do **not** require
  `expected_version` (delete/restore are role-gated, soft, and restorable — not the
  same lost-update risk as a field-level PATCH) — but they still bump `version`, so
  a PATCH racing against a delete/restore correctly gets `stale_write` instead of
  silently reverting it.

Example error shape:
{
  "error": {
    "code": "person_not_found",
    "message": "...",
    "detail": {
      "person_id": "..."
    }
  }
}

## Versioning & Compatibility Rules
- **2026-08-22 (seed S-053, ADR-049), documentation only, no change of any kind**: the
  `phone`/`email` redaction rule above has been in force since 2026-07-05 and was never
  written down here. Nothing about the API changed on this date. A client that assumed a
  `null` `phone` meant "no number on file" was wrong before this section existed and is
  wrong after it; the section says so out loud.
- **2026-08-22 (seed S-054), behaviour change, no schema change**: the four edge
  reads listed above stopped returning edges whose counterpart person is
  soft-deleted, and `spouse_count`/`child_count` stopped counting them. No field
  was added, removed, or renamed, so this is not breaking under the rules below.
  A client will notice one thing: a count can go **down** without any edge being
  deleted, and a list can lose a row it held before. That old row was a defect —
  it pointed at a person the same API answered `404` for — so there is no
  behaviour worth preserving and no compatibility period.
- **2026-08-02 (ADR-036), breaking for writers**: `avatar_url` moved from
  client-writable to server-managed; sending it on create/update is now a 422. It
  remains present and unchanged on every read. Shipped without a version bump because
  no backend code ever populated the field and its meaning was documented as undefined
  — there was no working write behaviour to preserve.
- Non-breaking: add optional fields, add new include profile values, add new optional query params.
- Breaking: remove/rename fields, change required headers, change error envelope.
- Breaking changes require either:
  - additive compatibility period, or
  - new versioned route and migration notice in docs/decisions.
