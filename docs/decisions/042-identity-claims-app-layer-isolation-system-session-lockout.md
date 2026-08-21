# ADR-042: `identity_claims` Keeps Application-Layer Clan Isolation, and Its RLS Policy Denies the Request Role

## Status

Accepted (2026-08-22), by seed S-011. **Decision only. Nothing is shipped by this ADR.** Seed
S-012 builds the migration and the tests, and the "What S-012 must build" section below is the
part it has to satisfy.

`identity_claims` is the first clan-owned table this repository covers **without** giving it
clan isolation at the database layer. Read "What this decision does not buy you" before
reporting that as a defect.

## Context

### The missing column is the smallest part of the problem

`backend/app/models/identity_claim.py` is 54 lines and declares no `clan_id`. It reaches a clan
only through `person_id` at `:32-36`. So the template predicate from
`backend/migrations/versions/027_rls_events_branches.py:26`,
`clan_id = nullif(current_setting('app.clan_id', true), '')::uuid`, has nothing to compare.

That is where seed S-011 starts, and it is not where the decision is made. Three facts read at
source on 2026-08-22 decide it, and each one is bigger than the missing column.

### Fact 1: every path that touches this table already bypasses RLS, on purpose

Both claim handlers are wired to the privileged session:

- `backend/app/infrastructure/dependencies.py:144` — `get_claim_command_handler(db = Depends(get_system_db))`
- `backend/app/infrastructure/dependencies.py:149` — `get_claim_query_handler(db = Depends(get_system_db))`

`get_system_db` at `backend/app/core/database.py:86-93` uses `AsyncSessionLocal`, which has no
RLS seam, so it keeps the privileged connection. Its own docstring says it "bypasses RLS exactly
like the scheduler/purge". The comment above the wiring, at `dependencies.py:140-143`, records
why: "Identity claims are a CROSS-CLAN flow (a claimant resolves a person by global id and is
not yet a member of that person's clan)". ADR-008 Phase 4 says the same at lines 56-59.

A grep of `backend/app` on 2026-08-22 for `IdentityClaim` and `identity_claims` returns the
model, the model registry, the domain entity, the repository, the schemas, and the two handler
factories above. **No request-role code path reads or writes this table.** So a policy added
today would be inert: it would sit in `pg_policies`, pass a coverage gate, and protect nothing.
ADR-008 already names that failure at lines 100-107, "false security", and it is the reason
that ADR exists.

### Fact 2: two of the four routes have no clan context at all

| Route | Clan context | Source |
|---|---|---|
| `GET /m/claims` (list my claims, "across all clans") | none | `backend/app/api/v1/claims.py:35-43` |
| `DELETE /m/claims/{claim_id}` (cancel) | none | `backend/app/api/v1/claims.py:51-57` |
| `GET /m/clans/{clan_id}/claims` | the admin's active clan | `backend/app/api/v1/claims.py:65-83` |
| `POST /m/persons/{person_id}/claim` | the **claimant's** active clan, not the person's | `backend/app/api/v1/persons.py:417-424` |

The first two depend only on `require_active_user`, which is `ensure_user_profile`
(`backend/app/core/permissions.py:123`), and that dependency takes `get_current_user` plus
`get_db` and no clan (`backend/app/core/security.py:142-145`). Under the RLS seam an absent clan
leaves the GUC empty, which `backend/app/core/rls.py:64` turns into `''` and the policy turns
into NULL: zero rows, rejected writes, fail closed. That is correct behaviour for a clan-owned
table and wrong behaviour for these two routes, which are deliberately cross-clan.

The fourth row is the sharp one. `POST /persons/{person_id}/claim` runs under `RequireViewer`
(`permissions.py:118`, resolving through `get_current_clan_id` at `permissions.py:43`), so a clan
**is** set. It is the claimant's own active clan. The person being claimed usually belongs to a
different clan, which is the entire point of the workflow. A policy keyed on the person's clan
would reject exactly the insert the feature exists to perform.

### Fact 3: the clan of a claim is provenance, and provenance is nullable

The clan that owns a claim is the person's **origin** clan, not a membership. ADR-007's
2026-07-05 update settled that: "Claim review is authorized by the person's origin clan
(`person.created_by_clan_id`, provenance)". The read path matches it:
`backend/app/infrastructure/persistence/claim_repository.py:204-205` joins `persons` and filters
`Person.created_by_clan_id == clan_id`.

