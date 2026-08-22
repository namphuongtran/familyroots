# Expired invitations: lazy expire + allow re-invite (M11) — Design

**Date:** 2026-07-25
**Source finding:** M11 in `docs/architecture/backend-review-2026-07-18.md`.
**Owner decision:** create-path lazy expire-on-read (not a background job; not a list-display change).

> **Amendment (2026-08-22, seed S-019 and [ADR-053](../../decisions/053-invitation-status-is-derived-not-stored.md)):
> the "not a list-display change" half of the owner decision is superseded. The maintainer was
> asked on 2026-08-22 and chose the reversal.** The list read now derives the reported status from
> `expires_at` rather than returning the stored column. The other three clauses of this design stand
> unchanged: there is still **no background sweep**, expiry is still realized lazily in storage on
> re-invite, the accept path still refuses an expired token, and a re-invite still inserts a fresh
> row. **Nothing about the stored data changed** — only what a reader is told about it.
>
> Why it was reversed, in one sentence: this document's reasoning was that "a client can render
> 'expired'", and by 2026-08-02 the design spec had met that in practice and named it
> § J20 "**A status field that lies**", requiring every client to learn the rule independently or be
> wrong. The full argument, the three readings that found no client depending on the stored value,
> and the rejected sweep are in ADR-053.

## Problem

An invitation whose `expires_at` has passed **stays `status='pending'` forever** —
nothing ever transitions it. Two consequences on the re-invite path:

- `InvitationCommandHandler.create` calls `get_pending_by_email(clan_id, email)`
  (`invitation_repository.py:23-31`) which matches `status='pending'` with **no
  `expires_at` filter**, so the stale row raises `invitation.pending_exists` (409).
- Even if that check were bypassed, the partial unique index
  `uq_clan_invitations_pending ON (clan_id, email) WHERE status='pending'`
  (migration 001:655-658) blocks the re-insert.

Net: once an invitation times out unaccepted, that email can **never** be re-invited
to that clan. `Invitation.accept` correctly rejects an expired token
(`entity.py:90-91` → `invitation.expired`), so the row also never leaves `pending` via
the accept path.

The `clan_invitations_status_check` already permits `'expired'`
(migration 001:648-651) — **no migration needed**.

## Design (lazy expire-on-read on the create path; no migration, no new ADR)

### 1. New repository method: `expire_stale_pending`

```python
# invitation_repository.py
async def expire_stale_pending(self, clan_id: uuid.UUID, email: str) -> int:
    """Transition any (clan, email) invitation that is still 'pending' but whose
    expires_at has passed to 'expired'. DB-side now() for a single clock. Returns the
    row count (0 or 1 — the partial unique index allows at most one pending per pair).
    Frees the uq_clan_invitations_pending slot so a fresh invite can be inserted."""
    result = await self._session.execute(
        update(ClanInvitation)
        .where(
            ClanInvitation.clan_id == clan_id,
            ClanInvitation.email == email,
            ClanInvitation.status == "pending",
            ClanInvitation.expires_at <= func.now(),
        )
        .values(status="expired")
    )
    return result.rowcount
```

### 2. `get_pending_by_email` returns only LIVE pendings

Add `ClanInvitation.expires_at > func.now()` to the filter, so a timed-out invitation
never counts as a blocking pending (belt-and-suspenders with step 1, and correct
independent of call order).

### 3. `create` handler: expire-then-check-then-insert

```python
async def create(self, cmd):
    email = cmd.email.strip().lower()
    # Lazily retire a timed-out prior invite for this (clan,email) so it neither
    # blocks re-invite nor collides on the partial unique index. Committed atomically
    # with the new invite below.
    await self._repo.expire_stale_pending(cmd.clan_id, email)
    if await self._repo.get_pending_by_email(cmd.clan_id, email):  # now LIVE-only
        raise ConflictError("invitation.pending_exists")
    ... # unchanged: new token, new expires_at, create_invitation, track(inv), commit()
```

