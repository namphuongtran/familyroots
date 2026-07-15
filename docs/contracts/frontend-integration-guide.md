# Frontend Integration Guide (web + mobile)

## Type
Integration guide (cross-cutting; complements the per-surface `rest-*-api.md` contracts)

## Owner
backend

## Consumers
- web (Next.js 16 / React 19)
- mobile (Flutter / Dio)

Every claim below is verified against backend code as of 2026-07-12 (files cited per
section). Where the backend leaves something genuinely undefined it is marked
**⚠️ UNDEFINED — needs backend decision** instead of guessed at.

---

## 1. Bootstrap sequence

Code: `app/api/v1/auth.py`, `app/application/auth/handlers.py`, `app/api/v1/me.py`,
`app/core/security.py` (`get_current_clan_id`), `app/middleware/language_middleware.py`.

### 1.1 Login

`POST /api/v1/auth/login` `{"email", "password"}` →

```json
{
  "data": {
    "access_token": "...", "refresh_token": "...", "expires_in": 3600,
    "user": {
      "id": "...", "email": "...", "full_name": "...",
      "clan_id": "...|null", "clan_name": "...|null", "role": "...|null",
      "is_approved": false, "has_pending_membership": false,
      "person_id": "...|null", "preferred_locale": "vi"
    }
  }
}
```

Persist: `access_token`, `refresh_token`, `expires_in`, and the nested `user` object.
Field semantics (from `AuthCommandHandler.login` + `auth_repository.get_login_profile`):

- `clan_id`/`clan_name` reflect **one** membership row, *including a pending one*
  (the login query does not filter on `is_approved`).
- `role` is non-null **only when that membership is approved** — a pending member gets
  `role: null`.
- `is_approved` — whether that membership is approved.
- `person_id` — the person record linked to the user (identity claim), or null.
- **⚠️ `has_pending_membership` is always `false` in the login response** — the login
  handler never computes it (only `GET /auth/me` does). Call `GET /auth/me` right after
  login and use *that* value for routing to the pending screen.
- **⚠️ `preferred_locale` is always the default `"vi"` in login and `GET /auth/me`
  responses** — the backend never populates it from Supabase `user_metadata`, even
  after a successful `PATCH /auth/me`. Until fixed, read the user's locale from the
  Supabase session (`user_metadata.preferred_locale`) or your own storage, not from
  this field. (Backend gap; `PATCH /auth/me` *does* persist the value server-side.)
- **⚠️ Multi-clan users**: the login profile query is `LIMIT 1` with no `ORDER BY`, so
  *which* membership appears as `user.clan_id` is **UNDEFINED — needs backend
  decision**. Do not use `user.clan_id` as the active clan for multi-clan users; use
  the clan-resolution flow below.

`GET /auth/me` returns the same profile shape directly under `data`, but joined on
**approved** memberships only, and with a real `has_pending_membership`.

### 1.2 Clan resolution

1. `GET /api/v1/me/clans` → `{"data": [{clan_id, clan_name, clan_slug, role,
   joined_at}], "meta": {"count": N}}` — **approved memberships only** (pending ones
   are never listed).
2. If `count == 1`: you may skip explicit selection — the backend auto-selects.
3. If `count > 1`: let the user pick; optionally validate with
   `POST /api/v1/me/clans/{clan_id}/select` (echoes the clan context, 403
   `clan_membership_required` if not an approved member). Selection is **not** stored
   server-side — the client must persist the choice and send it as a header.

`X-Current-Clan-Id` header rules, exactly as implemented in `get_current_clan_id`:

| Situation | Result |
|---|---|
| Header sent, user approved in that clan | that clan is active |
| Header sent, malformed UUID | 400 `invalid_clan_id_format` |
| Header sent, not an approved member | 403 `clan_membership_required` |
| No header, exactly 1 approved clan | auto-selected (header optional) |
| No header, multiple approved clans | 400 `multiple_clans_no_selection` |
| No approved membership at all | 403 `no_approved_clan_membership` |
| Clan suspended (`clans.is_active = false`) | 403 `clan_suspended` |
| Account deactivated (`user_profiles.is_active = false`) | 403 `account_deactivated` |

Recommendation: always send the header once a clan is chosen, even for single-clan
users — it makes client behavior deterministic if the user later joins a second clan.

### 1.3 Per-request headers

Every API request after login:

