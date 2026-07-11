# Auth Email Verification — Design Spec

**Date:** 2026-07-11
**Branch:** `feat/auth-email-verification` (off `main` @ 006d129)
**Security gap closed:** registration currently calls `admin.create_user(email_confirm=True)` — every
account is auto-confirmed with no proof the registrant owns the email. Anyone can register under
someone else's address. This spec requires a verified email before an account can authenticate.

**Owner decisions (2026-07-11):** Approach **A** (admin create *unconfirmed* + anon `resend` to send
the confirmation email). Supabase project already has **"Confirm email" enabled + SMTP configured** →
real end-to-end semantics (not a stubbed-only flag).

## Current flow (verified)

`register` → `IdentityProvider.create_user(email_confirm=True)` (admin/service-role; auto-confirms,
sends nothing) → assign clan membership → returns `RegisterResponse` with **no session**. The user
then calls `/login` (`sign_in_with_password`) separately. So requiring verification = create the user
**unconfirmed**, send a confirmation email, and let `/login` fail cleanly until the user confirms.

## Design (Approach A)

Two concerns, both landing in this one PR:

### Concern 1 — Enforce: unverified accounts cannot log in

- **Create unconfirmed.** `SupabaseIdentityProvider.create_user` passes `email_confirm=False`
  (`supabase_identity_provider.py:67-69`). Everything else about create/compensation is unchanged
  (admin API → clean `IdentityUserExistsError` detection; `delete_user` compensation intact).
- **Classify the login rejection.** `_classify` (`supabase_identity_provider.py:30-58`): inside the
  `AuthApiError` branch, **before** the generic 4xx→`IdentityAuthError`, add:
  `if exc.code == "email_not_confirmed": return IdentityEmailNotVerifiedError()`. (`email_not_confirmed`
  is a real `supabase_auth` `ErrorCode`; matching `.code`, not the message, is locale/rewording-proof.)
- **New domain exception** `IdentityEmailNotVerifiedError(IdentityError)` in
  `domain/auth/identity_provider.py` — a distinct sibling of `IdentityAuthError`, so `login`'s
  `except IdentityAuthError` does NOT swallow it; it propagates like `IdentityUnavailableError`.
- **403 handler.** Add `identity_email_not_verified_handler` (mirrors `identity_unavailable_handler`)
  returning **403** with envelope code `email_not_verified`, registered in `main.py`; i18n
  `error.email_not_verified` ×4 locales. (Today an unconfirmed login is mislabeled 401
  invalid-credentials.)

### Concern 2 — Send the verification email (+ resend)

- **Port method** `IdentityProvider.send_verification_email(*, email: str) -> None` (mirrors
  `send_password_reset`).
- **Adapter** `SupabaseIdentityProvider.send_verification_email`: anon client
  `resend({"type": "signup", "email": email, "options": {"email_redirect_to": <url>}})` via
  `asyncio.to_thread` (blocking SDK), `email_redirect_to` included only when configured. Mirrors
  `send_password_reset` exactly (anon client + off-load + optional redirect).
- **Register wiring.** In `AuthCommandHandler.register`, after `_assign_clan_membership` succeeds,
  send the verification email **best-effort** (swallow + log, like `/forgot-password`): a transient
  SMTP failure must not fail an otherwise-successful registration — the user recovers via resend.
  Ordering: create (unconfirmed) → assign membership → send verify email → return. If assignment
  fails, the existing compensation deletes the unconfirmed user and no email was sent.
- **Resend endpoint.** `POST /auth/resend-verification` (`ResendVerificationRequest{email: EmailStr}`)
  → `AuthSessionService.send_verification_email(email)` → port. **Non-enumerating**: always 200 with
  the same message, swallow provider errors (byte-for-byte the `/forgot-password` pattern). i18n
  `auth.verification_email_sent` ×4.
- **Config** `EMAIL_VERIFY_REDIRECT_URL: str = ""` (`core/config.py`, mirrors
  `PASSWORD_RESET_REDIRECT_URL`).

### Not changed (deliberate scope limits)

- `RegisterResponse` shape/`message` unchanged — the verification prompt is carried by the emailed
  link and enforced by the login 403; overloading the clan-oriented message is out of scope.
- Clan membership is still created at register time (pending/admin as today); the user simply cannot
  authenticate until verified. Deferring membership until verification would require persisting the
  intended clan action — unnecessary complexity.
- OAuth `/onboard` path is unaffected (those users authenticate via the provider directly; no
  password/confirmation email in play).

## Testing

Tests use the **stub `IdentityProvider`** (via the `get_identity_provider` DI seam) + real-DB + real
RS256 JWT — no live Supabase. The stub gains a `send_verification_email` method and a
sign-in that can raise the not-verified error.

- **Adapter unit** (`test_supabase_identity_provider`-style, mock the SDK clients): `create_user`
  passes `email_confirm=False`; `send_verification_email` calls anon `resend` with
  `{"type": "signup", "email": ...}` (+ `email_redirect_to` when configured, absent when not).
- **Classification** (`test_identity_error_classification.py`): an `AuthApiError(code="email_not_confirmed")`
  → `IdentityEmailNotVerifiedError` (extend the pinned table); a generic 400 invalid-creds still →
  `IdentityAuthError`; 5xx/429/408 still → `IdentityUnavailableError` (regression guard).
- **Login → 403** (HTTP flow, stub identity raising the not-verified error): response is **403** with
  envelope `code == "email_not_verified"`, NOT 401.
- **Register** (stub): on success, `create_user` then `send_verification_email(email)` is called
  (after membership assignment); on an assignment failure, `delete_user` is called and
  `send_verification_email` is **not** (compensation, no email for a rolled-back account).
- **Resend endpoint**: 200 + fixed message for both a known and an unknown email; a provider
  exception is swallowed (still 200) — non-enumerating.

Full gate: `uv run pytest`, `uvx ruff check .`, `uvx ruff format --check .`, `uv run mypy app/ tests/`,
`uv run lint-imports`.

## Out of scope (documented)

- Redesigning `RegisterResponse.message` for verification copy.
- Deferring clan membership until verification.
- A backend-hosted confirmation-callback route (confirmation is handled by Supabase's hosted flow +
  the `email_redirect_to` target, same model as password reset).
- The pre-existing F-1 envelope inconsistency (the new resend route follows the `{data}` convention;
  existing routes untouched).
