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
- GET /me/users — viewer; cursor-paginated (`cursor`, `limit` 1–100)
- GET /me/users/pending — admin; cursor-paginated
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
- Adding new clan settings fields is non-breaking.
- Changing role semantics or approval flow is breaking.
- Keep membership and admin action envelopes stable for client handling.
