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
- `clan_slug` (register + onboard, `clan_action=create`) must match
  `^[a-z0-9]+(-[a-z0-9]+)*$` — lowercase ASCII alphanumerics and single
  hyphens, max 100 chars; anything else is a 422. Clients slugify the clan
  name before submitting (the slug appears in URLs and export filenames).
- `POST /register` is **non-enumerating (ADR-021)**: it returns the identical
  201 body whether or not the email already has an account. Clan-input
  validation (`clan_id_required_for_join`, `clan_name_required_for_create`,
  `clan_slug_taken`, `clan_not_found`) runs unconditionally *before* the
  identity is created, so those 422/409/404 codes are still returned
  identically on both paths — only the account-existence signal itself
  (previously 409 `auth.email_already_exists`) is gone. An existing email
  gets a silent, best-effort password-reset/recovery email instead of an
  error; a fresh email proceeds through the normal create-and-verify flow.
  See [error-codes.md](error-codes.md) and
  [frontend-integration-guide.md](frontend-integration-guide.md).
- Login returns authenticated session/profile data for client bootstrap.
- A deactivated account (`is_active = false`) gets **403 `account_deactivated`**
  at login — no tokens, no profile data. See `auth-flow.md` and
  `error-codes.md`.
- `POST /refresh` is **not** gated on `is_active` (`AuthSessionService` is
  DB-free by design): the tokens it returns are unusable against a deactivated
  account because every authenticated request is gated at the
  `get_current_user` chokepoint (see `auth-flow.md`).
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

`POST /register` (201) — **uniform for both paths** (ADR-021: non-enumerating,
no `user_id`/`clan_id`/`is_approved`/`email` — the client always routes to a
"check your email" screen; real profile state arrives after verify + login):
```json
{ "data": { "message": "..." } }
```

`POST /onboard` (201) — **unchanged**, still the full profile shape (this is
an authenticated surface — attaching an already-logged-in user to a clan —
with no enumeration concern, so it kept `RegisterResponse`):
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
- `POST /register`'s response shape changed (ADR-021, 2026-07-14) from the
  full `RegisterResponse` to a uniform `{"message": ...}` envelope, taken as a
  breaking change deliberately accepted pre-frontend (no client consumed the
  old shape yet).
- Keep error envelopes and token semantics stable across client releases.
