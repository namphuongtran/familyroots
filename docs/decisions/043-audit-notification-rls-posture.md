# ADR-043: `audit_logs` Is Inside Layer 2 with Per-Command Policies, `notification_log` Takes the Template Unchanged

## Status

Accepted (2026-08-22). **Nothing is shipped by this ADR.** It is a decision, and a follow-up
migration is the change that carries it. No gate was run, because this file and its index row are
the whole diff.

Every measurement below was taken on **2026-08-22** in
`.claude/worktrees/mobile`, at commit `a955248`.

## Context

### The question, in one sentence

Is a table that only privileged code writes, and that a request handler reads only through a
clan-filtered query, inside RLS layer 2 or outside it?

[ADR-008](008-rls-defense-in-depth.md) does not answer it. It only records that the two tables were
skipped, and gives half a reason for one of them: "`audit_logs` has nullable-clan platform rows +
a super-admin cross-clan reader". `notification_log` is not named there at all.

### What "privileged" means here, because it is not a second credential

ADR-008's Decision § 1 says the system path uses "a separate privileged `SYSTEM_DATABASE_URL`".
**That was never built, and the shipped design says so on purpose:**
`docs/superpowers/specs/2026-07-25-rls-activation-phase1-design.md:119` records that the design
"does NOT require a second DB credential / `SYSTEM_DATABASE_URL`". `grep -rn SYSTEM_DATABASE_URL
backend/` returns nothing, 2026-08-22.

There is one engine and one login role (`backend/app/core/database.py:45`, built from
`settings.DATABASE_URL`). The split is what happens *after* connecting:

| Session | Class | What runs at `after_begin` | Effective role |
|---|---|---|---|
| request | `AsyncRequestSessionLocal` / `RlsSession`, `database.py:56-70` | `SET LOCAL ROLE familyroots_app` + `set_config('app.clan_id', …)`, `rls.py:63-65` | `familyroots_app`, `NOBYPASSRLS` |
| system | `AsyncSessionLocal`, `database.py:49-53` | nothing | the `DATABASE_URL` login role, which bypasses RLS |

So "privileged" in this ADR means "the login role, with no `SET LOCAL ROLE` applied". Anything the
system session can reach, RLS does not touch.

### Measurement 1 — who writes and reads each table, and as which role

Read from the tree on 2026-08-22.

| Path | Table | Session dependency | Effective role | Source |
|---|---|---|---|---|
| `AuditLogHandler`, wired by 13 of the 15 `create_event_dispatcher(db)` sites | `audit_logs` write | `Depends(get_db)` | `familyroots_app` | `event_dispatcher.py:77-90`, `dependencies.py:91, 97, 104, 123, 196, 210, 228, 236, 255, 274, 286, 306, 339` |
| identity-claim command handler | `audit_logs` write | `Depends(get_system_db)` | login role, bypass | `dependencies.py:144-146` |
| platform-admin command handler | `audit_logs` write | `Depends(get_system_db)` | login role, bypass | `dependencies.py:167-171` |
| `GET /api/v1/platform-admin/audit-log`, the **only** reader | `audit_logs` read | `Depends(get_system_db)` | login role, bypass | `dependencies.py:174-177`, `platform_admin_query_port.py:134-149`, `platform_admin.py:94-104` |
| anniversary scheduler, dedup `SELECT` and `INSERT` | `notification_log` | `AsyncSession(bind=conn)` on `engine.connect()` | login role, bypass | `scheduler.py:90, 102, 173, 201` |

`dependencies.py:97` is `_repo_uow`, whose seven callers (`109, 134, 242, 248, 279, 298, 311`) are
all `Depends(get_db)` read handlers, so it is counted as a request site.

**The opening premise is half wrong, and this is the fact that shapes the decision.** It said
"both tables are written by privileged paths, not by request handlers". That holds for
`notification_log` and does **not** hold for `audit_logs`: 13 of 15 dispatcher sites hang off
`Depends(get_db)`, so most audit rows in this system are written by the non-bypass request role.
The audit writer is not a system path. It is the request path, writing a side-effect row inside the
caller's own transaction (ADR-014).