`backend/app/models/person.py:38-43` declares that column `Mapped[uuid.UUID | None]` with
`ON DELETE SET NULL`, which ADR-009 lists among its two deliberate SET NULL columns: "A person
outlives its origin clan (its provenance is simply cleared)". So the key any policy would use is
nullable and can be cleared underneath the claim.

Note also that the seed's option A cannot be written as its text gives it. `persons` has no
`clan_id` column at all. It carries the nullable origin above, and membership is the M:N
`clan_memberships` table, which is why `029_rls_persons.py:45-48` keys on an `EXISTS` against
`clan_memberships` rather than on a column.

## Decision

### 1. The application layer stays the only clan-isolation enforcement on this table

`identity_claims` keeps the isolation it has: `list_clan_claims` filters on the person's origin
clan (`claim_repository.py:204-205`), the admin routes check `clan_id != active_clan_id` and
raise `clan_context_mismatch` (`claims.py:76-77`, `:100-101`, `:123-124`), and
`ClaimCommandHandler._verify_admin_access` authorizes review by the origin clan, taking
`claim.person.created_by_clan_id` (`backend/app/application/person/claim_handlers.py:117`, `:198`).

This is the third option in seed S-011, and it is chosen without softening: **this table has one
layer of clan isolation where the six covered tables have two.** The precedent is ADR-031, which
accepted an application-layer guarantee for cross-clan edges and wrote down the residual risk
rather than hiding it. The difference is worth stating: ADR-031 expected RLS to subsume its gap
later, and this ADR does not. RLS cannot subsume this one until the claim flow itself stops being
cross-clan.

### 2. RLS is still enabled, with one explicit policy that denies the request role

The migration S-012 writes enables row-level security on `identity_claims` and creates exactly
one policy:

```sql
CREATE POLICY identity_claims_system_session_only ON identity_claims
    FOR ALL USING (false) WITH CHECK (false);
```

**This is not clan isolation, and calling it a second layer would be a lie.** It is a tripwire.
It converts one specific future failure from silent to loud: an engineer who wires a claims query
to `get_db` instead of `get_system_db` gets zero rows and a rejected write, in their own test
run, instead of a query that quietly reads every clan's claims. Today that mis-wiring leaks and
nothing reports it, because `002_rls_documents_pilot.py:45` grants `familyroots_app` full CRUD on
every table in `public`.

The policy is written explicitly rather than left as "RLS enabled with no policies", which
produces the same deny-all in Postgres. Two reasons. The standing coverage guard at
`backend/tests/integration/test_rls_activation.py:190-193` treats an enabled table with no policy
as a lockout defect and fails on it, and it is right to. And a named policy states intent to
whoever reads `pg_policies` next.

The privileged connection is unaffected, exactly as it is for the six covered tables. The policy
is `ENABLE`, not `FORCE`, and the system path connects as a bypassing role (owner locally,
service role on Supabase, per ADR-008 lines 103-105).

### 3. Why the subquery was rejected

Written correctly against provenance, the option A policy would be
`EXISTS (SELECT 1 FROM persons p WHERE p.id = identity_claims.person_id AND p.created_by_clan_id = <GUC>)`.
Four objections, in increasing order of seriousness:

1. It is inert today, for Fact 1. Every reader is on the system session.
2. It breaks two routes and the create route the moment it is not inert, for Fact 2.
3. **It interacts with the `persons` policy from migration 029, and the interaction is against
   us.** Postgres applies the referenced table's row security to a table named inside a policy
   expression, so the inner `SELECT ... FROM persons` would itself be filtered by `persons_sel`
   (`029_rls_persons.py:56`), which requires a `clan_memberships` row for the active clan
   (`:45-48`). A claimant has no membership in the person's clan by definition
   (`dependencies.py:140-141`). So the claim would be filtered twice, by origin **and** by
   membership, and the strictest of the two wins. The seed asked for this interaction to be
   reasoned about rather than assumed. Reasoned about, it makes the option worse, not merely
   slower.
4. A person whose origin clan was cleared to NULL by ADR-009 has claims that no clan can see.
   That happens to match ADR-007 (such claims "cannot be reviewed"), so it is not a defect on its
   own. It is one more edge the policy would own silently.

The per-row cost the seed names is real but it is the least of these.

### 4. Why the denormalized column was rejected

A `identity_claims.clan_id` copied from `persons.created_by_clan_id` fails on the invariant, not
on the schema change:

