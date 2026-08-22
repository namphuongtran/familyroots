# ADR-048: Only `POST /invitations/{token}/accept` Moves to the System Session, and `clan_invitations` Takes the Clan-Isolation Policy

## Status

Accepted (2026-08-22), by seed S-043, which split out of S-009 because it carries a decision.
**This ADR ships code**, unlike ADR-042, ADR-043 and ADR-047, which were decision-only: a new
dependency provider, one route re-pointed at it, migration `032`, and the tests.

Every measurement below was taken on **2026-08-22** in the worktree `.claude/worktrees/backend`,
on branch `seed/s-043-invitation-accept-session`, from commit `d262514`.

## Context

### The question, in one sentence

`clan_invitations` is a clan-owned table with a NOT-NULL `clan_id`, and three of its four routes
are clan-scoped, but the fourth cannot be. Does the table get a policy, and where does the fourth
route run?

### What S-009 measured, and what it could not decide

Seed S-009 enabled RLS on `clan_memberships` (migration `031`) and stopped at
`clan_invitations`. The reason is written into `031_rls_clan_memberships.py:28-39` and pinned by a
test: adding `clan_invitations` to that migration's table list makes every invitation acceptance
raise `EntityNotFoundError: invitation.not_found`.

The chain, each link read at source:

| Link | Source | What it does |
|---|---|---|
| the route declares no clan | `backend/app/api/v1/invitations.py:95-99` (before this ADR: `:89-93`) | `get_current_user` and the handler, no `get_current_clan_id` — the invitee is not a member yet, so no membership check could pass |
| the handler ran on the request session | `backend/app/infrastructure/dependencies.py:336-340` | `get_invitation_command_handler(db = Depends(get_db))` |
| the seam drops the role regardless | `backend/app/core/rls.py:63-65` | `SET LOCAL ROLE familyroots_app` plus `set_config('app.clan_id', <clan or ''>)` on **every** transaction |
| the lookup has no clan predicate | `backend/app/infrastructure/persistence/invitation_repository.py:53-58` | `select(ClanInvitation).where(ClanInvitation.token == token)` — the token IS the authorization |
| the write half fails the same way | `invitation_repository.py:107-127` | `transition_status` updates by `id` + `status`, with no `clan_id` |

An unset GUC makes the migration-027 predicate
`clan_id = nullif(current_setting('app.clan_id', true), '')::uuid` evaluate to NULL, which is zero
rows and a rejected write. Fail-closed is the correct default and it is wrong for this one route.

### The seed's framing is wrong on one point, and the correction changes the shape of the problem

Seed S-043 says create, list and revoke "share the same handler" as accept. **List does not.**
Read at source on 2026-08-22:

| Route | Handler dependency | Provider | Session |
|---|---|---|---|
| `POST /clans/{clan_id}/invitations` (create) | `invitations.py:42` | `get_invitation_command_handler` | `get_db` |
| `GET /clans/{clan_id}/invitations` (list) | `invitations.py:62` | `get_invitation_**query**_handler`, `dependencies.py:343-344` | `get_db` |
| `DELETE /clans/{clan_id}/invitations/{id}` (revoke) | `invitations.py:76` | `get_invitation_command_handler` | `get_db` |
| `POST /invitations/{token}/accept` | `invitations.py:93` (before this ADR) | `get_invitation_command_handler` | `get_db` |

So moving `get_invitation_command_handler` to `get_system_db` would have stripped RLS from
**create and revoke**, not from all three. List shares the *session* dependency, not the handler.
The correction does not rescue that option — two clan-scoped write paths is still two too many —
but a later reader deserves the accurate count. All four routes are wired to `get_db`, and that
is the fact the option turned on.

### Nothing else in the tree touches this table

`grep -rn "ClanInvitation\|clan_invitations" backend/app --include='*.py'`, run 2026-08-22,
returns the model, the model registry, the mapper, the repository, and one error-message mapping
at `backend/app/core/exceptions.py:296`. There is no scheduler job, no export path, and no
platform-admin reader. The four routes above are the complete surface.

### What the accept path actually does, because the blast radius of a privileged session is the whole decision

`InvitationCommandHandler.accept` (`backend/app/application/invitation/handlers.py:67-131`)
touches four tables, and every one of them is keyed off the invitation the token resolved to:

1. `clan_invitations` — read by token (`:68`), then claimed by a conditional UPDATE on `id` (`:83-89`).
2. `user_profiles` — `ensure_profile` for the accepting user (`:93`).
3. `user_clan_roles` — read for `(cmd.user_id, inv.clan_id)` (`:95`), then promoted or inserted
   with `clan_id=inv.clan_id` (`:102`, `:113-127`).
4. `audit_logs` — written by the in-transaction domain-event dispatch on `uow.commit()` (`:130`, ADR-014).

There is no query in that path that is filtered by "the caller's clan", because the caller has no
clan. Every clan value comes from `inv`, and `inv` comes from a 256-bit
`secrets.token_urlsafe(32)` (`handlers.py:36`). The token is the authorization boundary, and
ADR-021 already rate-limits `/api/v1/invitations` at 20 requests per minute per IP against
guessing it.

