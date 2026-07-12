# Contract: auth-api

## Type
REST API

## Owner
backend

## Consumers
- web
- mobile

## Schema
Base route: /api/v1/auth

Core operations:
- POST /register
- POST /onboard (201 — create clan + first admin for an already-authenticated user)
- POST /login
- POST /logout
- POST /refresh
- POST /forgot-password
- POST /resend-verification
- GET /me
- PATCH /me (updates full_name and preferred_locale)
- POST /me/fcm-token
- DELETE /me/fcm-token

Request/response expectations:
- Bearer JWT is required after login.
- Register can either join an existing clan or create a new clan.
- Login returns authenticated session/profile data for client bootstrap.
- **Email verification**: register creates the identity unconfirmed and sends a
  verification email best-effort. Login with an unconfirmed email fails with
  **403 `email_not_verified`** (not 401 — credentials were correct). Clients should
  offer "resend verification" on that error.
- `POST /resend-verification` is 200 always (non-enumerating — same message whether
  or not the email exists); body `{"email": ...}`.
- FCM token endpoints are used by mobile and any push-enabled clients.
- `POST /forgot-password` is 200 always (non-enumerating); triggers a Supabase
  recovery email. Reset **completion is client-side**: the email link opens the
  web/mobile app with a `token_hash`/`type=recovery`; the client calls the Supabase
  SDK `verify_otp({type:'recovery', token_hash})` then `update_user({password})`.
  The backend has no `reset-password` endpoint by design.

Response shapes (all 2xx bodies are `{"data": ...}` — see
[Response envelope](README.md#response-envelope)):

`POST /register` (201) / `POST /onboard` (201):
```json
{
  "data": {
    "user_id": "...", "email": "...", "full_name": "...",
    "clan_id": "...", "is_approved": false, "message": "..."
  }
}
```

`POST /login` — tokens plus a **nested** `user` profile object:
```json
{
  "data": {
    "access_token": "...", "refresh_token": "...", "expires_in": 3600,
    "user": {
      "id": "...", "email": "...", "full_name": "...",
      "clan_id": "...", "clan_name": "...", "role": "...",
      "is_approved": true, "has_pending_membership": false,
      "person_id": "...", "preferred_locale": "vi"
    }
  }
}
```

`POST /refresh` — **tokens only**, no `user`:
```json
{ "data": { "access_token": "...", "refresh_token": "...", "expires_in": 3600 } }
```

`POST /logout`, `PATCH /me`, `POST /me/fcm-token`, `DELETE /me/fcm-token`,
`POST /forgot-password`, `POST /resend-verification` — a message envelope:
```json
{ "data": { "message": "..." } }
```

`GET /me` — the profile object directly under `data` (same shape as `login`'s
nested `user`):
```json
{ "data": { "id": "...", "email": "...", "full_name": "...", "...": "..." } }
```

## Versioning & Compatibility Rules
- Adding optional auth/profile fields is non-breaking.
- Changing login/register payload requirements is breaking.
- Keep error envelopes and token semantics stable across client releases.