### Measurement 2 — three request routes write an audit row with **no** clan GUC set

The GUC is set in exactly one place: `backend/app/core/security.py:289`, inside
`get_current_clan_id`. A route that does not depend on `get_current_clan_id` leaves the ContextVar
unset, so `apply_rls_context` sends the empty string (`rls.py:64`) and the policy's
`nullif(…)::uuid` is NULL.

| Route | Audit row written | Clan dependency | Source |
|---|---|---|---|
| `POST /api/v1/auth/register` (unauthenticated) | `clan.create` or `clan.join_request` | none | `auth.py:46-49`, `auth/handlers.py:154, 189` |
| `POST /api/v1/auth/onboard` | same | `get_current_user` only | `auth.py:64-68` |
| `POST /api/v1/invitations/{token}/accept` | `InvitationAccepted` | `get_current_user` only | `invitations.py:89-93`, `invitation/handlers.py:129` |

`backend/app/api/v1/auth.py:17` imports `get_current_user` and nothing else from
`app.core.security`, so no route in that file can have a clan GUC.

Each of the three writes an audit row whose `clan_id` is a real clan. Under the migration-027
predicate as a `WITH CHECK`, the comparison is `<real clan> = NULL`, which is NULL, which is not
true, so the insert is **rejected**. Registration, onboarding, and invitation acceptance would all
start failing. That is the concrete form of the seed's warning that a policy assuming a request
role will break the writers.

### Measurement 3 — `audit_logs` inserts carry `RETURNING`, so the SELECT policy sees them

[ADR-038](038-persons-returning-vs-membership-rls.md) found that Postgres matches a `RETURNING`
row against the **SELECT** policy, and that SQLAlchemy's `eager_defaults="auto"` appends
`RETURNING` whenever a server default exists. `persons` was fixed in the ORM
(`backend/app/models/person.py:33`). Nothing else in `backend/app/` sets `__mapper_args__`; that
grep returns one hit, 2026-08-22.

Measured on 2026-08-22, SQLAlchemy 2.0.51, against the `postgresql` dialect:

```
AuditLog eager_defaults setting = auto | prefers eager = True
Person   eager_defaults setting = False | prefers eager = False
server_default cols on audit_logs: ['created_at']
```

So every ORM insert into `audit_logs` appends `RETURNING created_at`, and any SELECT policy on the
table is applied to the row being returned. **The same collision ADR-038 fixed on `persons` is
sitting live on `audit_logs`,** unexercised only because the table carries no policy today.

### Measurement 4 — `notification_log` has exactly two accessors, both in the scheduler

`grep -rn "notification_log\|NotificationLog" backend/app` returns five hits on 2026-08-22:
`models/__init__.py:15, 36`, `models/notification_log.py:1, 14`, `services/scheduler.py:173`, and
`services/scheduler.py:201`. There is no query port, no repository, and no route.
`docs/contracts/push-notifications.md:135` states it: "`notification_log` is not queryable by
clients today."

Its `clan_id` is `NOT NULL` with `ON DELETE RESTRICT` (`models/notification_log.py:17-21`), which
[ADR-009](009-clan-deletion-restrict.md) lists among its eleven RESTRICT foreign keys. It has none
of `audit_logs`' problems.

### What the two tables actually have in common, and it is not the writer

Both were skipped for reasons about their **writers**. The reason layer 2 exists is about
**readers**: ADR-008's Context says it in one line, "so that a future missed `WHERE clan_id = …`
cannot leak cross-clan data". A missed filter is a defect in a reader. Whether the writer is
privileged is beside the point.

That reframing is what makes the answer clean, and it is the thing this ADR contributes.

## Decision

### 1. The general answer: the reader decides, so both tables are inside layer 2

