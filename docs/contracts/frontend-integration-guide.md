# Frontend Integration Guide (web + mobile)

## Type
Integration guide (cross-cutting; complements the per-surface `rest-*-api.md` contracts)

## Owner
backend

## Consumers
- web (Next.js 16 / React 19)
- mobile (Flutter / Dio)

Every claim below is verified against backend code as of 2026-08-02 (files cited per
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
- `has_pending_membership` — **computed at login** (since 2026-07-16): true when the
  user has *any* membership row with `is_approved = false`. Login and `GET /auth/me`
  read it from the same query port, so they agree for the same user — no follow-up
  `GET /auth/me` call is needed just for this boolean.
- `preferred_locale` — echoed from the identity metadata of the session being returned
  (`user_metadata.preferred_locale`, validated against `vi|en|zh|fr`; anything else,
  or absent, → `"vi"`). `GET /auth/me` echoes the same claim off the **current access
  token**, so a `PATCH /auth/me {"preferred_locale": …}` is visible in the profile
  response from the next token refresh onward, not on the very next call with the old
  token. Clients that switch locale should apply it locally at once and treat this
  field as the server's record of the saved choice, not as a live echo of the last
  PATCH.
- **Multi-clan users**: which membership lands in `user.clan_id` is **deterministic**
  ([ADR-035](../decisions/035-deterministic-login-membership-selection.md)) — approved
  memberships beat pending ones, then oldest `joined_at` (the membership row's
  `created_at`, the same value `GET /me/clans` returns as `joined_at`), then lowest
  `clan_id` as the final tiebreak. It is a *login landing hint*, not a stored active
  clan: the user may switch, and the client still owns clan selection via the
  clan-resolution flow below.

`GET /auth/me` returns the same profile shape directly under `data`, but joined on
**approved** memberships only (same ordering, minus the approval preference, which is
implicit).

### 1.2 Clan resolution

1. `GET /api/v1/me/clans` → `{"data": [{clan_id, clan_name, clan_slug, role,
   joined_at}]}` — a plain canonical array, no `meta` — **approved memberships only**
   (pending ones are never listed).
2. If `data.length === 1`: you may skip explicit selection — the backend auto-selects.
3. If `data.length > 1`: let the user pick; optionally validate with
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

Note: `403 account_deactivated` (`user_profiles.is_active = false`) is **not**
part of this clan-resolution table — it's checked earlier, in `get_current_user`,
the single chokepoint on every authenticated request (including this one), not
just clan-scoped ones.

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
(`web/src/infrastructure/http/request-context.ts`).

Mobile reference implementation: `mobile/lib/core/network/interceptors/` — one
interceptor per header (`auth`, `clan`, `locale`, `trace`), assembled onto the single
Dio in `core/network/dio_provider.dart`. `isClanScoped(path)` in
`clan_interceptor.dart` is the single source of truth for which routes are exempt
from `X-Current-Clan-Id`.

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
  `web/src/middleware.ts` can gate protected routes server-side. The profile and the
  memberships are server state, held in one TanStack Query query
  (`web/src/features/auth/hooks/use-session.ts`) and never persisted in the browser;
  the active clan is the `current_clan_id` cookie (ADR-061 § 2, #183). Do not
  duplicate tokens, the profile or the role into localStorage.
- **Mobile**: satisfied. `supabase_flutter` is configured with a `LocalStorage`
  backed by `flutter_secure_storage` (`mobile/lib/core/storage/secure_session_store.dart`),
  so the session sits in the iOS Keychain / Android Keystore, never in shared
  preferences. The **PKCE code verifier has its own secure store** in the same file:
  leaving it on the default `GotrueAsyncStorage` writes it to SharedPreferences in
  plaintext. Clan selection and locale are not secrets and stay in ordinary
  preferences (`prefs_store.dart`).

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

Clan-input errors (a bad or missing `clan_code`, `clan_name`/`clan_slug`, an
already-taken slug, a nonexistent clan) still surface as normal 422/409/404
errors with their existing codes (`auth.clan_id_required_for_join`,
`auth.clan_code_and_id_both_given`, `auth.clan_name_required_for_create`,
`auth.clan_slug_taken`, `clan_not_found`) and should be handled as ordinary
form-validation errors — these are not account-existence signals.

**The join field submits `clan_code`, a clan code (the slug), not a UUID**
(ADR-057 § 2, 2026-08-26). `clan_id` is accepted on that path for one
more release and sending both is a 422; see "The join identifier" in
[rest-auth-api.md](rest-auth-api.md) for the window and what gets deleted when it
closes.

`POST /auth/onboard` (already-authenticated users attaching to a clan) is
**unchanged** and still returns the full profile-shaped response
(`user_id`/`email`/`clan_id`/`is_approved`/`message`).

What the backend does for the underlying email delivery (verified):

- `POST /auth/register` creates the Supabase user **unconfirmed**
  (`email_confirm: False`) and then sends the verification email best-effort via the
  anon client: `auth.resend({"type": "signup", "email": ...,
  "options": {"email_redirect_to": EMAIL_VERIFY_REDIRECT_URL}})`.
  `email_redirect_to` is only passed when `EMAIL_VERIFY_REDIRECT_URL` is configured;
  when empty, **Supabase falls back to the project's Site URL**. ADR-063 § 4 deletes
  this setting and its reset twin, because the decided template ignores `{{ .RedirectTo }}`.
  #202 removes them.
- `POST /auth/resend-verification` `{"email"}` sends the same email; always 200 with
  the same message (non-enumerating).
- Logging in before verifying → **403 `email_not_verified`** (not 401) — show a
  "resend verification" screen on that code.

### 3.1 What the email link lands as (answered 2026-10-04, issue #163)

The backend never sees this leg. It runs Supabase → the user's mailbox → the client.
The shape of the landing URL follows from two facts. One is in this repository, and
one is in the project's email templates.

**1. A `?code=` landing is impossible for these emails.** The backend sends every
auth email itself, through `auth.resend` (type `signup`) and `auth.reset_password_email`
(`backend/app/infrastructure/supabase_identity_provider.py:162-187`). The pinned
`supabase_auth` 2.31.0 sends **no `code_challenge`** on either call. Only its OAuth
helper adds one, even though `ClientOptions.flow_type` defaults to `"pkce"`. Supabase
Auth chooses the flow from that challenge (`supabase/auth`
`internal/api/recover.go:43`). With no challenge, the flow is **implicit**.
`web/src/app/api/auth/callback/route.ts` is the **Google OAuth** callback
(`web/src/features/auth/api/supabase-auth.ts`, `signInWithOAuth`), not an email
landing. An email link that reaches it carries no `code`, so it redirects to
`/vi/login?error=auth_callback_failed`.

**2. The email template picks between the two remaining shapes:**

| Template link | The link opens | The client lands with | The client finishes with |
|---|---|---|---|
| `{{ .ConfirmationURL }}`, **the Supabase default, and what the hosted project carries until #203** | `https://<ref>.supabase.co/auth/v1/verify?token=…&type=signup\|recovery&redirect_to=…`. Supabase verifies it on the click | `<redirect_to>#access_token=…&refresh_token=…&expires_in=…&token_type=bearer&type=signup\|recovery`, a **URL fragment**. A failure arrives as `#error=…&error_code=…&error_description=…` | **signup**: nothing. The address is already confirmed on the click, so route to login. **recovery**: read the fragment in browser code, set the session, then `updateUser({ password })` |
| a custom link built from `{{ .TokenHash }}`, **the shape ADR-063 decides** | our own page, directly: `{{ .SiteURL }}/verify-email/confirm?token_hash=…&type=email` or `{{ .SiteURL }}/reset-password?token_hash=…&type=recovery` | `?token_hash=…&type=email\|recovery` | `verifyOtp({ type, token_hash })`, **only on a user action**, never on load (ADR-063 § 2) |

**Two traps in the default shape:**
- A fragment never reaches a server. A Next.js route handler or server component
  cannot read it.
- The web's browser client cannot read it either. `@supabase/ssr` 0.12.4 fixes
  `createBrowserClient` to `flowType: "pkce"`, and auth-js 2.111.0 throws
  `Not a valid PKCE flow url.` when a PKCE client meets an implicit fragment
  (`GoTrueClient.js:3250-3254` in the installed package). A recovery screen on the
  default template must parse the fragment and call `setSession` itself.

**Where `redirect_to` lands.** It is `EMAIL_VERIFY_REDIRECT_URL` (or
`PASSWORD_RESET_REDIRECT_URL`) only when Supabase allows that URL. Otherwise it is the
project's **Site URL**. A URL is allowed when it has the Site URL's scheme and host
(any port, for a loopback host), or when it is listed under Redirect URLs (`supabase/auth`
`internal/utilities/request.go:106-113`). The live values are recorded in
[ops/supabase-hosted-project.md](../ops/supabase-hosted-project.md).

**Decided, not yet built (2026-10-04).** [ADR-063](../decisions/063-auth-email-links-land-as-a-token-hash-on-a-page-of-ours.md)
chose the `token_hash` row. The default link has a third trap: an email scanner that
fetches it spends the token before the person clicks. The landing pages are #200 and
#201. The templates move into the repository in #202, and the owner pushes them in #203.
**Until #203, the hosted emails still carry the default link, and no page reads it.**

---

## 4. Password-reset landing flow

Code: `app/api/v1/auth.py` (`forgot_password`),
`supabase_identity_provider.py` (`send_password_reset`), `rest-auth-api.md`.

1. `POST /api/v1/auth/forgot-password` `{"email"}` — always 200 with the same message
   (non-enumerating; provider failures are swallowed). Sends a Supabase recovery
   email with `redirect_to = PASSWORD_RESET_REDIRECT_URL` when configured (else the
   Supabase Site URL).
2. The email link lands in one of the two shapes in §3.1, with `type=recovery`. With
   the default template it is a URL fragment that carries a session. ADR-063 decides
   the `token_hash` shape, landing on `/{locale}/reset-password` (#201).
3. The client completes the reset **entirely via the Supabase SDK**. The backend has
   no reset-password endpoint, by design. It establishes the session from the link,
   then sets the password. Under ADR-063 § 2, both calls run on the form's one submit,
   never on page load, and a retry after a failed `updateUser` calls `updateUser` only:

```ts
// default template: the session is in the fragment (see §3.1 for why the PKCE browser
// client cannot pick it up by itself)
await supabase.auth.setSession({ access_token, refresh_token })
// custom {{ .TokenHash }} template instead:
// await supabase.auth.verifyOtp({ type: 'recovery', token_hash })
await supabase.auth.updateUser({ password: newPassword })
```

4. Keep the session and go on to the server guard's entry (ADR-063 § 3). This
   replaces "route to login".

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

Client routing rule: if `is_approved` is false and `has_pending_membership` is true →
pending-approval screen (web: `/{locale}/pending-approval`). If both are false and
`clan_id` is null → onboarding (`POST /auth/onboard`). The **login response carries
both flags correctly** (§1.1), so this decision can be made without a second call;
re-fetch `GET /auth/me` when you want a fresher answer (e.g. polling while the user
waits on an admin's approval).

### 5.1 Founder designation (thủy tổ) / tree onboarding

Code: `PUT /clans/me/founder` (`app/api/v1/clans.py::designate_founder`); see
[rest-clans-api.md](rest-clans-api.md#founder-designation-thủy-tổ) for the full
contract and [ADR-026](../decisions/026-single-founder-designation.md) for why.

A newly-onboarded clan has no thủy tổ (founder) until an admin explicitly
designates one — this is expected, not an error. The flow:

1. Admin/editor creates persons (`POST /persons`) — nothing designates a
   founder implicitly; person creation has no founder field.
2. Admin calls `PUT /clans/me/founder` with `{person_id}` for the person who
   should root the tree. Re-designating the current founder is a harmless
   no-op; designating someone else is a swap (see the contract for details).
3. `GET /tree` (no `root_person_id`) now renders, rooted at the designated
   founder, with graph-computed đời (generation) populated on every reachable
   node.

**Until step 2 happens**, `GET /tree` (no `root_person_id`) returns
**404 `clan_founder_not_found`**. Clients must treat this specific code as the
"prompt the admin to designate a thủy tổ" signal — e.g. an inline banner/CTA on
the tree screen linking to the founder-designation admin action — **not** as a
generic not-found/broken-tree state. Non-admin viewers hitting this 404 should
see a "waiting on your clan admin" message, since they cannot self-serve the
fix.

The same 404 can reappear later if an admin soft-deletes the current founder
(see ADR-026) — `is_founder` on the membership row is untouched by
delete/restore, it's just unreachable while the person is deleted. Recovery is
**one of two independent paths**, whichever fits the situation:

1. **Restore the deleted founder** — `POST /persons/{id}/restore` on that
   same person. No `PUT /clans/me/founder` call is needed: the membership's
   `is_founder` flag never changed, so as soon as the person is live again,
   `GET /tree` re-renders rooted at them on the very next call.
2. **Designate someone else** — `PUT /clans/me/founder` with a different
   `person_id`, when the deleted founder isn't coming back (or the admin
   wants a different thủy tổ regardless).

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
  upload, `GET /documents/{id}`, and restore.
- **Every response that carries a `presigned_url` also carries
  `presigned_url_expires_at`** — an absolute, timezone-aware UTC timestamp
  (`<url minted at> + TTL`). This holds for `POST /documents` (upload),
  `GET /documents/{id}`, and `POST /documents/{id}/restore`. Schedule refreshes off
  that timestamp; do not hardcode a TTL client-side (the server may shorten it).
- `GET /documents` (list) returns summaries **without** URLs — so also without an
  expiry — fetch the detail endpoint for a downloadable/displayable URL.
- `PATCH /documents/{id}/set-avatar` does **not** presign at all any more (ADR-036);
  see "Avatars" below.

**Rule: presigned URLs are ephemeral.** Never persist them (DB, Hive, localStorage)
or bake them into cached view models beyond the TTL. When an image URL starts
failing (403/expired), re-fetch `GET /documents/{id}` for a fresh one.

### Avatars are the one exception — permanent public URLs (ADR-036)

`persons.avatar_url` (and the `avatar_url` echoed on person, tree, search and event
responses) is now defined: it is a **permanent, publicly fetchable URL** into a
dedicated public avatars bucket that the backend writes.

- **Read**: safe to cache and persist indefinitely — DB, Hive, localStorage, an
  `<img src>`. It has no expiry, no token and no query string, and it is fetchable
  without an `Authorization` header. This is the opposite of the presign rule above,
  and the only field it applies to.
- **Write**: only `PATCH /documents/{document_id}/set-avatar` sets it. That response
  now returns the URL:
  `{"data": {"message", "document_id", "avatar_url"}}`.
- **Do not send `avatar_url` to `POST /persons` or `PATCH /persons/{id}`.** Any value
  — including `null` or `""` — is rejected with **422** `validation_error`,
  `detail.fields: ["body.avatar_url"]`, and fails the whole request. If your person
  form currently round-trips the field, strip it from the payload.
- Never construct or guess an avatar URL; render only what the API returned.
- The object path is stable per person, so **replacing an avatar reuses the same URL**.
  Expect up to ~5 minutes (`AVATAR_CACHE_CONTROL_SECONDS`) before caches pick up a new
  portrait; append your own cache-busting query parameter if you need an instant swap.
- New failure to handle on set-avatar: **503 `storage_bucket_not_configured`** means
  a bucket the environment needs has not been created yet — the public avatars bucket,
  or the private documents bucket the photo is copied from. An operator action, not
  something a retry fixes. Surface it as "files are not available in this environment"
  rather than a generic retry prompt. Document upload, detail and restore, and the
  JSON clan export, can answer the same code since #177.
- Privacy, so the UI does not over-promise: an avatar is readable by **anyone with the
  link, without logging in, regardless of clan**, and stays readable after the
  underlying document is deleted. Do not describe avatars as private or clan-only.

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
  `mobile/lib/core/l10n/`, template `app_vi.arb`) on mobile.

The user's saved locale: `PATCH /auth/me {"preferred_locale": "vi|en|zh|fr"}` writes
Supabase `user_metadata.preferred_locale`; on each authenticated request the backend
syncs it into `user_profiles.language` (which is what server-sent notifications use).
Both profile responses **do** echo the value back (§1.1) — `POST /auth/login` from the
freshly-signed-in session, `GET /auth/me` from the presented access token. Because the
locale rides in the token's claims, a PATCH is reflected in `GET /auth/me` (and in
notification locale) once the token is refreshed; apply the new locale in the UI
immediately rather than waiting to read it back.

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