### `user_clan_roles` makes this decision unavoidable rather than merely convenient

Point 3 above is the part that outlives this ADR. Seed **S-010** covers `user_clan_roles`. The
accept path **inserts** a row into that table for a clan the caller is not yet a member of. Under
the seam with an unset GUC, that insert fails the `WITH CHECK` exactly as the invitation read
fails the `USING`. So even if `clan_invitations` were left uncovered forever, S-010 would hit the
same wall on the same route. Moving accept off the seam is a precondition for S-010, not only for
this seed.

## Decision

### 1. Accept gets its own provider on the privileged session. Create, list and revoke do not move.

`backend/app/infrastructure/dependencies.py:358-362` adds:

```python
def get_invitation_accept_handler(
    db: AsyncSession = Depends(get_system_db),
) -> InvitationCommandHandler:
    uow = SqlAlchemyUnitOfWork(db, create_event_dispatcher(db))
    return InvitationCommandHandler(SqlAlchemyInvitationRepository(db), uow)
```

`backend/app/api/v1/invitations.py:99` points the accept route at it. **Named by name, because
seed S-043 requires it:**

- **create** keeps `get_invitation_command_handler` on `get_db`. Unchanged. It gains DB-level
  isolation from § 2.
- **list** keeps `get_invitation_query_handler` on `get_db`. Unchanged. It gains DB-level
  isolation from § 2.
- **revoke** keeps `get_invitation_command_handler` on `get_db`. Unchanged. It gains DB-level
  isolation from § 2.
- **accept** moves to `get_invitation_accept_handler` on `get_system_db`, and is the one path on
  this table with no DB-level isolation. It keeps the application-layer guarantee it always had:
  the token, and the fact that every clan value it writes is copied from the row that token
  resolved to.

This is not a new pattern. `dependencies.py:140-149` already does exactly this for identity
claims, with a comment giving the same reason in the same words: "a claimant resolves a person by
global id and is not yet a member of that person's clan". ADR-042 Fact 1 records it. The
invitation invitee is the same shape of actor. What is new here is that this table has **three
other request-role paths worth protecting**, which is precisely why the split is per-route rather
than per-aggregate.

### 2. `clan_invitations` takes the migration-027 predicate, in migration `032`

`backend/migrations/versions/032_rls_clan_invitations.py`, `USING` and `WITH CHECK` both
`clan_id = nullif(current_setting('app.clan_id', true), '')::uuid`, reversible in `downgrade`.
Grants already exist (migration `002:45` table CRUD, `026` functions and sequences).

### 3. The route-to-session wiring is pinned by a test, not by a comment

`backend/tests/unit/api/test_invitation_accept_session_wiring.py` walks the resolved FastAPI
dependant subtree of each of the four routes' handler providers, and asserts accept resolves
`get_system_db` and not `get_db`, while create, list and revoke resolve `get_db` and not
`get_system_db`. The comment in `dependencies.py:347-357` says the same thing, and a comment has
never stopped anyone.

The test is scoped to the **handler's** subtree on purpose. `get_current_user`
(`backend/app/core/security.py:108-111`) takes `Depends(get_db)`, so an RLS request session is
opened on the accept route no matter which session the handler uses. That session reads
`user_profiles`, which carries no policy, and it is never the session the invitation repository
holds. A whole-route assertion would have asserted something untrue.

## Alternatives considered

| Alternative | Why not |
|---|---|
| **Move `get_invitation_command_handler` to `get_system_db`** — the seed's option A | It is shared by create and revoke (`invitations.py:42`, `:76`), both clan-scoped writes with a real GUC. It trades one uncovered path for three, and buys nothing the per-route split does not |
| **Leave `clan_invitations` uncovered** — the seed's option B | Unlike `identity_claims` (ADR-042 Fact 1), this table has three live request-role paths, so a policy here is not inert. It also does not survive S-010: accept writes `user_clan_roles`, so the same wall arrives on the same route from a different table. Leaving it uncovered postpones the decision without removing it, and it makes S-015's coverage list carry a permanent exemption for a table that does not need one |
| **A permissive clause in the policy for the clan-less case**, e.g. `OR current_setting('app.clan_id', true) = ''` | Strictly worse than the system session. It would let **any** clan-less request session read **every** clan's invitations, including a future route nobody has written yet, and it would do so silently. The system session at least is one greppable wiring decision in one file. A policy that opens itself when context is missing inverts the fail-closed rule in ADR-008 § 3, "Default-deny" (its lines 173-176) |
| **Read the invitation privileged, then set `app.clan_id` from it and finish under the seam** — the hybrid | Three independent objections. (a) It redefines the GUC. Today `app.clan_id` is only ever a clan the caller has an **approved** membership in (`security.py:248-268` rejects anything else), and every policy in the tree is written against that meaning; setting it from a token would make the GUC mean "a clan someone claims" on one path. (b) It splits the token read from the conditional-UPDATE claim at `handlers.py:83-89` across two sessions, and that UPDATE is the accept-vs-revoke race guard the handler's own comment calls C3 (`handlers.py:79-82`) — its atomicity with the surrounding transaction is load-bearing. (c) It needs a second population site for the clan ContextVar outside `get_current_clan_id`, which is a change to `app/core/rls.py` or beside it; ADR-047 § "What a later seed must establish" sets the bar for touching that seam, and this would not clear it |
| **A dedicated Postgres role for the accept path, with its own policy** | A role per use case is not this repository's shape: there is one login role and one `familyroots_app` (ADR-043's table at its lines 34-38). It would also need a second policy on the table whose predicate is "any row", which is the permissive clause above wearing a hat |
| **Give the table a deny-all tripwire policy, as ADR-042 gives `identity_claims`** | ADR-042 chose deny-all because **no** request-role path touches that table, so a real policy would be inert. Here three of the four paths are request-role with a live GUC. Deny-all would break create, list and revoke |