A table is inside layer 2 when a request-role session can reach its rows. Both can:
`familyroots_app` holds `SELECT, INSERT, UPDATE, DELETE` on **all** tables in `public`
(`002_rls_documents_pilot.py:45`, plus default privileges at line 49), and that grant is
table-blind. So today, a clan-facing handler that forgot its `WHERE clan_id` could read every
clan's audit rows, and nothing at the database would stop it.

The privilege of the writer changes **the shape of the policy**, never the membership question.

### 2. `notification_log` takes the migration-027 template, unchanged

```sql
ALTER TABLE notification_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY notification_log_clan_isolation ON notification_log
  USING      (clan_id = nullif(current_setting('app.clan_id', true), '')::uuid)
  WITH CHECK (clan_id = nullif(current_setting('app.clan_id', true), '')::uuid);
```

Three facts make the template correct here and none of them is in doubt: `clan_id` is `NOT NULL`,
so there is no row the predicate mishandles; the only accessor is the scheduler on a bypassing
session, so nothing breaks; and no request path touches the table, so nothing regresses.

**The policy is inert today, and that is accepted deliberately.** It guards a reader that does not
exist yet. The alternative is a permanent exemption row in the clan-owned table list, which is
a second place to record the same fact and therefore a second place to be wrong. A cheap correct
policy beats a permanent exception.

### 3. `audit_logs` takes per-command policies, not the template

```sql
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;

CREATE POLICY audit_logs_sel ON audit_logs FOR SELECT
  USING (clan_id = nullif(current_setting('app.clan_id', true), '')::uuid);

CREATE POLICY audit_logs_ins ON audit_logs FOR INSERT
  WITH CHECK (true);

-- deliberately no UPDATE policy and no DELETE policy
```

Each of the three lines answers a measurement above:

- **`audit_logs_sel` is the whole point.** It is the guard against a future clan-facing audit
  reader that forgets its filter. It is what makes the table a member of layer 2 rather than an
  exception to it.
- **`audit_logs_ins` is permissive because Measurement 2 says it must be.** The writer is the
  request role, on three routes that have no clan context by design, and on a further thirteen
  dispatcher sites where the row's clan comes from the domain event rather than from the GUC. A
  `WITH CHECK` here buys nothing: the value is derived from an `AuditableEvent`, not from client
  input, and the leak direction layer 2 exists for is read, not write.
- **The absent `UPDATE` and `DELETE` policies are not an omission.** With RLS enabled, a command
  with no matching policy is denied for a non-bypass role. So the request role can append to the
  audit trail and can never edit or erase it. `audit_logs` is documented as an "immutable log of
  all write actions" at `backend/app/models/audit_log.py:1`; this makes the database enforce it.
  That is a guarantee the table did not have before and it is a second reason to bring it inside.

### 4. NULL-`clan_id` rows are retained, unfiltered at write, and invisible to every clan

This is the question the seed asked, so the answer is stated in full.

| Row | Kept in the table | Visible to the request role | Visible to the platform-admin surface |
|---|---|---|---|
| `clan_id` = a live clan | yes | only to that clan | yes |
| `clan_id` NULL, a platform-level action | yes | **no clan sees it** | yes |
| `clan_id` NULL because ADR-009's `SET NULL` fired on clan delete | yes | **no clan sees it** | yes |

Nothing is deleted, nothing is rewritten, and no insert is filtered. What changes is visibility to
one role that has no reader today.

Hiding those rows from every clan is the correct reading of the column's own comment
(`models/audit_log.py:18-21`): a platform-level action has no clan, so no clan owns it; and a row
whose clan was deleted has no clan left to show it to. `NULL = <anything>` is NULL in SQL, so the
`audit_logs_sel` predicate hides them without a special case.

### 5. ADR-030's platform audit surface is untouched, and here is the mechanism

[ADR-030](030-platform-audit-newest-first-retention.md) requires the super-admin audit log to
paginate newest-first across **all** clans, including the unfiltered case that "returns rows across
all clans, not only `clan_id IS NULL` platform events". That reader is
`SqlAlchemyPlatformAdminQueryPort.get_audit_log` (`platform_admin_query_port.py:134-149`), reached
through `get_platform_admin_query_handler`, which depends on `get_system_db`
(`dependencies.py:174-177`). The system session never issues `SET LOCAL ROLE`, so RLS does not
apply to it at all.

