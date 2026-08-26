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
- Register can join an existing clan, create a new clan, or **name no clan at
  all**. `clan_action` is **optional** on `POST /register` and **required** on
  `POST /onboard`. See "Registering with no clan" below.
- `clan_code` (register + onboard, `clan_action=join`) names the clan to join.
  It is the clan's **slug**, not its UUID, and it must match the same
  `^[a-z0-9]+(-[a-z0-9]+)*$` pattern, max 100 chars; anything else is a 422
  `validation_error` naming `body.clan_code`. A well-formed code that no clan
  carries is a 404 `clan_not_found`. See the deprecation window below.
- `clan_slug` (register + onboard, `clan_action=create`) must match
  `^[a-z0-9]+(-[a-z0-9]+)*$` — lowercase ASCII alphanumerics and single
  hyphens, max 100 chars; anything else is a 422. Clients slugify the clan
  name before submitting (the slug appears in URLs and export filenames).
- `POST /register` is **non-enumerating (ADR-021)**: it returns the identical
  201 body whether or not the email already has an account. Clan-input
  validation (`clan_id_required_for_join`, `clan_code_and_id_both_given`,
  `clan_name_required_for_create`, `clan_slug_taken`, `clan_not_found`) runs
  unconditionally *before* the
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

### The join identifier: `clan_code` now, `clan_id` for one more release

**Decided by seed S-081 on 2026-08-26.** [ADR-057](../decisions/057-the-invitation-link-is-the-primary-join-path.md)
§ 2 made the typed join identifier the clan **code** (the slug) and left this one
question to this file, under "What this ADR deliberately does not decide": whether
`clan_id` is removed at once or accepted alongside the code for one release.

**The answer is one release, then removal.** `POST /auth/register` and
`POST /auth/onboard` accept **either** `clan_code` **or** `clan_id` on
`clan_action=join`. `clan_code` is the supported field. `clan_id` is deprecated on
this path and will be deleted, along with the 422 below.

| Request on `clan_action=join` | Result |
|---|---|
| `clan_code` alone | Resolved through `get_clan_by_slug`. This is the supported form |
| `clan_id` alone | Resolved through `get_clan_by_id`. **Deprecated** — works for one release |
| both | 422 `auth.clan_code_and_id_both_given`. Never silently reconciled |
| neither | 422 `auth.clan_id_required_for_join`, unchanged |
| a code no clan carries | 404 `clan_not_found` |
| a code failing the slug pattern | 422 `validation_error`, `detail.fields` contains `body.clan_code` |

**Why a window and not a clean break.** The web register form sends `clan_id` on
join, read 2026-08-26 at `web/src/app/[locale]/(auth)/register/page.tsx:130` for
`completeOnboarding` and `:140` for `signUp`. That form is a **separate seed**
(S-082) in a separate pull request. Removing `clan_id` here would make every join
submission 422 from the moment this change merges until that one does. There is no
compensating cost, because the field is optional either way: nothing that sends
`clan_code` is affected by `clan_id` still being accepted.

**No other client sends it.** Counted 2026-08-26: `grep -rn
"auth/register\|auth/onboard\|clan_id" mobile/lib` returns seven lines and none of
them builds a register or onboard body -- `refresh_interceptor.dart:17` lists
`/auth/register` as a path exempt from token refresh, and the rest read `clan_id`
out of responses. `mobile/lib/features/auth/presentation/` holds `blocked_page`,
`login_page`, `message_page`, `pending_approval_page`, and `verify_email_page`, and
no register page.

**Why both together is a 422 rather than a precedence rule.** The two fields can
name **different clans**, and a membership landing on the wrong clan is the one
boundary this product cannot get wrong (root `CLAUDE.md`). A precedence rule would
resolve such a request silently, and the response would look correct.

Measured 2026-08-26 against the code this change replaced, by posting
`clan_id` = clan A and `clan_code` = clan B to `POST /auth/register`:

```
status=201 body={"data":{"message":"auth.registration_received"}}
clan_id_sent_A=d82e6613-7330-4572-997c-fe2cee39c2ce
clan_code_sent_B=mb-7629e3b957 (7629e3b9-575f-462b-9b56-c74f32e6c01e)
rows=[(UUID('d82e6613-7330-4572-997c-fe2cee39c2ce'), False)]   LANDED_ON=A
```

The old schema had no `clan_code` field, so Pydantic dropped it and the join landed
on A with a 201 and no warning. A 422 is the honest answer while two identifiers
exist, and it disappears with `clan_id`.

**`auth.clan_id_required_for_join` keeps its name** even though the field it names
is the deprecated one. Spec § 7.1b writes the register screen's field-level error
handling around that exact code
(`docs/superpowers/specs/2026-08-02-design-system-and-screens.md:866-869`), and
[error-codes.md](error-codes.md) documents it. Renaming a stable error code would be
a second breaking change for no gain. Read it as "no clan identifier was supplied".

**What to delete when the window closes.** `clan_id` on `RegisterRequest` and
`AuthenticatedOnboardingRequest` (`backend/app/schemas/auth.py`), its branch in
`AuthCommandHandler._resolve_join_target`, the
`auth.clan_code_and_id_both_given` code and its four i18n entries, the two rows
above that mention `clan_id`, and the two tests named for it in
`backend/tests/integration/test_join_by_clan_code.py`. The `clan_not_found` copy
itself is **not** changed here: that message is shared with clan detail and the
platform-admin routes, and the inline register-field wording spec § 7.1b asks for
belongs to the web form (seed S-082).