- `Authorization: Bearer <access_token>`
- `Accept-Language: vi|en|zh|fr` — the backend takes the **first language tag's first
  two letters**; anything unsupported falls back to `vi`
  (`language_middleware.py`). This drives all server-localized text (§9).
- `X-Current-Clan-Id: <uuid>` — on clan-scoped routes (persons, tree, events,
  documents, relationships, branches, claims, clan admin).

Web reference implementation: `web/src/lib/api/axios.ts` attaches all three via a
request interceptor; the clan id resolves through `getRequestContext()`
(`web/src/infrastructure/http/request-context.ts`). Mobile: the Dio
`auth_interceptor.dart` is still a scaffold (see `mobile/CLAUDE.md`) — implement the
same three headers there.

---

## 2. Token lifecycle

Code: `app/application/auth/handlers.py` (`AuthSessionService`),
`app/infrastructure/supabase_identity_provider.py`, `web/src/lib/api/axios.ts`,
`web/src/middleware.ts`.

- Tokens are Supabase-issued JWTs. `expires_in` is whatever Supabase returns
  (seconds; **3600** with the default Supabase JWT expiry). The backend keeps no
  session state; it validates the JWT per request against Supabase JWKS.
- `POST /api/v1/auth/refresh` `{"refresh_token"}` →
  `{"data": {"access_token", "refresh_token", "expires_in"}}` (tokens only, no
  `user`). **Persist the new `refresh_token`** — Supabase rotates it. Failure → 401
  `auth.invalid_refresh_token`.
- `POST /api/v1/auth/logout` (Bearer required) revokes the session server-side
  (Supabase admin `sign_out(..., "global")`, best-effort). The stateless access token
  **remains valid until it expires** — treat logout as "stop renewing", and clear all
  client state anyway.

### Recommended refresh strategy (mobile / any non-Supabase-SDK client)

Reactive, single-flight: on a 401 from any API call, run **one** shared refresh
(`POST /auth/refresh`), queue concurrent 401s behind it, retry the failed request once
with the new token; if the refresh itself fails, sign out and route to login. Never
refresh in a loop.

### What web actually does today (`axios.ts`)

The web client does **not** call `POST /auth/refresh`. It delegates token lifetime to
the Supabase JS SDK: the request interceptor reads
`supabase.auth.getSession()` (the SDK auto-refreshes proactively), and the response
interceptor treats any 401 as terminal — `supabase.auth.signOut()` + redirect to
`/{locale}/login`. That is a valid variant of "refresh-then-signout" because the SDK
performs the refresh before the request; a client without the Supabase SDK must
implement the reactive single-flight strategy above itself.

### Storage guidance

- **Web**: session lives in Supabase SSR cookies (`@supabase/ssr`) so
  `web/src/middleware.ts` can gate protected routes server-side; client-side app
  state (profile, current clan, memberships) lives in the persisted Zustand store
  (`web/src/store/auth.store.ts` — persists non-sensitive fields only). Do not
  duplicate tokens into localStorage.
- **Mobile**: use `supabase_flutter` session management, or if storing backend-issued
  tokens manually, use platform secure storage (iOS Keychain / Android Keystore) —
  never plain shared preferences/Hive for tokens.

---

## 3. Email-verification landing flow

Code: `app/infrastructure/supabase_identity_provider.py`
(`create_user`, `send_verification_email`), `app/core/config.py`, ADR-015,
ADR-021, `docs/architecture/auth-flow.md`.

### 3.0 Register is non-enumerating (ADR-021, 2026-07-14)

`POST /auth/register` returns the **same 201 body for every call that passes
clan-input validation**, regardless of whether the email already has an
account:

```json
201 { "data": { "message": "..." } }
```

**There is no `409`-on-duplicate-email anymore** — that behavior (and the
`auth.email_already_exists` code) is gone. The client cannot and must not
try to distinguish "new account" from "email already registered" from this
response. **Always route to a "check your email" screen** after a successful
`201`:

- If the email was new, a verification email is on its way (§3 below).
- If the email already had an account, the user silently receives a
  password-reset/recovery email instead — from the user's point of view this
  looks the same ("check your email"), which is the point: the endpoint no
  longer confirms which case applies.

Clan-input errors (bad/missing `clan_id`, `clan_name`/`clan_slug`, an
already-taken slug, a nonexistent clan) still surface as normal 422/409/404
errors with their existing codes (`auth.clan_id_required_for_join`,
`auth.clan_name_required_for_create`, `auth.clan_slug_taken`,
`clan_not_found`) and should be handled as ordinary form-validation errors —
these are not account-existence signals.

