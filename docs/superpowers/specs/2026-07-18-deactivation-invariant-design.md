# Deactivation Invariant (A1) — Design

**Date:** 2026-07-18
**Source finding:** H1 in `docs/architecture/backend-review-2026-07-18.md`
**Owner decision:** Option A — gate inside `get_current_user` (chosen over an
explicit `get_active_user` swap across 65 routes).

## Problem

`user_profiles.is_active` is enforced in only two dependencies —
`ensure_user_profile` (`app/core/security.py:184`) and `get_current_clan_id`
(`app/core/security.py:230-234`). Every route that authenticates with bare
`get_current_user` skips the check entirely. Verified bypasses:

- `POST /invitations/{token}/accept` — a **deactivated user becomes an approved
  clan member with a role** (`app/api/v1/invitations.py:89-100`; the handler never
  checks either).
- `POST /auth/onboard` — deactivated user creates clans / join-requests.
- `GET/PATCH /auth/me`, FCM token register/remove, `GET /me/clans`,
  `POST /me/clans/{id}/select`.
- `POST /auth/login` and `POST /auth/refresh` (unauthenticated handlers) issue
  fresh token pairs + full profile for a deactivated account.
- `send_to_clan` (`app/services/notification.py:101`) broadcasts push content to
  deactivated members.

Deactivation lives only in our DB (the Supabase JWT stays valid), so it must be an
API-layer invariant — today it is a per-route accident.

## Design

### 1. Chokepoint: `get_current_user` gains the `is_active` gate

`app/core/security.py::get_current_user` adds `db: AsyncSession = Depends(get_db)`
and, after JWT verification, one PK-indexed scalar check:

```python
is_account_active = await db.scalar(
    select(UserProfile.is_active).where(UserProfile.id == uuid.UUID(payload["sub"]))
)
if is_account_active is False:
    raise ForbiddenError("account_deactivated")
```

Semantics (identical to today's `get_current_clan_id` gate):
- **Only an explicit `False` blocks.** A missing profile row (`None`) falls through —
  first-login provisioning (`ensure_user_profile`) must keep working for brand-new
  Supabase accounts.
- Error: 403 with existing code `account_deactivated` (already in all 4 locales).

Every authed route — current and future — inherits the invariant by construction.
FastAPI's per-request dependency cache means `get_db` yields the same session the
route uses; net cost is one PK scalar SELECT on the few routes that didn't already
pay it (see §3).

### 2. Handler-level gate where no JWT dependency runs

- **`login`** (`app/application/auth/handlers.py:314`): after Supabase `sign_in`
  succeeds, check `user_profiles.is_active` for the authenticated user id via a new
  `AuthQueryPort.is_account_active(user_id) -> bool | None` port method (the login
  response includes full profile/clan data — a deactivated account must get none of
  it); explicit `False` → raise `ForbiddenError("account_deactivated")` — no tokens,
  no profile in the response. (We do not attempt to revoke the Supabase session that
  `sign_in` created; the chokepoint makes those tokens useless against our API.
  Missing profile row → proceed, as today.)
- **`refresh_token` is intentionally NOT gated.** It lives in `AuthSessionService`,
  which is deliberately DB-free by design (its docstring is the contract), and its
  response contains only tokens — no profile data. Those tokens are inert against
  our API because the §1 chokepoint rejects every authenticated request. Adding a DB
  dependency to a DB-free service to invalidate already-useless tokens is not worth
  the design break. Documented as an accepted consequence below.

### 3. Single source: remove the now-duplicate checks

- `ensure_user_profile`: delete the `is_active` check at `security.py:184` (its
  sub-dependency `get_current_user` now guarantees it); keep a one-line comment
  pointing at the chokepoint.
- `get_current_clan_id`: delete the scalar check at `security.py:224-234` (same
  reason). Net query count for clan-scoped routes is unchanged (the same scalar
  moved from here into the chokepoint).

### 4. Notification fan-out

`send_to_clan` member SELECT adds `UserProfile.is_active.is_(True)` so deactivated
members stop receiving clan push notifications.

## Accepted consequences (documented, intentional)

- A deactivated user cannot call `POST /auth/logout` (403). Their refresh token
  stays live at Supabase but is useless against our API. Uniform invariant beats a
  logout exemption.
- `POST /auth/refresh` still returns a fresh token pair for a deactivated account
  (tokens only, no profile). Every use of those tokens against the API 403s at the
  chokepoint. Revisit only if client JWTs ever grant direct Supabase access (RLS),
  which is not the case today.
- A deactivated super admin is locked out like anyone else — reactivation requires
  another super admin or direct DB access. Consistent with "deactivation is total".
- Routes whose tests stub `get_current_user` via `dependency_overrides` bypass the
  gate *in those tests* (the override replaces the whole dependency). The invariant
  tests below therefore use the **real** dependency via the RS256 JWKS-injection
  pattern from `tests/integration/test_auth_http_flow.py`.

## Error contract

No new codes. `403 {"error": {"code": "account_deactivated", ...}}` — already
documented and localized. `docs/contracts/rest-auth-api.md` and
`docs/architecture/auth-flow.md` get a short "deactivation is enforced on every
authenticated request" note (doc-sync: grep all `docs/contracts` for `is_active` /
deactivation mentions).

## Tests (all real-DB integration; RED-first)

1. **Chokepoint HTTP tests** (real `get_current_user`, real RS256 JWT, real PG):
   deactivated user → 403 `account_deactivated` on the previously-bypassed routes:
   `POST /invitations/{token}/accept` (the privilege escalation — also assert **no
   membership row was created**), `POST /auth/onboard`, `GET /auth/me`,
   `GET /me/clans`. Positive control: same routes 2xx for an active user.
2. **First-login regression**: valid JWT, **no profile row** → request succeeds and
   provisions the profile (None ≠ False semantics preserved).
3. **Login gate**: deactivated account → login 403 with no tokens and no profile
   in the body. Active-user positive control. (No refresh test — refresh is
   intentionally ungated per §2; the chokepoint tests already prove refreshed
   tokens are useless.)
4. **Notification fan-out**: clan with one active + one deactivated approved member
   → `send_to_clan` targets only the active member's tokens.
5. **Sabotage verification** (process step, not a committed test): removing the
   chokepoint gate must turn test 1 RED — proven during development by the RED-first
   ordering.
6. Existing suite must stay green: the two removed duplicate checks were covered by
   existing tests (`get_current_clan_id` deactivation test, `ensure_user_profile`
   test) — those tests must still pass, now exercising the chokepoint via the
   dependency chain (adjust only if they unit-call the functions directly).

## Out of scope (tracked elsewhere in the review)

Unifying the `require_role` vs `RequireClanRole` stacks, `last_login_at` coverage,
ORM-as-pydantic type lie (all Low, review §LOW); any change to platform-admin
deactivate/activate endpoints themselves.
