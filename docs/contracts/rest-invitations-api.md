# Contract: invitations-api

## Type
REST API

## Owner
backend

## Consumers
- web
- mobile

## Schema
Two surfaces: a clan-admin surface (manage invitations) and an invitee surface
(accept an invitation). See ADR-007 (identity-claims workflow) for how invitations
coexist with self-request-join.

Headers:
- Authorization: Bearer <jwt>
- X-Current-Clan-Id: <uuid> (admin surface)
- Accept-Language: vi|en|zh|fr

### Admin surface — base route: /api/v1/clans/{clan_id}/invitations

| Method | Path                                   | Min role | Notes |
|--------|----------------------------------------|----------|-------|
| POST   | `/clans/{clan_id}/invitations`         | admin    | Create an email-targeted invitation (201) |
| GET    | `/clans/{clan_id}/invitations`         | admin    | List the clan's invitations |
| DELETE | `/clans/{clan_id}/invitations/{id}`    | admin    | Revoke (204 No Content) |

- The path `{clan_id}` **must equal** the active `X-Current-Clan-Id`, else
  403 `clan_context_mismatch` (the guard fires before the handler).
- A **live** pending invitation is unique per `(clan_id, email)` (partial unique
  index); creating a second one while the first is still valid surfaces
  `invitation.pending_exists` (409).
- **Re-inviting after expiry works** (M11): a pending invitation whose `expires_at`
  has passed is lazily transitioned to `expired` on the next create for that
  `(clan_id, email)`, and the new invitation is issued with a fresh `token`/`expires_at`.
  Expiry is realized lazily on re-invite (no background sweep) and emits no event; the
  timed-out row remains as `expired` history. Only a *still-valid* pending invite blocks.
- The invitation `token` is a ~256-bit `secrets.token_urlsafe(32)` value.
- **`status` on a list row is DERIVED at read time, not the stored column**.
  Because expiry is realized lazily (previous bullet), a timed-out invitation keeps
  `status = 'pending'` in storage until somebody re-invites that email — possibly
  forever. Reporting the stored value made the list say `pending` for a link `accept`
  already refuses, so the read computes the field instead:
  - a stored `pending` whose `expires_at` has passed is reported as **`expired`**;
  - `accepted`, `revoked`, and an already-stored `expired` are reported **verbatim**,
    however long ago `expires_at` passed. They record an act, not a deadline.
  The comparison is strict (`expires_at < now`, UTC) and is **the same predicate
  `accept` refuses on**, so a row this endpoint calls `pending` is a row `accept` will
  still take. Nothing else in the row is derived. The stored column is unchanged by a
  read; a client that wants the raw lifecycle value cannot get it from this API.
- **`status` appears in exactly one response: the list row.** There is no
  per-invitation detail route, and the 201 create body carries no `status` — a freshly
  created invitation is always pending.
- Clients may keep deriving the row state from `expires_at` themselves; the server now
  reaches the same answer, so the two agree rather than compete.

### Invitee surface — base route: /api/v1/invitations

| Method | Path                          | Auth | Notes |
|--------|-------------------------------|------|-------|
| POST   | `/invitations/{token}/accept` | Yes  | Accept; grants the invited clan role |

- Accept verifies the authenticated user's email matches the invited email
  (case-insensitive) — `invitation.email_mismatch` otherwise — preventing token
  forwarding to a different account.
- Accept fails closed on a non-pending/expired/already-member invitation
  (`invitation.not_pending` / `invitation.expired` / `invitation.already_member`).
- Invitation create/accept/revoke emit auditable domain events → `audit_logs` rows.
- **The invitee surface takes no `X-Current-Clan-Id`, and cannot.** The invitee is not a
  member of the clan yet, so there is no clan for them to select. Sending the header has no
  effect on this route. The token is the authorization: it is the only thing that decides
  which clan the caller is granted a role in. Nothing here changed with
  [ADR-048](../decisions/048-invitation-accept-runs-on-the-system-session.md) — the request,
  the response and the error codes are identical — but ADR-048 is where the reason is
  written down, along with what that costs at the database layer.

Response shapes (see [Response envelope](README.md#response-envelope)):

`POST /clans/{clan_id}/invitations` (201):
```json
{ "data": { "id": "...", "email": "...", "role": "...", "token": "...", "expires_at": "...", "accept_path": "..." } }
```

`GET /clans/{clan_id}/invitations` — plain array under `data` (no `meta` — not
cursor-paginated). Fields: `id`, `clan_id`, `email`, `role`, `status`, `expires_at`,
`accepted_at`, `created_at`. `status` is one of `pending` | `accepted` | `revoked` |
`expired` and is **derived** — see the admin-surface bullets above:
```json
{ "data": [ { "id": "...", "clan_id": "...", "email": "...", "role": "...", "status": "expired", "expires_at": "...", "accepted_at": null, "created_at": "..." } ] }
```

`POST /invitations/{token}/accept`:
```json
{ "data": { "clan_id": "...", "role": "...", "message": "..." } }
```

`DELETE /clans/{clan_id}/invitations/{id}` — 204 No Content, no body.

Error envelope: standard `{ "error": { "code", "message", "detail" } }`.

## Versioning & Compatibility Rules
- Non-breaking: add optional invitation metadata, add optional query params.
- Breaking: change the token scheme, the email-match rule, the role-grant semantics,
  or the error envelope.
- Deriving `status` changed no field name and no type. It changed the **value**
  a timed-out row reports, from `pending` to `expired` — which is the defect it fixed,
  and matches what a client was already told to compute for itself. A client that
  counted `status == "pending"` rows now gets a smaller, truthful count.
