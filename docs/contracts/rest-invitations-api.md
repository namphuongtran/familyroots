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
- A pending invitation is unique per `(clan_id, email)` (partial unique index);
  a duplicate create surfaces `invitation.pending_exists` (409).
- The invitation `token` is a ~256-bit `secrets.token_urlsafe(32)` value.

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

Error envelope: standard `{ "error": { "code", "message", "detail" } }`.

## Versioning & Compatibility Rules
- Non-breaking: add optional invitation metadata, add optional query params.
- Breaking: change the token scheme, the email-match rule, the role-grant semantics,
  or the error envelope.
