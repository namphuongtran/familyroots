# ADR-053: An Invitation's Reported Status Is Derived From `expires_at`, Not Stored

**Status:** Accepted (2026-08-22). Shipped in the same change.

**This ADR supersedes an owner decision, and that is the reason it exists rather than being
a contract note.** `docs/superpowers/specs/2026-07-25-invitation-expiry-reinvite-design.md:5`
records: "**Owner decision:** create-path lazy expire-on-read (not a background job; **not a
list-display change**)", and `:89` states "**List endpoint unchanged** — `list_by_clan` still
returns the stored `status`; it already returns `expires_at`, so a client can render 'expired'.
Not reshaped here." That document now describes behaviour the code no longer has, and carries a
dated amendment pointing here. **The maintainer was asked and chose this on 2026-08-22.**

## Context

### The security half was already right, and saying so keeps this decision small

`backend/app/domain/invitation/entity.py` refuses to accept an invitation whose `expires_at` has
passed, raising `ConflictError("invitation.expired")`. Read at commit `fc0be76`, that check sat at
`:90`. **An expired invitation could never be used.** Nothing in this decision changes that, and the
test that proves it is part of the change.

### The defect was what a client is told

Nothing sweeps `clan_invitations`. A timed-out row keeps `status = "pending"` until the next create
for the same `(clan_id, email)` lazily retires it. So a list of invitations showed an admin
`Đang chờ` for a dead link.

The design spec had already met this and named it. `docs/superpowers/specs/2026-08-02-design-system-and-screens.md`
§ J20 is titled **"A status field that lies"**, and reads: "Trusting `status` would show an admin
`Đang chờ` for a dead link they are waiting on. So §7.10c derives the row state client-side from
`expires_at` and offers `Mời lại`, which reliably succeeds. The general rule this establishes: **when
a server field and a timestamp disagree, the timestamp wins in the UI.**" § 7.10c repeats it:
"**Expiry must be computed client-side.**"

**That rule is a client instruction, and it does not fix the server's answer.** Every future client —
the mobile app, an export, a third party reading the API — would have to learn it independently, or
be wrong.

## Decision

**The read derives the reported status from `expires_at`. The stored column is not swept.**

- `is_expired(expires_at, *, now)` in `backend/app/domain/invitation/entity.py` is **one predicate
  with two callers**: `accept` refuses on it, and the read derives from it. The comparison moved out
  of `accept` unchanged — `expires_at is not None and expires_at < now`, byte-identical to what was
  inline before.
- `effective_status(status, expires_at, *, now)` reports `expired` for a `pending` row past its
  deadline, and reports every other status verbatim. A stored `accepted`, `revoked`, or `expired` is
  never relabelled.
- The read uses `datetime.now(UTC)`, the same clock the accept path uses, **not** the database-side
  `now()` that `expire_stale_pending` uses. Agreeing with the accept decision is the whole point. It
  is read once per response, so every row in one list is judged at one instant.
- `docs/contracts/rest-invitations-api.md` states that the field is derived, which statuses derive,
  that the comparison is strict, and that `status` appears in exactly one response.

### Why not a sweep

A scheduled sweep would transition the row for real. It needs the advisory-lock topology at
`docs/architecture/notifications-scheduler.md:30-46`, and it adds **a third out-of-band writer**
beside the scheduler and the purge job. It buys a stored value that no reader needs, because every
reader already has `expires_at` in the same row.

### Why not "leave it to the client", which is what the 2026-07-25 decision said

Three readings, taken 2026-08-22, and none of them found a client depending on the stored value:

1. **The contract never promised it.** `docs/contracts/rest-invitations-api.md:36-40` describes lazy
   expiry **on re-invite**. That is about the row and the create path, not about what `status` means
   in a list row. There was no consumer promise to break.
2. **No client reads it.** The only `status` occurrence under `web/src` is the generated OpenAPI type
   at `web/src/generated/api-types.ts:2622-2637`. `mobile/lib` has none.
3. **The design spec already tells the client to ignore the field.** Deriving it on the server
   reaches the same answer § 7.10c reaches, so the client rule becomes **redundant rather than
   contradicted**. No web or mobile work is owed by this change.

## Consequences

- **§ 7.10c's client-side derivation is now belt and braces.** It is not wrong and it need not be
  removed. If it is ever removed, the server answer is already correct.
- **A future server-side `?status=` filter cannot be a plain `WHERE status = …`.** The derivation is
  per-row in Python and costs nothing today, because the list endpoint is not cursor-paginated and
  has no server-side filter (`docs/contracts/rest-invitations-api.md:70-74`). Anyone adding that
  query parameter must repeat the `expires_at` predicate in SQL, and that is worth its own seed
  before the parameter exists.
- **There is no invitation detail route.** The end state asked for consistency "in the list and
  in the detail". `backend/app/api/v1/invitations.py` has three admin routes — create (201), list,
  delete (204) — plus accept. `status` is returned in exactly one response, the list row, and the
  201 create body has no `status` field at all. Recorded in the contract so the next reader does not
  go looking for a route that does not exist.
- **The two halves are pinned to one predicate on purpose.** If they ever drift, a list reports
  `pending` for an invitation `accept` refuses, which is the exact defect this closes. The unit test
  `test_the_read_and_accept_agree_at_the_exact_boundary` pins both to the same instant, and it was
  watched failing when `<` was changed to `<=`.

## Verification, run 2026-08-22

The backend full quality gate, `CLAUDE.md:76`, on the combined batch tree: `1376 passed`,
`All checks passed!`, `474 files already formatted`, `no issues found in 435 source files`,
`Contracts: 6 kept, 0 broken`.

**Three negative controls, each watched failing:**

1. Revert the read path only: `AssertionError: assert 'pending' == 'expired'` — exactly the named
   test, `1 failed, 16 passed`.
2. Plant the drift the shared predicate exists to stop, `<` to `<=`:
   `test_the_read_and_accept_agree_at_the_exact_boundary` fails.
3. Make expiry never fire, `return False`: five tests fail, across both the read half and the accept
   half, proving the accept half's test can also fail.

**The integration test overrides `get_db` with the plain session maker, so it is not evidence about
the `clan_invitations` RLS policy.** The database-layer two-sided proof for that table remains
`backend/tests/integration/test_rls_phase7_clan_invitations.py`, which this change does not touch.

## Related

- `docs/superpowers/specs/2026-07-25-invitation-expiry-reinvite-design.md` — the owner decision this
  supersedes, now carrying a dated amendment.
- `docs/superpowers/specs/2026-08-02-design-system-and-screens.md` § J20 and § 7.10c — the client
  rule this makes redundant.
- `docs/architecture/notifications-scheduler.md:30-46` — the advisory-lock pattern the rejected sweep
  would have needed.
- `docs/contracts/rest-invitations-api.md` — the surface, updated in the same change.