- **It cannot be enforced declaratively.** A composite foreign key to `persons (id,
  created_by_clan_id)` needs a unique index on a pair whose second column is nullable, and under
  the default `MATCH SIMPLE` a NULL in the referencing column skips the check entirely.
- **The source column moves.** `persons.created_by_clan_id` is `ON DELETE SET NULL` (ADR-009), so
  the copy goes stale exactly when a clan is removed, which is the moment isolation matters most.
- **`test_clan_fks_are_restrict` forces a choice and both answers are wrong.** ADR-009 pins that
  the clan-referencing foreign keys partition exactly into RESTRICT and SET NULL. RESTRICT on a
  claim contradicts the person's own SET NULL. SET NULL leaves a claim whose `clan_id` is NULL,
  which the policy then hides from everyone including the origin clan.
- It is inert today for Fact 1, and it breaks the same routes as the subquery for Fact 2. The
  schema change buys nothing that the subquery does not, and costs a backfill on top.

### 5. The one-pending-claim invariant is what a clan-keyed policy would actually break

`backend/app/models/identity_claim.py:17-23` declares
`uq_identity_claim_user_pending`, unique on `user_id` where `status = 'PENDING'` (created in
`backend/migrations/versions/001_initial.py:770`). ADR-007 calls it the spam guard: at most one
pending claim per user **globally**, across all clans.

The index itself would survive any policy, because Postgres runs unique and foreign-key checks
outside row security. What would not survive is the check the application makes first.
`ClaimCommandHandler.submit_claim` calls `has_pending_claims`
(`backend/app/application/person/claim_handlers.py:44-46` and
`claim_repository.py:66-72`) and raises a clean `ConflictError("user_already_has_pending_claim")`.
Under any clan-keyed policy that SELECT becomes blind to a pending claim held in another clan.
The handler would sail past its own guard and hit the unique index instead, turning a documented
409 into an integrity error raised from the flush. The invariant would still hold and would stop
being **checkable** in the place the product checks it.

The deny-all policy leaves this untouched, because the handler stays on the system session.

## Consequences

### What this decision buys

- The identity-claim workflow keeps working exactly as ADR-007 specifies, cross-clan, with no
  route losing its clan-free access and no create path fighting a policy.
- No schema change, no backfill, no new invariant to keep true, no per-row subquery on a table
  read by an admin queue.
- One future defect class fails loudly instead of leaking: a claims query wired to the request
  session.
- The decision is cheap to revisit. If the claim flow is ever redesigned to be clan-scoped, the
  deny-all policy is replaced by a real one, and nothing else written here has to be undone.

### What this decision does not buy you, stated plainly

**`identity_claims` has one layer of clan isolation, and the other clan-owned tables have two.**
If a future read path forgets its `created_by_clan_id` filter, the database will not stop it, and
one clan's admin will see another clan's claims: the claimant's user id, the person id, and the
requester and reviewer notes. That is the residual risk, it is accepted here, and it is not
mitigated by anything in this ADR. The tripwire in section 2 catches a mis-wired **session**. It
does not catch a missing **filter** on the correct session.

**The deny-all policy will make a coverage gate lie unless the gate is told.** A check that asks
"does this table have RLS enabled and at least one policy" answers yes for `identity_claims` and
means nothing by it. Seed S-015 owns that gate, and section "What S-012 must build" item 5 is the
obligation that keeps it honest.

**Nothing here is verified against a running database.** This ADR is documentation only, produced
under a seed whose verification field says "No gate". Every claim above is read from source at
the line cited, on 2026-08-22. The empirical checks belong to S-012.

## What S-012 must build

S-012 is blocked on this ADR and its author reads this section as the specification.

1. **A new migration** (the next free number after `029_rls_persons`, which S-008 to S-010 may
   also be claiming; take the number that is free when you write it). It runs
   `ALTER TABLE identity_claims ENABLE ROW LEVEL SECURITY` and creates
   `identity_claims_system_session_only` as `FOR ALL USING (false) WITH CHECK (false)`. The
   downgrade drops the policy and disables row-level security. Both directions run.
2. **A test that the request role is denied both ways**: under a real `RlsSession` with the GUC
   set to a clan that owns a seeded claim, a SELECT returns zero rows and an INSERT is rejected.
   Seed the claim through the privileged connection, as the existing claim tests do
   (`backend/tests/integration/test_list_my_claims.py:62`).