`audit_logs_sel` therefore cannot narrow that surface. ADR-030's retention rule (both tables
retained indefinitely, no purge) is likewise untouched: neither policy deletes anything.

### 6. The migration must fix the `RETURNING` collision in the ORM, following ADR-038

Because of Measurement 3, adding `audit_logs_sel` **without** an ORM change would reject exactly
the writes § 3 was shaped to protect: the `RETURNING created_at` row is matched against the SELECT
policy, and for a no-GUC or NULL-clan insert that predicate is NULL. The permissive
`audit_logs_ins` would accept the write and `audit_logs_sel` would then reject the row on its way
back, which is ADR-038's failure verbatim.

The fix is ADR-038's fix, on the same grounds it gave: change the ORM, not the policy.

```python
# backend/app/models/audit_log.py
__mapper_args__ = {"eager_defaults": False}  # noqa: RUF012
```

`created_at` is the only server default on the table, the value is never read back by
`AuditLogHandler` (it calls `self._db.add(...)` and returns, `event_dispatcher.py:77-90`), and both
session makers set `expire_on_commit=False`, so nothing observes the difference. The database stays
the timestamp authority.

**This is a decision, not a suggestion.** A policy on `audit_logs` without this line is a broken
build, and it will not be visible in a unit test — ADR-038 records that its own instance stayed
invisible "until a test drove an HTTP write through a real `RlsSession`".

## What the migration is obliged to build

Read this section as the specification; it is what "the two tables may get different answers"
resolved to.

1. **One reversible migration** enabling RLS and creating: `notification_log_clan_isolation` as in
   § 2; `audit_logs_sel` and `audit_logs_ins` as in § 3, and no `UPDATE` or `DELETE` policy.
2. **The ORM line in § 6**, in the same commit as the migration. Not a follow-up.
3. **`backend/tests/integration/test_rls_activation.py:180-187`** — extend the pinned coverage set
   from the six tables it names today to eight. That assertion is the thing that fails first if the
   migration lands without a policy.
4. **Two-sided isolation at the database layer** for both tables: clan A reads its own row under
   `familyroots_app` with the GUC set, clan B does not see it, and the reverse. Assert against the
   session, not through the API — there is no API for either table, so an API-only test would prove
   nothing at all here.
5. **The three NULL/no-GUC audit write paths, driven over HTTP** through a real `RlsSession`:
   `POST /auth/register`, `POST /auth/onboard`, `POST /invitations/{token}/accept`. This is the
   test that catches the § 6 collision. Without it, § 6 is an unproven claim.
6. **A NULL-`clan_id` row is invisible to a clan and visible to the platform surface** — one
   assertion each. This is the pair that proves § 4 and § 5 together.
7. **Immutability**: under `familyroots_app` with a valid GUC, an `UPDATE` and a `DELETE` against
   an own-clan audit row each affect zero rows. This is the only proof that § 3's absent policies
   do what § 3 claims.
8. **The scheduler still crosses clans**: it writes `notification_log` rows for two clans in one
   run. It bypasses, so this must keep passing unchanged; it is the test a naive policy breaks.
9. **A planted inversion on each policy.** Replace the predicate with `true`, watch the named
   two-sided test fail, restore. A green suite passes over a policy that protects nothing.

## Consequences

### What this buys

- The two tables stop being exceptions. Afterwards, eight of fourteen clan-owned tables carry a
  policy, and the coverage gate can be written without a permanent exemption list beside it.
- A future clan-facing audit endpoint is guarded before it is written, which is the only order in
  which a defense-in-depth layer is ever cheap.
- The audit trail becomes immutable at the database for the request role, not only by convention.

### What this does not buy, stated plainly

- **Neither policy protects a reader that exists today.** `audit_logs` has one reader and it
  bypasses; `notification_log` has none. Both policies are inert on 2026-08-22. Anyone measuring
  "does this change any response" will correctly find that it does not.
