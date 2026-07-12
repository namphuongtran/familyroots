# Authentication & Authorization Flow

End-to-end description of how a request goes from JWT to an authorized, clan-scoped
handler call. Code: `backend/app/core/security.py`, `app/core/permissions.py`,
`app/application/auth/handlers.py`, `app/infrastructure/supabase_identity_provider.py`.

## Token validation

- Identity provider is **Supabase Auth**. The backend validates the Bearer JWT
  against the project's **JWKS** (cached 1 hour, asyncio-Lock guarded refresh),
  `audience="authenticated"`.
- No session state server-side; refresh happens via `POST /auth/refresh`
  (Supabase refresh token, returns tokens only).

## Per-request identity pipeline

1. `get_current_user` — decode + verify JWT.
2. `ensure_user_profile` — **lazy upsert** of `user_profiles` on first sight of a
   user (no Supabase webhook dependency); shared `ON CONFLICT` helper.
3. **Deactivation gate** — `user_profiles.is_active = false` → 403 `account_deactivated`.
4. `get_current_clan_id` — resolves the active clan from the `X-Current-Clan-Id`
   header: auto-selects when the user belongs to exactly one clan; 400 when ambiguous;
   403 when not an approved member. **Suspended clan** → 403 `clan_suspended`.
   There is intentionally **no tenant middleware** — scoping is explicit per route.
5. Role check — `require_role(ClanRole.X)` (hierarchical `viewer < editor < admin`)
   or `RequireClanRole([...])` (explicit set), reading `user_clan_role` and requiring
   `is_approved = true`.
6. Handlers/repositories then filter every read/write by `clan_id`
   (see `multi-tenancy.md` — app-layer isolation is the only enforced layer today).

Super-admin routes (`/api/v1/platform`) bypass clan context and are gated by
`get_super_admin` — `user_profiles.platform_role = 'super_admin'` **from the DB**,
never a JWT claim or env match. Bootstrap via `scripts/bootstrap_super_admin.py` only.

## Registration & email verification (ADR-015)

- `POST /auth/register` creates the Supabase identity **unconfirmed**
  (`email_confirm: False` via admin API), creates profile + clan membership in the
  DB, then sends the verification email **best-effort** (a mail failure never fails
  registration).
- **Compensation invariant**: if DB-side setup fails after the identity was created,
  the orphan Supabase user is deleted — and no verification email is ever sent on
  the compensation path.
- Login with correct credentials but unconfirmed email → **403 `email_not_verified`**
  (distinct from 401; the client offers "resend verification").
- `POST /auth/resend-verification` and `POST /auth/forgot-password` always return
  200 with the same message whether or not the account exists (**non-enumerating**).
- Password-reset **completion is client-side** (Supabase `verify_otp` + `update_user`);
  the backend has no reset-password endpoint by design.
- Ops prerequisite: Supabase dashboard "Confirm email" ON + SMTP configured.

## Error semantics

Identity-provider failures map **truthfully**: infrastructure unavailability → 503
`identity_unavailable`; bad credentials → 401; policy denials → 403 with a stable
`code` (`email_not_verified`, `account_deactivated`, `clan_suspended`,
`clan_membership_required`). Envelope: `{"error": {code, message, detail}}`.

## Rate limiting

In-memory sliding window, **20 req/min/IP, scoped to `/api/v1/auth` only** (fine for
a single instance; Redis is the scale-out path). Extending the scope to
`/invitations/*/accept` is an open backlog item.
