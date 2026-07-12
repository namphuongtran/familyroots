# ADR-015: Email Verification via Admin-Create-Unconfirmed + Best-Effort Resend

## Status
Accepted (2026-07-11 — shipped, PR #66)

## Context
Registration must end with a verified email, but the backend creates identities via
the Supabase **admin** API (to control clan setup atomically), which skips Supabase's
own signup-confirmation flow. Verification also must never make registration fail or
leak which emails exist.

## Decision
- `create_user` sets `email_confirm: False`; verification mail is sent via anon
  `resend(type=signup)` — **best-effort after DB success** (mail failure never fails
  registration).
- **Compensation invariant**: if clan/membership setup fails after identity creation,
  the orphan Supabase user is deleted and **no email is ever sent on that path**.
- Unverified login → **403 `email_not_verified`** (a distinct sibling of auth
  failure — credentials were right), matched by error `code`.
- `POST /auth/resend-verification` is non-enumerating (always 200, same body).
- `EMAIL_VERIFY_REDIRECT_URL` setting controls the landing page.
- Ops prerequisite: Supabase "Confirm email" ON + SMTP configured (owner-confirmed).

## Consequences
Easier: registration stays atomic-with-compensation; clients get a stable,
actionable error code; no enumeration oracle.
Harder: two Supabase calls (admin create + anon resend); local/dev without SMTP
means manually confirming users; the flow depends on dashboard config that code
can't verify.

Flow detail: `docs/architecture/auth-flow.md`.