### Registering with no clan

**Decided by seed S-085 on 2026-08-26**, and recorded in
[ADR-058](../decisions/058-registration-may-name-no-clan.md). This section extends "The
join identifier" above rather than replacing any of it: everything that section says
about `clan_code`, `clan_id`, and the deprecation window still holds whenever
`clan_action` is present.

**`clan_action` is optional on `POST /register` and required on `POST /onboard`.**

| Request to `POST /register` | Result |
|---|---|
| `clan_action` absent, no clan field either | **201.** An account is created with **no clan membership**. This is the supported invitee form |
| `clan_action` absent, but `clan_code`, `clan_id`, `clan_name` or `clan_slug` present | 422 `validation_error`. `detail.fields` contains `body`. Never silently treated as clanless |
| `clan_action=join` or `clan_action=create` | Exactly as "The join identifier" above. Nothing changed |

The 201 body is the same non-enumerating `{"data": {"message": ...}}` as every other
register outcome, and the verification email is still sent. **No error code was added to
this route**, which is deliberate: the register surface is non-enumerating (ADR-021) and a
new code is the easiest way to leak whether an email is registered. The "clan named
without an action" rule therefore lives in `RegisterRequest` itself, where it runs before
the route body and cannot consult the identity provider at all.

**Why the route needs this at all.** `POST /invitations/{token}/accept` requires an
authenticated caller — `Auth | Yes` at
[rest-invitations-api.md](rest-invitations-api.md):62, and the route declares
`Depends(get_current_user)` at `backend/app/api/v1/invitations.py:95-99`. An invited
person holds a token, has no clan code to type and no clan to found, and so had no way to
create the account that accept then requires them to hold. ADR-057 recorded that finding;
this closes it. The order a client should implement is: **register (no clan) → verify
email → login → accept**.

**What a clanless account looks like at login.** `POST /login` returns the ordinary
envelope with the membership fields empty:

```json
{ "data": { "access_token": "...", "refresh_token": "...", "expires_in": 3600,
  "user": { "clan_id": null, "role": null, "is_approved": false,
            "has_pending_membership": false, "...": "..." } } }
```

That triple — `clan_id` null, `is_approved` false, `has_pending_membership` false — is the
exact condition spec § 7.1b's sibling section § 7.2a uses to select its **onboarding
variant** (`docs/superpowers/specs/2026-08-02-design-system-and-screens.md:925-927`). It
is **not** the pending-approval state, which requires `has_pending_membership: true`. A
client must not tell a clanless user that a join request is being reviewed.

**`POST /onboard` is unchanged and still requires `clan_action`.** Its response
`RegisterResponse` types `clan_id` as non-optional, so it has no way to answer for an
account with no clan, and the route exists only to attach an already-authenticated user to
one. ADR-058 § 3 holds the reasoning. An invitee never calls it.

**The invitation token is not accepted by `POST /register`.** ADR-058 § 4 and § 5 record
why, including the four objections to granting the membership during sign-up and the reason
accept cannot create an account. Nothing about the invitation contract changes here.

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

### Profile field semantics (login and `GET /me`)

- `has_pending_membership` — true when the user has any membership row with
  `is_approved = false`. **Both** `POST /login` and `GET /me` compute it from the
  same query port, so they agree for the same user; clients do not need a
  follow-up `GET /me` after login just to read this flag.
- `preferred_locale` — echoed from the session's identity metadata
  (`user_metadata.preferred_locale`), validated against `vi|en|zh|fr`; unknown or
  absent → `"vi"`. `GET /me` reads the claim off the **presented access token**, so
  a value written by `PATCH /me` appears here from the next token refresh onward.
- `clan_id`/`clan_name`/`role`/`is_approved` describe **one** membership, chosen
  deterministically — see below.

### Which membership login returns (multi-clan users)

A user may belong to several clans. `POST /login` returns exactly one membership,
selected by a fixed, documented ordering
([ADR-035](../decisions/035-deterministic-login-membership-selection.md)):

1. **approved before pending** (`is_approved DESC`),
2. then **oldest `joined_at` first** (the membership row's `created_at` — the same
   value `GET /me/clans` exposes as `joined_at`),
3. then **lowest `clan_id`** as a final tiebreak.

`role` is non-null only when the selected membership is approved, so a
purely-pending user gets `role: null`, `is_approved: false`. `GET /me` applies the
same ordering over **approved memberships only**.

This is a *landing hint*, not server-side state: clan selection is still the
client's, sent per request as `X-Current-Clan-Id` (see
[frontend-integration-guide.md](frontend-integration-guide.md#12-clan-resolution)).

## Versioning & Compatibility Rules
- Adding optional auth/profile fields is non-breaking.
- Changing login/register payload requirements is breaking.
- `POST /register`'s response shape changed (ADR-021, 2026-07-14) from the
  full `RegisterResponse` to a uniform `{"message": ...}` envelope, taken as a
  breaking change deliberately accepted pre-frontend (no client consumed the
  old shape yet).
- `POST /register` and `POST /onboard` changed their **join** identifier
  (ADR-057 § 2, seed S-081, 2026-08-26) from a `clan_id` UUID to a `clan_code`
  slug. This is a breaking change to two public routes, landed with a
  one-release deprecation window rather than a clean break — see "The join
  identifier" above for the window, its reason, and the exact list of what to
  delete when it closes.
- Keep error envelopes and token semantics stable across client releases.
- The login membership-selection ordering (ADR-035) is load-bearing for client
  bootstrap; changing it is a behaviour change requiring a new ADR.
