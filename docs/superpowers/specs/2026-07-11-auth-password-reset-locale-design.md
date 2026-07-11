# Auth: Password Reset + user_profiles.language — Design (2026-07-11)

**Status:** approved (owner) — proceeding to implementation plan.

## Goal

Ship the two demand-driven auth items users hit immediately:
1. **Password reset** — a locked-out user has no self-service recovery today (only the
   Supabase dashboard). Add a backend `forgot-password` trigger.
2. **Populate `user_profiles.language`** — the column is never written, so PR-H's
   per-recipient push locale is inert (everyone gets `vi`). Sync it so the notification
   job delivers each member's chosen language.

**Deferred (owner decision):** email verification (A2). `email_confirm: True` stays;
membership is admin-approved so the imposter-email blast radius is low. Revisit when
public self-registration opens. Documented as a follow-up.

## Context — current state (verified)

Auth routes: register/onboard/login/logout/refresh/me/fcm-token — no reset/verify.
`IdentityProvider` port: create_user/delete_user/sign_in/refresh/sign_out/update_user.
`ensure_user_profile` (post-A1, `core/security.py`) lazily upserts the profile via
`pg_insert(...).on_conflict_do_nothing()` + re-select on create, and refreshes
`last_login_at` (throttled) on the else branch — both branches commit. `update_profile`
(`AuthSessionService`, DB-free) writes the chosen locale only to Supabase user metadata.
`send_to_clan` (PR-H) reads `COALESCE(up.language,'vi')` — currently always `vi`.

Supabase reset model (verified via docs): `client.auth.reset_password_email(email,
{"redirect_to": url})` emails a recovery link carrying `token_hash` + `type=recovery`;
the **completion** (`verify_otp(type='recovery', token_hash)` → `update_user({password})`)
is inherently client-side (the token is delivered to the client by the link — Supabase's
PKCE flow).

## Decisions (owner-approved)

- **Reset completion is client-side.** The backend only *triggers* the email; the
  web/mobile Supabase SDK completes the reset. No backend `reset-password` endpoint (it
  would force the stateless backend to juggle a transient GoTrue recovery session for no
  benefit). Documented in `rest-auth-api.md`.
- **forgot-password is 200-swallow.** Always return the same 200 body regardless of
  whether the email exists OR whether the provider is reachable — never leak account
  existence or provider state. Provider errors are logged, not surfaced (no 503 here).
- **Locale sync point is `ensure_user_profile`, not `update_profile`** (refinement):
  `AuthSessionService.update_profile` is DB-free by design; adding a DB write there breaks
  that contract. Instead `ensure_user_profile` (runs every authenticated request, already
  reads the JWT) syncs `user_profiles.language` from the JWT's
  `user_metadata.preferred_locale`. Trade-off: the DB reflects a locale change on the next
  request after the client's token refresh (not instantly) — acceptable because the only
  consumer is the daily background notification job. If a request-time reader of
  `user_profiles.language` ever appears, add an immediate write in `PATCH /me` then.

## Design

### 1. Password-reset trigger
- **Port** (`app/domain/auth/identity_provider.py`): add
  `async def send_password_reset(self, *, email: str) -> None` to the `IdentityProvider`
  Protocol (docstring: best-effort; sends a recovery email via the provider).
- **Adapter** (`app/infrastructure/supabase_identity_provider.py`):
  `await asyncio.to_thread(get_anon_client().auth.reset_password_email, email, opts)` where
  `opts = {"redirect_to": settings.PASSWORD_RESET_REDIRECT_URL}` only when that setting is
  non-empty (else call without options → Supabase uses the project Site URL). Off-loaded
  (sync SDK). It may raise; the route swallows (below).
- **Service** (`app/application/auth/handlers.py`, `AuthSessionService`): add
  `async def send_password_reset(self, *, email: str) -> None` delegating to
  `self._identity.send_password_reset(email=email)`.