## Consequences

### What this buys

- `clan_invitations` gets layer-2 isolation on the three paths that can carry it. A missed
  `WHERE clan_id = …` in `get_pending_by_email`, `expire_stale_pending`, `list_by_clan` or
  `get_by_id` is now stopped by the database rather than by review.
- The accept path's session is an explicit, tested, one-line wiring decision instead of an
  accident of a shared provider.
- **S-010 is unblocked on its hardest edge.** The `user_clan_roles` write inside accept no longer
  runs under the seam, so a policy on that table does not have to reason about this route.
- The failure mode that S-009 measured is now impossible to reintroduce silently: it fails in
  `test_invitation_accept_session_wiring` before it can fail in production.

### What this costs, stated plainly

- **The accept path has one layer of clan isolation where the other three have two.** That is the
  same posture ADR-042 accepted for `identity_claims` and ADR-031 accepted for cross-clan edges,
  and it is written here rather than hidden.
- **A leaked or guessed token reads and writes across clans**, exactly as it did before this ADR.
  Nothing about the posture of the token changed; what changed is that the fact is now written
  down. The guards are the 256-bit token (`handlers.py:36`), the pending-status check in the
  aggregate (`handlers.py:77`), expiry, and ADR-021's rate limit.
- **The audit row for `InvitationAccepted` is written on the privileged session.** ADR-043 gives
  `audit_logs` per-command policies, built by seed **S-014**. That seed must count this writer
  among the privileged ones, alongside the identity-claim and platform-admin handlers at
  `dependencies.py:144`, `:149`, `:167` and `:174`. It is not a new class of writer, but it is a
  new member of the class and S-014's list has to include it.
- **Four test modules had to learn about the second session.** Anything that exercises accept over
  HTTP now overrides `get_system_db` as well as `get_db`
  (`test_e2e_journeys.py`, `test_deactivation_invariant.py`, `test_invitation_rate_limit.py`), and
  the envelope unit test overrides the new provider
  (`tests/unit/api/test_invitation_envelope.py`). A future test that overrides only `get_db` and
  then calls accept will reach the real engine. That is the sharpest edge this change leaves.

## What this ADR deliberately does not decide

- **`user_clan_roles` and `clan_settings`**, which are seed S-010. This ADR removes one obstacle
  in front of S-010 and decides nothing else about them.
- **The invitation-expiry disagreement**, which is seed S-019.
- **`audit_logs` policies**, which ADR-043 decided and seed S-014 builds.
- **Any change to the invitation request or response contract.** There is none: the route, its
  body, and its envelope are byte-identical before and after.
- **`FORCE ROW LEVEL SECURITY`**, which ADR-008 lines 104-105 leaves until every table is covered.

## Related

- Seed **S-043** in [`../SEEDS.md`](../SEEDS.md), which this ADR closes, and seed **S-009**, which
  split it out.
- [ADR-008: Row-Level Security as Defense-in-Depth Layer-2](008-rls-defense-in-depth.md) — § 3, "Default-deny"
  (its lines 173-176), is the fail-closed rule this policy keeps for the three covered paths.
- [ADR-042: `identity_claims` Keeps Application-Layer Clan Isolation](042-identity-claims-app-layer-isolation-system-session-lockout.md) —
  the precedent for a cross-clan actor on the privileged session, and the contrast: that table has
  no request-role path and this one has three.
- [ADR-047: The RLS Seam Sets `app.clan_id` Only](047-rls-seam-sets-clan-id-only.md) — the seam
  contract, and the bar the rejected hybrid option would have had to clear.
- [ADR-043: `audit_logs` Is Inside Layer 2 with Per-Command Policies](043-audit-notification-rls-posture.md) —
  seed S-014 inherits one new privileged writer from this ADR.
- [ADR-021: Non-Enumerating Auth Surfaces + Invitation-Accept Rate Limit](021-non-enumerating-auth-surfaces.md) —
  the guard that stands in front of the token.
- [ADR-014: UoW In-Transaction Domain-Event Dispatch](014-uow-in-transaction-domain-events.md) —
  why the audit row is written on the accept path's own session.
