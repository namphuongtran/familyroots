# Contract: clans-api

## Type
REST API

## Owner
backend

## Consumers
- web
- mobile

## Schema
Base route: /api/v1/clans

Core operations:
- GET /me — viewer; supports `?include=stats` (adds a nested `stats` object)
- PATCH /me — admin
- GET /me/users — viewer; cursor-paginated (`cursor`, `limit` 1–100) — see [User list rows](#user-list-rows) below
- GET /me/users/pending — admin; cursor-paginated — see [User list rows](#user-list-rows) below
- POST /me/users/{user_id}/approve — admin
- POST /me/users/{user_id}/reject — admin
- PATCH /me/users/{user_id}/role — admin; `role` is a **query parameter**, not a body field
- DELETE /me/users/{user_id} — admin
- PUT /me/founder — admin; designate or correct the clan's thủy tổ (founder) — see [Founder designation](#founder-designation-thủy-tổ) below

Behavior:
- All operations are scoped by X-Current-Clan-Id.
- Admin-only operations mutate clan membership and role state.
- Paginated lists return the standard `{"data", "meta": {cursor, has_more, limit}}` envelope.
- Response shapes should remain consistent with user-facing admin workflows.

### Clan info (`GET /me` and `PATCH /me`)

Both routes answer with the same object, the `clans` row (`ClanResponse`):

```jsonc
{
  "data": {
    "id": "uuid",
    "name": "string",
    "slug": "string",                     // identity, never editable through this API
    "description": "string|null",
    "origin_place": "string|null",
    "founded_year": 1750,                 // plain integer year or null, NOT a HistoricalDate
    "avatar_url": "string|null",
    "motto": "string|null",
    "ancestral_hall_location": "string|null",  // nhà thờ tổ
    "clan_rules": "string|null",               // gia huấn
    "is_active": true,                    // false = platform-suspended; every clan-scoped
                                          //   request then 403s with clan_suspended
    "created_at": "ISO-8601",
    "updated_at": "ISO-8601"
  }
}
```

`created_at` and `updated_at` are plain timestamps. The HistoricalDate rule in
[README.md](README.md) covers genealogy dates (birth, death, marriage, event); it does not
cover row audit timestamps, and `founded_year` is a year integer rather than a date.

`GET /me?include=stats` adds one nested object, and nothing else changes:

```jsonc
{ "data": { "...": "...", "stats": { "total_users": 0, "approved_users": 0,
                                     "pending_users": 0, "total_members": 0 } } }
```

**`PATCH /me` — admin.** The request body is a partial update. Exactly eight fields are
accepted, and every one is optional; an omitted field is left alone rather than blanked:

```jsonc
{
  "name": "string", "description": "string", "origin_place": "string",
  "founded_year": 1802, "avatar_url": "string", "motto": "string",
  "ancestral_hall_location": "string", "clan_rules": "string"
}
```

**The 200 body is the stored row after the write, not an echo of the request.** It carries
every field above plus `slug`, `is_active`, `created_at`, and a `updated_at` that has moved
to the time of this write. A client may use the response instead of re-fetching `GET /me`.

- `slug`, `is_active`, `id` and the timestamps are **not** editable here. A body naming any
  other field is rejected with **422 `field_not_updatable`**, `detail.field` naming the
  first offender, and **nothing is written** — the whole batch is validated before any
  field is applied.
- A PATCH that sets a field to the value it already holds is a valid **no-op**: 200, the
  same body, and `updated_at` unchanged.
- **403** — caller is not an approved clan admin.

Pinned by
`backend/tests/integration/test_clan_patch_returns_updated_row.py`, which reads the
response body against the stored row. Until 2026-08-26 this route answered **500** on every
PATCH that changed something, while writing the row anyway; a no-op PATCH
answered 200, so the failure only appeared on real edits.

### User list rows

The two user lists return **different row shapes**, because they have different guards.
The difference is deliberate and load-bearing — see
[ADR-039](../decisions/039-clan-user-list-identity-asymmetry.md).

**`GET /me/users` — viewer** (`ClanUserSummary`). Readable by every approved member of
the clan:

```jsonc
{
  "data": [
    {
      "id": "uuid",             // the user_clan_roles row id
      "user_id": "uuid",        // the account (user_profiles.id / Supabase auth sub)
      "role": "admin|editor|viewer",
      "person_id": "uuid|null", // linked person, null when the account isn't linked
      "display_name": "string|null", // user_profiles.display_name (nullable)
      "created_at": "ISO-8601"
    }
  ],
  "meta": { "cursor": "string|null", "has_more": false, "limit": 20 }
}
```

**`GET /me/users/pending` — admin** (`PendingClanUserSummary`). Same fields **plus
`email`**:

```jsonc
{
  "data": [
    {
      "id": "uuid",
      "user_id": "uuid",
      "role": "admin|editor|viewer",  // the role being requested
      "person_id": "uuid|null",       // null for a fresh registrant
      "display_name": "string|null",
      "email": "string|null",         // ADMIN-ONLY — see below
      "created_at": "ISO-8601"
    }
  ],
  "meta": { "cursor": "string|null", "has_more": false, "limit": 20 }
}
```

**`email` is on the pending queue only, and must stay that way.** `GET /me/users` is
`RequireViewer`, so an `email` field there would publish every member's login address to
the whole clan — the same exposure ADR-037 closed by keeping `phone`/`email` out of the
change-request review surface. The pending queue is `RequireAdmin`, the reader already
holds approve/reject/role powers, the decision it supports is an identity decision (approval
grants read access to hundreds of living relatives' records), and the address is the account
holder's own registration email rather than a genealogy record about a third party.

The key is **absent** from approved rows, not null. Clients must not assume the two rows are
the same type. Both `display_name` and `email` may be `null` — `user_profiles.display_name`
is nullable, and the profile join is a LEFT JOIN.

Pinned by
`backend/tests/integration/test_clan_users_identity_fields.py::test_email_is_on_pending_and_never_on_approved`.

### Last-admin invariant

A clan must always keep at least one approved admin. Both mutating endpoints below
enforce this under a `SELECT ... FOR UPDATE` lock on the clan's approved-admin rows
(`lock_admin_count`), so two concurrent requests that would both drop the clan to
zero admins serialize — exactly one succeeds, the other observes the post-commit
count and gets 403. The guard runs for **any** target, not just self-service:

- `PATCH /me/users/{user_id}/role` — demoting the clan's only approved admin away
  from `admin` (any target) → 403 `clan.last_admin_cannot_demote`.
- `DELETE /me/users/{user_id}` — removing the clan's only approved admin → 403
  `clan.last_admin_cannot_remove`. (Removing yourself is separately rejected with
  403 `clan.cannot_remove_self` regardless of admin count.)

See [error-codes.md](error-codes.md) for detail shapes and client handling.

### Founder designation (thủy tổ)

`PUT /clans/me/founder` — **admin only** (`RequireClanRole(["admin"])`) — designates
or corrects the clan's thủy tổ (founder), the person `GET /tree` roots at when no
`root_person_id` is given and the graph-computed đời (generation, ADR-012) is
anchored on (thủy tổ = đời 1). Full rationale and invariant in
[ADR-026](../decisions/026-single-founder-designation.md); read-model consequences
in [tree-read-model.md](../architecture/tree-read-model.md).

**Request:**
```jsonc
{ "person_id": "uuid" }
```

**Response `200`:**
```jsonc
{
  "data": {
    "person_id": "uuid",             // the newly-designated founder
    "previous_person_id": "uuid|null", // the prior founder, or null if none existed
    "message": "..."
  }
}
```

**Idempotency + swap semantics:**
- Re-designating the **current** founder is a no-op write: `previous_person_id`
  equals `person_id`, nothing changes in the database, and a `FounderDesignated`
  audit event still fires (idempotent request, not a no-op response).
- Designating a **different** person is a **swap**: the clan's existing founder
  membership (if any) is cleared and the target membership is set as founder in
  two explicitly ordered statements (`ClanRepository.swap_founder`), not left to
  ORM flush ordering — see ADR-026 for why. `previous_person_id` reports the
  founder that was displaced (`null` if the clan had none).
- A clan can have **exactly one live founder at a time** — enforced by the
  `uq_clan_memberships_one_founder` partial unique index (migration 023) as a DB
  backstop behind the swap, not just an application convention.

**Error cases:**
- **404 `person_not_found`** — `person_id` does not resolve to a live membership
  in the acting clan: the person doesn't exist, belongs to a different clan, or
  is soft-deleted. Same code as every other person-target lookup — see
  [error-codes.md](error-codes.md).
- **403** — caller is not an approved clan admin (standard RBAC rejection, see
  [rbac.md](../architecture/rbac.md)).
- **409 `conflict`** — lost the `uq_clan_memberships_one_founder` race against a
  concurrent designation (rare: two admins designating different persons at
  once). Standard generic-conflict envelope (SQLSTATE `23505` → 409); retry is
  safe — the client should refetch clan state and re-submit if the desired
  founder is still not designated.

**Onboarding consequence:** an undesignated clan (no `PUT /clans/me/founder`
call yet) makes `GET /tree` (no `root_person_id`) 404 with
`clan_founder_not_found` — this is the onboarding signal to prompt an admin to
designate a founder, not a broken-tree error state. See
[frontend-integration-guide.md](frontend-integration-guide.md) §5.1 and
[error-codes.md](error-codes.md#tree).

## Versioning & Compatibility Rules
- Adding new **clan info** fields to the `GET`/`PATCH /clans/me` body is non-breaking.
  "Clan info" is the `clans` row — name, slug, description, `origin_place`,
  `founded_year`, `motto`, `ancestral_hall_location`, `clan_rules`. **This has never meant
  a per-clan settings or preferences resource, and there is no such endpoint.** The
  `clan_settings` table that a reader might take this sentence to cover was dropped on
  2026-08-22 by [ADR-054](../decisions/054-clan-settings-table-is-dropped.md); no endpoint
  ever read or wrote it and no contract ever documented its shape. This wording was
  ambiguous until then, and the ambiguity is what ADR-054 removed.
- Changing role semantics or approval flow is breaking.
- Keep membership and admin action envelopes stable for client handling.
