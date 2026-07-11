# Auth Hardening — Quick Wins Design Spec

**Date:** 2026-07-11
**Branch:** `fix/auth-hardening-quickwins` (off `main` @ 7fd6d08)
**Scope:** the two decision-free auth-hardening items. Email verification is a separate, later spec
(needs an approach fork + a Supabase project-config step) — explicitly NOT in this PR.

## Item 1 — Shared `ensure_profile` upsert helper (dedup + TOCTOU close)

**Problem:** `SqlAlchemyAuthRepository.ensure_profile` (`auth_repository.py:89-102`) and
`SqlAlchemyInvitationRepository.ensure_profile` (`invitation_repository.py:73-82`) are **byte-identical**
(same `UserProfile` model, different import alias) and both use a non-atomic `session.get()` →
`add()` → `flush()`. That is (a) duplicated, and (b) a check-then-insert TOCTOU: two concurrent
paths creating the same profile row race to `IntegrityError`. The per-request dependency
`ensure_user_profile` (`security.py:140-152`) already solved this with `pg_insert(...)
.on_conflict_do_nothing(index_elements=["id"])`; the repositories were never updated.

**Fix:** extract one shared helper and route both repos through it.

- New `app/infrastructure/persistence/_profile.py`:
  ```python
  async def ensure_profile_row(
      session: AsyncSession, user_id: uuid.UUID, email: str, display_name: str | None
  ) -> None:
      """Idempotent, race-safe UserProfile provisioning. ON CONFLICT DO NOTHING on the PK
      makes a concurrent duplicate insert a no-op (no IntegrityError). Flushes (not commits) —
      the caller's UoW owns the transaction."""
      stmt = (
          pg_insert(UserProfile)
          .values(id=user_id, email=email, display_name=display_name or email.split("@")[0])
          .on_conflict_do_nothing(index_elements=["id"])
      )
      await session.execute(stmt)
      await session.flush()
  ```
- Both `ensure_profile` methods become `await ensure_profile_row(self._session, user_id, email, display_name)`.

**Semantics preserved:** first-writer's `display_name` wins (ON CONFLICT DO NOTHING = existing row
untouched), exactly like the old `if existing: return`. Still `flush`, not `commit` (register /
invitation flows commit via their handler/UoW). No schema change.

## Item 2 — `GET /api/v1/claims` "list my own claims"

**Problem:** `user_claims_router` (`claims.py:22`) only exposes `DELETE /{claim_id}` (cancel). A user
has no way to see the status of the identity claims they submitted; only clan admins can list claims
(`GET /clans/{clan_id}/claims`).

**Fix:** a user-facing read of the caller's own claims (across all clans — it is the user's own data,
not clan-scoped).

- **Query port** `ClaimQueryPort` (`domain/person/claim_repository.py`): add
  `list_user_claims(user_id, status, page, page_size) -> tuple[list[ClaimModel], int]`.
- **Impl** `SqlAlchemyClaimQueryPort` (`claim_repository.py`): mirror `list_clan_claims` but filter
  `ClaimModel.user_id == user_id` (no clan join — a user sees their own claims regardless of which
  clan owns the target person). Same `status` filter, `created_at DESC`, offset/limit paging, count.
- **Handler** `ClaimQueryHandler.list_my_claims(user_id, status, page, page_size) ->
  IdentityClaimPaginatedResponse` (mirrors `list_clan_claims`).
- **Route** on `user_claims_router`: `GET ""` → `/api/v1/claims`. Auth: `require_active_user`
  (returns `UserProfile` with `.id`). Query params: `status` (optional), `page` (ge=1, default 1),
  `page_size` (ge=1, le=100, default 20). Returns the **envelope** `{"data": <IdentityClaimPaginatedResponse>}`
  — the convention the F-1 standardization will converge on (a NEW endpoint should follow the target
  shape, not add a bare-model outlier; the older admin claims list stays bare until F-1).

No clan-isolation concern: the endpoint returns only the caller's own `user_id` rows; there is no
cross-clan read of other users' data.

## Testing (per project verification discipline)

**Item 1 (real-DB):**
- `ensure_profile_row` twice for the same `user_id` → exactly one row, no `IntegrityError`
  (idempotent); a second call with a different `display_name` does NOT overwrite the first
  (ON CONFLICT DO NOTHING).
- Both repos' `ensure_profile` delegate (a call through each creates the row).

**Item 2:**
- Real-DB query port / handler: seed claims for user A (2) and user B (1); `list_my_claims(A)` returns
  A's 2 only (not B's); `status` filter narrows; paging (`page_size=1` → 1 item, `total=2`).
- Route-level (dependency-override, `TestClient`): `GET /api/v1/claims` returns `{"data": {...}}`
  with the caller's claims; unauthenticated → 401/403 via `require_active_user`.

Full gate: `uv run pytest`, `uvx ruff check .`, `uvx ruff format --check .`, `uv run mypy app/ tests/`,
`uv run lint-imports`.

## Out of scope

- **Email verification** — separate spec (fork: anon `sign_up` vs admin `create_user` + resend; plus a
  Supabase dashboard "Confirm email" + SMTP step; login "Email not confirmed" → 403 mapping; resend
  endpoint; redirect-URL config).
- F-1 envelope standardization of the *existing* auth/claims/invitations/platform_admin routes (this
  spec only makes the ONE new endpoint follow the target convention).