- **Route** (`app/api/v1/auth.py`): `POST /auth/forgot-password`, body `ForgotPasswordRequest`.
  Wrap the call in `try/except Exception: logger.warning(...)` and ALWAYS
  `return {"data": {"message": t("auth.password_reset_sent")}}` (200). Non-enumerating +
  provider-state-hiding by construction. Already rate-limited (under `/api/v1/auth`).
- **Schema** (`app/schemas/auth.py`): `class ForgotPasswordRequest(BaseModel): email: EmailStr`.
- **Config** (`app/core/config.py` + `.env.example`): `PASSWORD_RESET_REDIRECT_URL: str = ""`.
- **i18n**: `auth.password_reset_sent` in all four locales (vi/en/zh/fr), a generic
  "If that email is registered, we've sent a password-reset link." message.
- **Contract doc** (`docs/contracts/rest-auth-api.md`): document `POST /auth/forgot-password`
  (200-always, non-enumerating) and that reset *completion* is client-side via the Supabase
  SDK (verify_otp recovery + update_user password).
- **Ops note (not code):** the Supabase project must allowlist `PASSWORD_RESET_REDIRECT_URL`
  and have the recovery email template. Documented, not configured here.

### 2. Populate `user_profiles.language`
In `ensure_user_profile` (`app/core/security.py`):
- **Create branch:** add `language=(user_metadata.get("preferred_locale") or "vi")` to the
  `pg_insert(...)` values (validate against the supported set `{vi,en,zh,fr}`; unknown →
  `"vi"`, reusing `app.core.locale.SUPPORTED_LOCALES`).
- **Refresh (else) branch:** compute the JWT's `preferred_locale` (validated); if it differs
  from `profile.language`, set `profile.language`. Commit when EITHER `last_login_at` is
  stale OR the language changed (extend the existing throttle-commit condition).
- No change to `update_profile` (still writes Supabase metadata; the DB follows on next
  token refresh via the sync above).

## Tests (TDD)
- **forgot-password** (unit/route): returns the SAME 200 body for a known and an unknown
  email; calls `send_password_reset` with the posted email; when the identity provider
  raises, the route STILL returns 200 (swallowed) and logs. Assert the response body is the
  localized `auth.password_reset_sent` message, not a raw key.
- **adapter**: `send_password_reset` off-loads via `asyncio.to_thread` and passes
  `redirect_to` only when configured (patch the anon client; assert the call args in both
  the configured and empty-`PASSWORD_RESET_REDIRECT_URL` cases).
- **locale sync** (integration, real migrated DB, second-session read-back like C1/A1):
  a first-login JWT with `user_metadata.preferred_locale="en"` → `ensure_user_profile`
  persists `user_profiles.language = "en"`; a later request whose JWT flips it to `"zh"`
  updates the stored language; an unknown/absent locale → `"vi"`.
- **Regression:** existing auth tests + the A1 `ensure_user_profile` tests stay green
  (language is additive to the upsert/refresh; `is_active` gate unchanged).

## Out of scope (deliberate)
- **Email verification** (deferred — `email_confirm: True` stays; follow-up when public
  self-registration opens).
- **Backend `reset-password` completion endpoint** (client-side by Supabase's PKCE design).
- **Immediate `PATCH /me` DB locale write** (ensure_user_profile sync suffices for the
  background notification consumer; add later if a request-time reader appears).
- MFA, account deletion/GDPR, account-existence non-enumeration on *register* (separate).

## Files touched
`app/domain/auth/identity_provider.py` · `app/infrastructure/supabase_identity_provider.py` ·
`app/application/auth/handlers.py` · `app/api/v1/auth.py` · `app/schemas/auth.py` ·
`app/core/security.py` · `app/core/config.py` · `.env.example` · `app/i18n/{vi,en,zh,fr}.json` ·
`docs/contracts/rest-auth-api.md` · tests.

## Packaging
One PR `feat/auth-password-reset-locale`, TDD → full gate (`scripts/check.sh`) → subagent review → PR.