3. **A test that the system session still works**: the same seeded claim is readable and writable
   through `AsyncSessionLocal`, so the workflow is untouched. Driving one claims route end to end
   is worth more than a raw query here.
4. **The cross-clan uniqueness test seed S-012 already names**: a pending claim for user U exists,
   and a second pending claim for U reached through a different clan is still rejected. This
   should behave identically before and after the migration, which is the point.
5. **The coverage guard, updated so it cannot be read as clan isolation.**
   `backend/tests/integration/test_rls_activation.py:180-187` pins the RLS-enabled set to six
   tables and this migration makes it seven. Do not simply add the name. Split the assertion into
   clan-isolated tables and deny-all tables, so `identity_claims` is enumerated as
   request-role-denied and a future reader cannot mistake it for covered. S-015 builds on
   whatever shape you leave.
6. **One empirical check of a claim this ADR makes from the manual, not from a run.** Postgres
   documents that referential integrity actions bypass row security, so the `ON DELETE CASCADE`
   from `persons` and `user_profiles` into `identity_claims`
   (`backend/app/models/identity_claim.py:29`, `:34`) should still cascade under the deny-all
   policy. Delete a person under the request role and prove the claim row goes with it. If it
   does not, this ADR is wrong on that point and S-012 should say so rather than working around
   it.
7. **The planted inversion**, as every isolation seed in M1 requires: drop
   `identity_claims_system_session_only`, watch the named denial test fail, restore it, and quote
   the output.

If S-012 finds that any of the three facts above no longer holds, in particular if a claim handler
has moved off `get_system_db`, it must stop and reopen this decision rather than adapt the
migration to a tree this ADR did not read.

## What this ADR deliberately does not decide

- **Whether the identity-claim flow should be clan-scoped at all.** Making it clan-scoped is the
  only route to real RLS coverage here, and it changes ADR-007's workflow, the two clan-free
  routes, and the session model together. That is a redesign with its own ADR, not an amendment.
- **`audit_logs` and `notification_log`.** They are seed S-013 and ADR-043. `audit_logs` shares
  the shape of the problem, a privileged cross-clan reader plus a nullable clan, and it should be
  free to reach a different answer. Nothing here binds it.
- **Whether an `app.user_id` GUC should exist.** ADR-008 line 135 describes the seam as setting
  `SET LOCAL app.clan_id` **and** `SET LOCAL app.user_id`, but `backend/app/core/rls.py:63-65`
  sets the role and `app.clan_id` only. A user-keyed policy would have been the one shape that
  fits `GET /m/claims`, and it does not exist today. Recorded here as a finding; adding it is a
  seed of its own, and it would still leave the admin queue unsolved.
- **`FORCE ROW LEVEL SECURITY`**, which ADR-008 lines 89-90 leaves until every table is covered.
  A deny-all table under FORCE would lock out the system session too, which is a trap worth
  writing down before that day.
- **The grants.** `familyroots_app` keeps full CRUD on `identity_claims` from
  `002_rls_documents_pilot.py:45`. Revoking them instead of adding a policy would be a second
  mechanism for the same intent, and the policy is the one this repository already reads.

## Related

- Seed S-011 in [`../SEEDS.md`](../SEEDS.md), which this ADR closes, and seed S-012, which it
  specifies.
- [ADR-007: Identity Claims Workflow](007-identity-claims-workflow.md), whose 2026-07-05 update
  makes review a provenance decision and whose spam guard is the invariant in section 5.
- [ADR-008: Row-Level Security as Defense-in-Depth Layer-2](008-rls-defense-in-depth.md), for the
  request-role seam, the fail-closed predicate, the "false security" warning at lines 100-107,
  and the Phase 4 note that identity-claim handlers run privileged.
- [ADR-009: Clan Deletion Is RESTRICT-Guarded](009-clan-deletion-restrict.md), for
  `persons.created_by_clan_id` being SET NULL and for the partition test a new clan foreign key
  would have to satisfy.
- [ADR-031: Cross-Clan Edge Prevention Is an Application-Layer Guarantee](031-cross-clan-edges-app-layer.md),
  the precedent for accepting an application-layer guarantee and writing down what it leaves open.
- [ADR-038: `persons` RLS](038-persons-returning-vs-membership-rls.md), for what happens when a
  policy meets a code path nobody drove through the real seam.