`POST /auth/onboard` (already-authenticated users attaching to a clan) is
**unchanged** and still returns the full profile-shaped response
(`user_id`/`email`/`clan_id`/`is_approved`/`message`).

What the backend does for the underlying email delivery (verified):

- `POST /auth/register` creates the Supabase user **unconfirmed**
  (`email_confirm: False`) and then sends the verification email best-effort via the
  anon client: `auth.resend({"type": "signup", "email": ...,
  "options": {"email_redirect_to": EMAIL_VERIFY_REDIRECT_URL}})`.
  `email_redirect_to` is only passed when `EMAIL_VERIFY_REDIRECT_URL` is configured;
  when empty, **Supabase falls back to the project's Site URL**.
- `POST /auth/resend-verification` `{"email"}` sends the same email; always 200 with
  the same message (non-enumerating).
- Logging in before verifying → **403 `email_not_verified`** (not 401) — show a
  "resend verification" screen on that code.

What the client receives on the landing URL: the backend never sees this leg — it is
Supabase → user's mailbox → client. Per Supabase's confirm-signup email flow the link
lands on your redirect URL with `token_hash` and `type=signup` (or `type=email`)
query params, and the client completes verification with the Supabase SDK:

```ts
// web (supabase-js)
await supabase.auth.verifyOtp({ type: 'signup', token_hash })
```
```dart
// mobile (supabase_flutter)
await supabase.auth.verifyOTP(type: OtpType.signup, tokenHash: tokenHash);
```

On success, route to login and have the user sign in through
`POST /api/v1/auth/login` so the client gets the backend profile bootstrap (§1).

**⚠️ VERIFY WITH SUPABASE DOCS**: the exact landing-URL parameter names
(`token_hash` + `type` vs. a PKCE `?code=` param) depend on the Supabase project's
email-template and flow configuration and are **not verifiable from this repo**.
Note that the web app already has a PKCE handler at
`web/src/app/api/auth/callback/route.ts` (`exchangeCodeForSession(code)`), so if the
project is configured for the PKCE flow the confirmation link should point there
instead. Pin down the project's Supabase email template before shipping this screen.

---

## 4. Password-reset landing flow

Code: `app/api/v1/auth.py` (`forgot_password`),
`supabase_identity_provider.py` (`send_password_reset`), `rest-auth-api.md`.

1. `POST /api/v1/auth/forgot-password` `{"email"}` — always 200 with the same message
   (non-enumerating; provider failures are swallowed). Sends a Supabase recovery
   email with `redirect_to = PASSWORD_RESET_REDIRECT_URL` when configured (else the
   Supabase Site URL).
2. The email link opens the client with `token_hash` / `type=recovery`.
3. The client completes the reset **entirely via the Supabase SDK** — the backend has
   no reset-password endpoint by design:

```ts
await supabase.auth.verifyOtp({ type: 'recovery', token_hash })
await supabase.auth.updateUser({ password: newPassword })
```

4. Route to login.

The same **⚠️ VERIFY WITH SUPABASE DOCS** caveat from §3 applies to the exact link
parameter format (token-hash vs PKCE code), which depends on Supabase project config.

---

## 5. Pending-approval state

Code: route dependencies in `app/api/v1/{auth,me,invitations}.py`,
`app/core/security.py`, `app/core/permissions.py`.

A user with a valid (verified) login but `is_approved = false` — i.e. their join
request awaits a clan admin — **can** call anything gated only by `get_current_user`
(a valid JWT):

- `GET /auth/me`, `PATCH /auth/me` (profile + locale)
- `POST /auth/logout`, `POST /auth/me/fcm-token`, `DELETE /auth/me/fcm-token`
- `POST /auth/onboard` (join another clan / create their own clan)
- `POST /api/v1/invitations/{token}/accept` — verified: this route depends on
  `get_current_user` only, no role or approval check
- `GET /me/clans` — works, but returns **approved memberships only**, so it is empty
  for a purely-pending user
- `POST /me/clans/{clan_id}/select` — 403 `clan_membership_required` until approved

Everything clan-scoped (persons, tree, events, documents, …) fails with
403 `no_approved_clan_membership` (from `get_current_clan_id`).