- **A clan can still write an audit row naming another clan**, because `audit_logs_ins` is
  permissive. Accepted: the value comes from a domain event assembled server-side, and no
  application code lets a client choose it.
- **Nothing here makes the in-process dispatcher durable.** An audit row is written inside the
  caller's transaction (ADR-014) and is lost with it on rollback. That was already true.
- **The system session still bypasses everything.** Layer 2 protects the request path only. A
  defect in `platform_admin_query_port.py` or in the scheduler is caught by neither policy.

## Alternatives considered

| Alternative | Why it was rejected |
|---|---|
| Copy the migration-027 template onto `audit_logs` | It breaks the three routes in Measurement 2. `POST /auth/register` is the whole registration flow |
| `USING (clan_id = GUC OR clan_id IS NULL)` — the predicate "nullable on purpose" invites | It makes **every** platform-level action and every orphaned row readable by **every** clan. That is strictly worse than hiding them, and it is the shape a reader is most likely to reach for, which is why it is named here rather than left out |
| Leave both tables outside layer 2 and record it as "not verified" | The coverage gate would need two permanent exemptions, and each is a second place to record a fact. `notification_log` in particular has no property that justifies an exception, only an absence of readers |
| Put `audit_logs` inside but `notification_log` outside, on the grounds that nothing reads it | Symmetrical to the row above, and the same objection. "No reader yet" is a reason to add the guard cheaply, not to skip it |
| Fix the `RETURNING` collision by widening `audit_logs_sel` instead of the ORM | ADR-038 rejected exactly this on `persons` and the reasoning transfers: a policy widened to admit a write stops describing the read rule it exists for |
| `FORCE ROW LEVEL SECURITY` on either table | Out of scope. ADR-008 puts it after full coverage, and it would make the table owner subject to its own policies, which changes what migrations can do |

## What this ADR deliberately does not decide

- **Audit retention.** ADR-030 owns it and its answer is "indefinitely, by design". Neither policy
  deletes.
- **Whether a clan-facing audit endpoint should exist.** `audit_logs_sel` makes one safe to build;
  it does not argue for building one.
- **A notifications history API.** `docs/contracts/push-notifications.md:135` says there is none,
  and this ADR does not change that.
- **`identity_claims`**, which has no `clan_id` at all. That is ADR-042.
- **The list of tables the coverage gate calls clan-owned**, and where that list lives.
- **`FORCE ROW LEVEL SECURITY`**, and the final sweep ADR-008 leaves open.
- **Whether ADR-008's `SYSTEM_DATABASE_URL` sentence should be repaired.** It is a dated record of
  what was decided; the shipped design at `specs/2026-07-25-rls-activation-phase1-design.md:119`
  is what is true. This ADR notes the disagreement rather than editing an accepted ADR.

## Related

- [ADR-008](008-rls-defense-in-depth.md) — the layer this joins, and the ADR whose "not yet" list
  named `audit_logs` without settling it.
- [ADR-038](038-persons-returning-vs-membership-rls.md) — the `RETURNING`/SELECT-policy collision,
  found on `persons` and shown here to be live on `audit_logs`. § 6 above is its precedent applied.
- [ADR-030](030-platform-audit-newest-first-retention.md) — the platform audit surface and the
  retention rule, both preserved by § 5.
- [ADR-009](009-clan-deletion-restrict.md) — why `audit_logs.clan_id` is `SET NULL` while
  `notification_log.clan_id` is `RESTRICT`, which is the root of the two tables differing.
- [ADR-014](014-uow-in-transaction-domain-events.md) — why the audit row is written by the request
  transaction, which is the fact that made the template wrong.
- [`../architecture/notifications-scheduler.md`](../architecture/notifications-scheduler.md) — the
  scheduler topology, the advisory lock, and the bound-connection session that bypasses RLS.
- [`../contracts/push-notifications.md`](../contracts/push-notifications.md) § 6 — the delivery log
  and the statement that no client can query it.
