# Expired invitations: lazy expire + allow re-invite (M11) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** A timed-out invitation no longer blocks re-inviting that email. `create`
lazily transitions a stale (clan,email) `pending` invite (expires_at ≤ now) to
`expired`, then re-invites succeed; a still-valid pending invite still 409s. Spec:
`docs/superpowers/specs/2026-07-25-invitation-expiry-reinvite-design.md`. No migration
(the `clan_invitations_status_check` already permits `'expired'`), no new ADR.

**Architecture:** New `InvitationRepository.expire_stale_pending(clan_id, email)`
(DB-side `now()` UPDATE, returns rowcount); `get_pending_by_email` gains
`expires_at > func.now()` (live-only); `create` calls `expire_stale_pending` then the
live-only pending check before inserting. Same-transaction via `uow.commit()`.

**Tech Stack:** SQLAlchemy async; real-PG integration tests (patterns:
`test_invitation_repository.py`, `test_invitation_accept.py`, `test_invitation_race.py`).

## Global Constraints

- Filter/UPDATE use **DB-side `func.now()`**, not a Python `datetime`, so expiry uses
  one clock (matches the timestamptz `expires_at`).
- The partial unique index `uq_clan_invitations_pending` allows at most one `pending`
  per (clan,email), so `expire_stale_pending` affects 0 or 1 rows.
- `expire_stale_pending` runs BEFORE `create_invitation`'s `session.add`, so the stale
  row is already `'expired'` when the new row flushes — no unique-index collision. Both
  commit together.
- The lazy expiry emits **no domain event** (passive lifecycle); the new invite emits
  `InvitationCreated` as today. Do NOT add an InvitationExpired event.
- Do NOT add a background job, do NOT reshape the list endpoint (owner decision).
- Update the `InvitationRepository` **port** (`app/domain/invitation/repository.py`)
  with the new method signature so the Protocol and adapter stay in sync (mypy).
- RED-first; full gate before done: `cd backend && uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports`.

---

### Task 1: RED — re-invite after expiry, live-only pending, isolation

**Files:**
- Create: `backend/tests/integration/test_invitation_expiry.py`

**Interfaces:**
- Consumes: `migrated_db_url` / real-PG conftest; seeding pattern from
  `test_invitation_repository.py` / `test_invitation_accept.py` (raw clan + user +
  `clan_invitations` inserts with explicit `status` and `expires_at`); the
  `InvitationCommandHandler.create` wiring (build repo+uow+handler, or drive the
  create endpoint — mirror whichever the existing invitation tests use).

- [ ] **Step 1: Write the tests** (per spec Tests 1–5):
  - `test_reinvite_after_expiry_succeeds` — seed a `pending` invite, `expires_at` in the
    PAST → `create` a new invite for the same (clan,email) → succeeds; afterwards exactly
    one `pending` row for that pair (the new one, fresh token/expiry) and the old row is
    `expired`. **RED today** (raises `pending_exists` / unique-index collision).
  - `test_live_pending_still_blocks` — seed a `pending` invite, `expires_at` in the
    FUTURE → `create` same pair → `ConflictError("invitation.pending_exists")`; still
    exactly one row. GREEN today (control — don't clobber a valid invite).
  - `test_expire_stale_pending_targets_only_stale` — past-expiry pending → method returns
    1, row now `expired`; future-expiry pending → returns 0, stays `pending`; an
    `accepted`/`revoked` row is never touched. (Drives `expire_stale_pending` directly.)
  - `test_get_pending_by_email_live_only` — future-expiry pending → returned; past-expiry
    pending → `None`. **RED today** for the past-expiry case.
  - `test_reinvite_isolation_two_sided` — a past-expiry pending for (clanA, email) and a
    FUTURE pending for (clanB, same email): re-inviting clanA succeeds and does NOT touch
    clanB's row (still one `pending`, unchanged token). Real-DB, two-sided.
- [ ] **Step 2: Run — record RED.** Expected fails: `test_reinvite_after_expiry_succeeds`,
  `test_get_pending_by_email_live_only` (past case), and the `expire_stale_pending` test
  (method does not exist yet → import/attr error is acceptable RED, or write it to call
  through the repo once added — order the tasks so Task 1 references the to-be-added
  method; if that makes Step 2 a hard error rather than an assertion failure, split that
  one test to Task 2's run). Controls (live-pending-blocks) pass. If a must-fail passes,
  STOP → BLOCKED.
- [ ] **Step 3: Commit** — `git commit -m "test: RED — expired invitations block re-invite forever (M11)"`.

---

### Task 2: The fix — lazy expire + live-only pending

**Files:**
- Modify: `backend/app/infrastructure/persistence/invitation_repository.py`
- Modify: `backend/app/domain/invitation/repository.py` (port Protocol — add `expire_stale_pending`)
- Modify: `backend/app/application/invitation/handlers.py` (`create`)

- [ ] **Step 1: Port** — add `expire_stale_pending(self, clan_id: uuid.UUID, email: str) -> int` to the `InvitationRepository` Protocol (matching the adapter).
- [ ] **Step 2: Adapter** — implement `expire_stale_pending` (spec §1: `update(...).where(clan_id, email, status=='pending', expires_at <= func.now()).values(status='expired')`, return `result.rowcount`). Add `func` to the sqlalchemy import if needed. Add `ClanInvitation.expires_at > func.now()` to `get_pending_by_email` (spec §2).
- [ ] **Step 3: Handler** — in `create`, call `await self._repo.expire_stale_pending(cmd.clan_id, email)` immediately before the `get_pending_by_email` check (spec §3). Nothing else changes.
- [ ] **Step 4: Run** — Task-1 file green; then `test_invitation_repository.py`, `test_invitation_accept.py`, `test_invitation_race.py`, `test_invitation_handlers.py`, `test_e2e_journeys.py`; FULL suite (report count). mypy: check per-module overrides. Verify the accept-vs-revoke CAS and existing pending-exists behavior for LIVE invites are unchanged.
- [ ] **Step 5: Commit** — `git commit -m "fix(invitations): lazily expire timed-out pending invites so re-invite works; live-only pending check (M11)"`.

---

### Task 3: Docs (grep-verified)

**Files:**
- Modify: `docs/contracts/rest-invitations-api.md` (or the invitations contract doc)
- Possibly: an invitation-lifecycle architecture doc if one exists

- [ ] **Step 1: Grep** — `grep -rn "pending_exists\|expires_at\|invitation.*expire\|expired\|re-invite\|reinvite" docs/contracts docs/architecture --include='*.md' | grep -v "review-2026-07-18\|superpowers"`. Disposition each.
- [ ] **Step 2: Edits** — document: a timed-out pending invitation is lazily transitioned to `expired` on the next invite to the same email (which then succeeds with a fresh token/expiry); a still-valid pending invite still returns 409 `invitation.pending_exists`; expiry emits no event and there is no background sweep (lazy on create). Reference the M11 finding.
- [ ] **Step 3: Re-run grep; zero stale statements. Commit** — `git commit -m "docs: lazy invitation expiry enables re-invite (M11)"`.

---

### Task 4: Full gate (controller-run)

- [ ] `cd backend && uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports` — all five green.