Client routing rule: after login call `GET /auth/me`; if `is_approved` is false and
`has_pending_membership` is true → pending-approval screen (web:
`/{locale}/pending-approval`). If both are false and `clan_id` is null → onboarding
(`POST /auth/onboard`). Do **not** rely on the login response's
`has_pending_membership` (§1.1 caveat).

---

## 6. Error handling

Canonical error catalog: [error-codes.md](error-codes.md) — the single source for
code values, HTTP status, `detail` shape, and per-code client handling; this section
only defines global interceptor behavior.

Envelope, every non-2xx JSON body (`app/core/exceptions.py`):

```json
{ "error": { "code": "stable_machine_code", "message": "localized text", "detail": { } } }
```

`message` is localized server-side from `Accept-Language`; `code` is stable — switch
on `code`, display `message`.

Global interceptor rules:

- **401** → single-flight refresh once (§2), retry; if refresh fails → sign out,
  route to login. (Web today skips the explicit refresh because the Supabase SDK
  refreshes proactively, and signs out directly on 401.)
- **403 `email_not_verified`** → resend-verification screen (§3).
- **403 `account_deactivated`** → blocked-account screen; sign out.
- **403 `clan_suspended`** → clan-blocked screen; offer clan switch if the user has
  other clans.
- **403 `no_approved_clan_membership`** → pending/onboarding routing (§5).
- **400 `multiple_clans_no_selection`** → clan picker (§1.2).
- **409 `stale_write`** → see §6.1 below.
- **429 `rate_limited`** → back off. `/api/v1/auth/*` is limited to **20
  requests/min/IP** (`RateLimitMiddleware`, `app/main.py`). The 429 carries
  `error.detail.retry_after` (seconds) and a `Retry-After` header — honor them; do
  not blind-retry login/refresh.
- **503 `auth_provider_unavailable` / `storage_unavailable`** → transient-outage
  message with retry; not the user's fault (never render as "wrong password").

### 6.1 Handling `409 stale_write` (optimistic concurrency, ADR-017)

`PATCH /persons/{id}`, `PATCH /relationships/marriages/{id}`, and
`PATCH /relationships/parent-child/{id}` are all optimistic-concurrency writes: the
request body requires a **required** `expected_version: int` field, sourced from the
`version` field on a prior `GET`/create/update response for that same record — there
is no client path that can PATCH one of these three resources without first having
read it. Two failure modes:

- **Missing `expected_version`** → plain 422 `validation_error` (Pydantic), same as
  any other malformed body — not `stale_write`.
- **`expected_version` doesn't match the row's current `version`** → 409
  `stale_write`, `detail: {"current_version": <int>}` — someone else (another editor,
  or the same user in another tab/device) updated, deleted, or restored the record
  after the client's last read.

Client handling on `stale_write`:
1. Reload the record (`GET` it again, or just use `detail.current_version` if all you
   need is the number) to get the current `version` and current field values.