The `expire_stale_pending` UPDATE executes against the DB immediately; the new
`create_invitation` row flushes at `commit()`, by which time the stale row is already
`'expired'`, so the partial unique index does not collide. Both land in the **same
transaction** (`uow.commit()`); a failure rolls back both.

### Why the expiry emits no domain event

Expiry is a **passive, time-driven lifecycle transition** with no actor decision —
unlike create/accept/revoke, which are actor actions that emit
InvitationCreated/Accepted/Revoked. The re-invite still emits `InvitationCreated`
for the NEW invitation as before. (Consistent with treating expiry as a derived
state, the way the scheduler/purge system writers operate without an actor.)

## What does NOT change (owner decision)

- **No background sweep job** — expiry is realized lazily when the email is
  re-invited (the only moment the stale row actually matters). A never-re-invited
  expired row simply stays `pending` in storage; it blocks nothing.
- ~~**List endpoint unchanged** — `list_by_clan` still returns the stored `status`; it
  already returns `expires_at`, so a client can render "expired". Not reshaped here.~~
  **Superseded 2026-08-22 by seed S-019 and ADR-053: `list_by_clan` derives the status from
  `expires_at`.** Struck rather than deleted, because this document is a dated record of what was
  decided on 2026-07-25 and a silent rewrite would erase the evidence that it changed.
- Accept path unchanged — the aggregate already refuses an expired token
  (`invitation.expired`); a re-invite is the documented path forward.
- Re-invite **inserts a fresh row** (new token, new `expires_at`); the expired row
  remains as history. No row reuse.

## Blast radius

`get_pending_by_email` is called only by `create`. `expire_stale_pending` is new.
The change is confined to the invitation create path.

## Tests (real-DB; RED-first)

1. **Re-invite after expiry succeeds** (the bug): seed a `status='pending'` invite for
   (clan, email) with `expires_at` in the PAST → `create` a new invite for the same
   (clan, email) → succeeds (201), the stale row is now `'expired'`, exactly one
   `'pending'` row exists (the new one) with a fresh token/expiry. **RED today**
   (raises `invitation.pending_exists`, or the insert collides on the unique index).
2. **Live pending still blocks** (control): seed a `pending` invite with `expires_at`
   in the FUTURE → `create` for the same (clan,email) → 409 `invitation.pending_exists`;
   no second row inserted. GREEN today; pins that a still-valid invite is not clobbered.
3. **`expire_stale_pending` transitions exactly the stale one** (unit/integration): a
   past-expiry pending → returns 1 and the row is `'expired'`; a future-expiry pending →
   returns 0 and stays `'pending'`; an already-`accepted`/`revoked` row is untouched.
4. **`get_pending_by_email` is live-only**: returns the row for a future-expiry pending,
   `None` for a past-expiry pending. RED today for the past-expiry case.
5. **Two-sided clan isolation**: expiring/re-inviting for (clanA, email) does not touch a
   pending invite for (clanB, same email). Real-DB.
6. Existing invitation suites (accept, race, repository, e2e) stay green — a past-expiry
   invite still can't be *accepted* (aggregate refuses), and the accept-vs-revoke CAS is
   untouched.

## Docs

- `docs/contracts/rest-invitations-api.md` (or the invitations contract): a timed-out
  pending invitation is lazily transitioned to `expired` on the next invite to the same
  email, which then succeeds; a still-valid pending invite still 409s
  `invitation.pending_exists`.
- `docs/architecture/*` (invitation lifecycle, if documented): note the lazy
  expire-on-create transition and that expiry emits no event.
- Grep sweep: `pending_exists|expires_at|invitation.*expire|expired` across
  docs/contracts + docs/architecture; per-hit dispositions.

No new ADR — this fixes a lifecycle gap using the existing `expired` status the schema
already defines.