2. Show a conflict message (per the design spec's Vietnamese UX cue: "người khác vừa
   sửa" / "someone else just edited this") — do not silently resubmit.
3. Re-apply the user's in-progress edit on top of the fresh data and resubmit the
   PATCH with the new `version` as `expected_version`. Do not retry blindly with the
   old `expected_version` — it will 409 again.

This is deliberately scoped to `persons`/`marriages`/`parent_child` only — events,
documents, branches, and clans do not have a `version` field or an
`expected_version` requirement yet (see ADR-017).

---

## 7. FCM token lifecycle

Code: `app/api/v1/auth.py`, `app/schemas/auth.py` (`FCMTokenRequest`),
`app/infrastructure/persistence/auth_repository.py`.

- Register/update: `POST /api/v1/auth/me/fcm-token` with body
  `{"token": "<fcm-token, max 500 chars>", "device_platform": "android"|"ios"|"web"}`
  (Bearer required, no clan header). Upsert semantics: `ON CONFLICT (token) DO
  UPDATE` — re-registering an existing token re-binds it to the **current** user
  (correct for a device handed to another account).
- Remove: `DELETE /api/v1/auth/me/fcm-token` with the same body shape (only `token`
  is used; deletion is scoped to the current user + token).
- When to call:
  - after every successful login (and app start if a token exists),
  - on FCM token **rotation** (`onTokenRefresh` in Firebase Messaging) — register the
    new token,
  - `DELETE` the current token **before** `POST /auth/logout`, while the Bearer token
    is still valid.

Full push behavior (payloads, types, pruning) is not yet documented in this tree —
check `app/services/` for the current notification dispatch code if you need it.

---

## 8. Files & presigned URLs

Code: `app/infrastructure/storage/supabase_adapter.py`,
`app/domain/document/repository.py`, `app/application/document/handlers.py`.

- Presign TTL: `DEFAULT_PRESIGN_TTL = 3600` seconds (1 hour) — used by document
  upload and `GET /documents/{id}`.
- `POST /documents` (upload) returns `presigned_url` **and**
  `presigned_url_expires_at` (now + 3600 s).
- `GET /documents/{id}` returns a fresh `presigned_url` but **⚠️ its
  `presigned_url_expires_at` is `null`** (the query handler never sets it — backend
  inconsistency). Assume the 1-hour TTL.
- `GET /documents` (list) returns summaries **without** URLs — fetch the detail
  endpoint for a downloadable/displayable URL.
- `PATCH /documents/{id}/set-avatar` internally presigns a 30-day URL
  (`expires_in=86400*30`) but the route response contains only
  `{"message", "document_id"}` — the URL never reaches the client.

**Rule: presigned URLs are ephemeral.** Never persist them (DB, Hive, localStorage)
or bake them into cached view models beyond the TTL. When an image URL starts
failing (403/expired), re-fetch `GET /documents/{id}` for a fresh one.

**⚠️ UNDEFINED — needs backend decision**: `persons.avatar_url` (and the `avatar_url`
echoed on tree/person/event responses) is a plain client-writable string column
(max 500 chars); no backend code populates it from the set-avatar flow. If a client
writes a presigned URL into it, it silently expires after the TTL. What clients
should store there (a permanent public URL? nothing, resolving avatars via the
avatar document instead?) is not defined by the backend today.

---

## 9. Localization ownership

Code: `app/middleware/language_middleware.py`, `app/services/translator.py`,
`app/services/relationship_descriptor.py`, `app/schemas/historical_date.py`.

Server-localized (driven by `Accept-Language`, locales `vi|en|zh|fr`, default and
fallback `vi`):

- `error.message` in every error envelope,
- `data.message` strings on action endpoints (logout, profile updated, …),
- kinship/relationship descriptions (`relationship_descriptor.py` renders via `t()`
  in the request locale).

**Not** localized by the server:

- `HistoricalDate.display` and `.lunar` — these are **stored user-entered text**
  (e.g. "khoảng 1750", "15/08 Nhâm Tý"), returned verbatim in every locale.
- All UI chrome (labels, buttons, navigation, empty states) — client-side:
  next-intl (`web/messages/*.json`) on web, `AppLocalizations` (ARB files under
  `mobile/lib/shared/l10n/`) on mobile.

The user's saved locale: `PATCH /auth/me {"preferred_locale": "vi|en|zh|fr"}` writes
Supabase `user_metadata.preferred_locale`; on each authenticated request the backend
syncs it into `user_profiles.language`. Remember the §1.1 caveat: the profile
*responses* do not echo it back yet.

---

## 10. Types today (no codegen)

Per ADR-010, a typed OpenAPI `response_model` (`Envelope[T]`) and client codegen are
**deliberately deferred** until the frontend commits to a codegen pipeline (dynamic
person/tree reads can't be statically typed). Until then:

- Hand-write TS interfaces (web) and Dart classes (mobile) **from the shapes in
  `docs/contracts/rest-*-api.md`** — those files are the canonical copies of every
  request/response body, envelope, and `HistoricalDate` shape.
- Generic wrappers to define once per client:
  `Envelope<T> = {"data": T}`, `PagedEnvelope<T> = {"data": T[], "meta": {cursor,
  has_more, limit}}`, `ApiError = {"error": {code, message, detail}}`,
  `HistoricalDate = {date, precision, display, lunar}`.
- When a backend shape changes, the contract file changes in the same PR — diff
  `docs/contracts/` to find out what to update (web additionally pins shapes in
  `web/tests/contracts/`).

## Versioning & Compatibility Rules
- This guide documents integration behavior; per-endpoint shapes are owned by their
  `rest-*-api.md` files — update those first, this guide second.
- Interceptor semantics (401/403/409/429 handling, header rules) are load-bearing
  across client releases; changing them is a breaking change requiring an ADR.
