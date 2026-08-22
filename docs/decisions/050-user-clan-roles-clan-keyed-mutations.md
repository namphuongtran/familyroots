# ADR-050: `user_clan_roles` Takes Clan-Keyed UPDATE and DELETE Only, and Every Reader Stays on the Session It Is On

## Status

Accepted, shipped (2026-08-22), by seed S-052, which split out of S-010 because it carries a
decision. **This ADR ships code**: migration `036_rls_user_clan_roles`, a fourth coverage-guard
set, and three test files. No application module changes, and that absence is the decision.

Every measurement below was taken on **2026-08-22** in the worktree
`.claude/worktrees/backend`, on branch `seed/s-052-clan-roles-session`, from commit `40b5356`.

## Context

### The question, in one sentence

`user_clan_roles` is the table the authorization gate reads. Does it get a policy, and if so,
which session resolves a caller's roles?

### The table is not like the eleven before it, and the difference is what it holds

Every table already inside layer 2 holds **data**: a person, an event, a document, a change
request, an audit row. `user_clan_roles` holds a **capability** — the row that says this user
may administer this clan. Two consequences follow, and they point in opposite directions.

- A policy here does not merely hide rows. It decides what a caller may do.
- The statements that mutate it are the highest-value writes in the product. A cross-clan
  `UPDATE … SET role = 'admin'` is privilege escalation, not a leak.

### What breaks under the migration-027 template, re-measured rather than trusted

Re-measured 2026-08-22 by putting `user_clan_roles` under the 027 predicate in a throwaway
migration `036` and running `backend/tests/integration/test_rls_login_two_clans.py`. Four of its
five cases fail, in two ways that look nothing alike:

```
FAILED test_rls_login_two_clans.py::test_login_resolves_a_multi_clan_user_under_the_rls_seam
FAILED test_rls_login_two_clans.py::test_me_clans_lists_both_clans_under_the_rls_seam
FAILED test_rls_login_two_clans.py::test_onboard_create_writes_a_user_clan_roles_row_with_no_clan_selected
FAILED test_rls_login_two_clans.py::test_onboard_join_writes_a_pending_user_clan_roles_row_with_no_clan_selected
4 failed, 1 passed in 3.77s
```

**Reads fail silently.**

```
E   AssertionError: {'id': 'e0506a08-…', 'email': '…', 'full_name': 'Đa Tộc', 'clan_id': None, ...}
E   AssertionError: set()
```

`POST /auth/login` still answers `200` and reports that the user belongs to nowhere.
`GET /me/clans` returns `[]`. Nothing raises and nothing is logged.

**Writes fail loudly.**

```
E   psycopg.errors.InsufficientPrivilege: new row violates row-level security policy for table "user_clan_roles"
[SQL: INSERT INTO user_clan_roles (id, clan_id, user_id, role, is_approved, approved_by, approved_at, invited_by) …]
```

Both `POST /auth/onboard` branches answer 500.

The line numbers the seed cites were re-read at source the same day and all four still hold:
`app/core/security.py:249-254` (the gate's own read) and `:290` (where it sets the GUC, after
that read); `app/infrastructure/persistence/auth_repository.py:69-88` (`add_membership`) and
`:120-137` (`get_login_profile`); `app/infrastructure/persistence/me_query_port.py:19-42`
(`list_clans`); `app/infrastructure/dependencies.py:192-202` (`get_auth_command_handler` on
`get_db`).

### Every reader and writer of the table, counted

`grep -rn "UserClanRole\|user_clan_role" backend/app --include='*.py'`, run 2026-08-22,
excluding the model file itself. Eleven modules touch it. This table is the census the decision
had to be made against, and it is why the ADR-048 shape does not transfer unchanged.

| # | Site | Session | Clan GUC when it runs | Commands |
|---|---|---|---|---|
| 1 | `app/core/security.py:249-254`, `get_current_clan_id` | `get_db` | **none** — it sets the GUC afterwards at `:290` | SELECT |
| 2 | `app/core/permissions.py:49-54`, `require_role` | `get_db` | set (depends on `get_current_clan_id`) | SELECT |
| 3 | `app/core/permissions.py:95-100`, `RequireClanRole` | `get_db` | set | SELECT |
| 4 | `auth_repository.py:54-61`, `:102-118`, `:120-137`, `:139-148` | `get_db` via `get_auth_command_handler` / `get_auth_query_handler` | **none** | SELECT |
| 5 | `auth_repository.py:69-88`, `add_membership` | `get_db` | **none** | INSERT |
| 6 | `me_query_port.py:19-42` `list_clans`, `:44-66` `get_clan_membership` | `get_db` via `get_me_query_handler` (`dependencies.py:156`) | **none** — neither `/me` route takes `get_current_clan_id` | SELECT |
| 7 | `clan_repository.py:31-39`, `:41-59`, `:61-92`, `:94-119`, `:157-170`, `:226-236` | `get_db` via the clan handlers (`dependencies.py:254`, `:259`) | set | SELECT |
| 8 | `clan_repository.py:136-155` `approve_if_pending`, `:172-188` `delete_role_by_id`, `:190-205` `delete_if_pending`, `:207-224` `change_role_if` | `get_db` | set | **UPDATE, DELETE** |
| 9 | `invitation_repository.py:98-105`, `:129-147`, `:149-170`, `:172-181` | `get_system_db` via `get_invitation_accept_handler` (`dependencies.py:358-362`, ADR-048) | n/a, bypasses | SELECT, INSERT, UPDATE |
| 10 | `claim_repository.py:74-84` `get_role`, `:128-146` `add_role` | `get_system_db` (`dependencies.py:144`, `:149`, ADR-042) | n/a, bypasses | SELECT, INSERT |
| 11 | `platform_admin_query_port.py:82-83`, `:114` | `get_system_db` (`dependencies.py:166-174`) | n/a, bypasses | SELECT |

Two more sites are not application queries but emit SQL against the table:

- `app/models/clan.py:34` declares `Clan.user_roles` as `lazy="selectin"`, so **every** load of a
  `Clan` ORM entity emits a SELECT here. Measured 2026-08-22: `grep -rn "\.user_roles" backend/app
  --include='*.py'` returns no consumer at all, so the collection is loaded and never read. This
  is the same trap S-010 found for `clan_settings` (`clan.py:35`), on the neighbouring line.
- `app/services/notification.py:127`, inside `send_to_clan`, joins the table in raw SQL. Its only
  caller is `app/services/scheduler.py:188`, and the scheduler binds its session to a bare
  `engine.connect()` (`scheduler.py:90`, `:102`), which is not an `RlsSession`, so no seam fires
  and it bypasses.

### Row 8 is the finding this ADR turns on

The four statements in row 8 are keyed on the **primary key alone**. Read at source 2026-08-22:

```
approve_if_pending   UPDATE user_clan_roles … WHERE id = :id AND is_approved = false   (:148-154)
delete_role_by_id    DELETE FROM user_clan_roles WHERE id = :id                        (:182-187)
delete_if_pending    DELETE FROM user_clan_roles WHERE id = :id AND is_approved = false (:199-204)
change_role_if       UPDATE user_clan_roles SET role = … WHERE id = :id AND role = :expected (:217-223)
```

Not one of them carries a `clan_id` predicate. Their clan safety rests entirely on `ucr_id`
having come from `get_user_clan_role(clan_id, user_id)` (`clan_repository.py:31-39`, which **is**
clan-filtered) a few lines earlier in `app/application/clan/handlers.py` — at `:59` for approve,
`:97` for reject, `:130` for change-role and `:172` for remove.

That is a read-then-write pair, not a filter. It is correct today and it is correct by
convention, which is precisely the class of guarantee ADR-008 § 1 built layer 2 to back up. A
`ucr_id` that reaches one of those four statements from anywhere else — a request body, a future
admin tool, a copy-paste — mutates authority in a clan the caller has nothing to do with, and
nothing at the database stops it.

### Why the ADR-048 shape does not transfer

Seed S-052 asks this first, and the answer is no, for a reason that is countable. ADR-048 moved
**one** route of four onto the privileged session, so three of four kept two layers. Here the
clan-less accessors are rows 1, 4, 5 and 6 of the census — six routes (`POST /auth/register`,
`POST /auth/onboard`, `POST /auth/login`, `GET /auth/me`, `GET /me/clans`,
`POST /me/clans/{clan_id}/select`) and, worse, **row 1 is the authorization gate itself**, which
is a shared dependency on every clan-scoped route rather than a route of its own.

`clan_invitations` had one route with no clan and a token standing in for one. `user_clan_roles`
has a whole authentication surface with no clan, because "which clans does this user belong to"
is the question the surface exists to answer.

## Decision

### 1. Migration `036` gives the table four per-command policies, two of them permissive by decision

| Command | Policy | Clause |
|---|---|---|
| `SELECT` | `user_clan_roles_sel` | `USING (true)` |
| `INSERT` | `user_clan_roles_ins` | `WITH CHECK (true)` |
| `UPDATE` | `user_clan_roles_upd` | `USING (…)` and `WITH CHECK (…)`, both the migration-027 predicate |
| `DELETE` | `user_clan_roles_del` | `USING (…)`, the migration-027 predicate |

`ENABLE`, not `FORCE`. Grants already exist (migration `002` table CRUD, `026` functions and
sequences). Reversible.

The permissive halves are written out explicitly rather than omitted. Under RLS a command with
**no** matching policy is denied for a non-bypass role, so omitting them would deny login,
onboarding and every role check — the same mechanism ADR-043 uses deliberately to make
`audit_logs` append-only, used here in reverse.

**This is the mirror of ADR-043, and the mirroring is the argument.** `audit_logs` has
clan-keyed reads and a permissive INSERT because a **record** leaks by being read, and the value
written there is server-assembled. `user_clan_roles` has permissive reads and clan-keyed
mutations because a **capability** leaks by being written. Both tables are half covered; they are
opposite halves, for opposite reasons.

### 2. No handler, repository or route changes the session it runs on

Named by name, because seed S-052 requires that this ADR state what it does to every other
reader and writer of the table. Using the census numbering above:

- **1. `get_current_clan_id`** (`security.py:249-254`) — unchanged, on `get_db`, reading with no
  GUC. Its SELECT is admitted by `user_clan_roles_sel`. It gains **nothing** from this ADR, and
  that is deliberate: see § "Alternatives", first row.
- **2 and 3. `require_role` and `RequireClanRole`** (`permissions.py:49-54`, `:95-100`) —
  unchanged, on `get_db`, with the GUC set. Their reads are SELECTs, so they are unaffected by
  the clan-keyed halves and could not have been broken by them. They gain no DB-level guarantee
  either; their clan safety stays the explicit `UserClanRole.clan_id == clan_id` predicate each
  one already carries.
- **4. `get_user_role`, `get_profile`, `get_login_profile`, `has_pending_membership`**
  (`auth_repository.py:54-61`, `:102-118`, `:120-137`, `:139-148`) — unchanged, on `get_db`,
  clan-less. Admitted by the permissive SELECT. `POST /auth/login` and `GET /auth/me` behave
  byte-identically before and after.
- **5. `add_membership`** (`auth_repository.py:69-88`) — unchanged, on `get_db`, clan-less.
  Admitted by the permissive INSERT. Both `POST /auth/onboard` branches still answer `201`.
- **6. `list_clans` and `get_clan_membership`** (`me_query_port.py:19-42`, `:44-66`) —
  unchanged, on `get_db`, clan-less. `GET /me/clans` still returns every membership, and
  `POST /me/clans/{clan_id}/select` still resolves one.
- **7. The six clan-scoped reads in `clan_repository.py`** — unchanged. `list_users`,
  `get_clan_stats`, `lock_admin_count`, `get_user_clan_role`, `role_is_approved` and `role_of`
  are SELECTs, so they are admitted unconditionally and keep the explicit `clan_id` filters they
  already carry. `role_is_approved` (`:157-170`) and `role_of` (`:226-236`) are the two that key
  on `ucr_id` alone; they read, they do not mutate, and this ADR leaves them uncovered.
- **8. `approve_if_pending`, `delete_role_by_id`, `delete_if_pending`, `change_role_if`** — the
  four statements this migration exists for. They **gain** a DB-level clan predicate. They are
  reached only from `/api/v1/clans/me/users/*` — approve (`app/api/v1/clans.py:161-167`),
  reject (`:180-186`), change-role (`:199-206`) and remove (`:220-226`) — every one of which
  carries `Depends(get_current_clan_id)`, so the GUC is always set when they run. Verified
  green: the full suite is 1340 passed with the migration live.
- **9. The invitation accept path** (`invitation_repository.py:98-181`) — unchanged, and
  **already privileged** since ADR-048, so it bypasses all four policies. Its `promote_if_pending`
  (`:149-170`) is the fifth `ucr_id`-keyed UPDATE in the tree and is the one statement this ADR
  does **not** cover, because bypass is what ADR-048 bought. Its guard remains the 256-bit token.
- **10. The identity-claim path** (`claim_repository.py:74-84`, `:128-146`) — unchanged, already
  privileged since ADR-042, bypasses.
- **11. Platform admin** (`platform_admin_query_port.py:82-83`, `:114`) — unchanged, already
  privileged, bypasses. Its cross-clan counts are the reason it must.
- **`Clan.user_roles`** (`clan.py:34`, `lazy="selectin"`) — unchanged and unaffected. It emits a
  SELECT, which is permissive, so a `Clan` loaded on a clan-less request session still gets its
  role collection populated. Contrast `clan_settings`, whose selectin came back empty after
  migration `035`; nothing consumes either one.
- **The anniversary scheduler** (`notification.py:127` via `scheduler.py:188`) — unchanged and
  unaffected. It bypasses the seam entirely.

### 3. The coverage guard gains a fourth set, rather than this table joining one that passes

`backend/tests/integration/test_rls_activation.py` carried three sets. `user_clan_roles` fits
none of them, so `_CLAN_KEYED_MUTATION_TABLES` is added and asserted by
`test_user_clan_roles_mutations_are_clan_keyed_and_its_reads_are_not`.

Listing it under `_CLAN_ISOLATED_TABLES` would have **passed** that set's assertion, because
that assertion asks whether *some* policy's `USING` reads the GUC and this table's `UPDATE`
policy does. It would then have told every later reader that reads on the authorization table are
confined to one clan, which is false. That is the S-014 finding recurring one table later, and
`.claude/rules/seeds.md` § "A set is a setting too" is the rule it recurred against.

## Alternatives considered

| Alternative | Why not |
|---|---|
| **(a) Move the clan-resolution reads and `add_membership` to the privileged session**, the seed's option (a), i.e. the ADR-048 shape | It is not one route, it is six plus the gate. Rows 4, 5 and 6 of the census mean `get_auth_command_handler`, `get_auth_query_handler` and `get_me_query_handler` all move, taking `POST /auth/register`, `POST /auth/onboard`, `POST /auth/login`, `GET /auth/me`, `GET /me/clans` and `POST /me/clans/{clan_id}/select` fully privileged — so those routes also lose the `audit_logs` read policy (ADR-043) and the `persons` / `clan_memberships` / `branches` policies their `Clan` selectins touch. Row 1 is worse still: `get_current_clan_id` is a shared dependency, so covering it means `Depends(get_system_db)` on **every clan-scoped route**, a second pooled connection per request against `DB_POOL_SIZE=10` / `DB_MAX_OVERFLOW=20` (`app/core/database.py:37-38`). All of that buys read isolation on a table whose read leak is a set of user ids and role strings; the names and emails live in `user_profiles`, which carries no policy at all |
| **(b) Set `app.clan_id` before `get_current_clan_id` runs**, the seed's option (b) | There is no clan to set. Two of the gate's three branches — auto-select for a single-clan user (`security.py:269-271`) and the multi-clan 400 (`:272-274`) — need the cross-clan list before any clan exists. The header branch could set the GUC from the unvalidated header first, and that is ADR-048's rejected hybrid word for word: today `app.clan_id` is only ever a clan the caller has an **approved** membership in (`security.py:249-268` rejects anything else) and every policy in the tree is written against that meaning. It is also circular — the policy deciding whether the caller may read their own role row would be keyed on a value the caller supplied — so it would provide zero isolation for the read it enables. And `GET /me/clans` is cross-clan by design and would still return `[]` |
| **(c) Leave the table outside layer 2 permanently**, the seed's option (c) | Honest, and it was the expected answer until row 8 of the census was read. Four statements that mutate authority are keyed on the primary key alone. A per-command policy covers exactly those four at no cost to any other path, so the honest absence is available for the read half only, and this ADR records it there instead |
| **(d) A "self or same clan" policy**, `USING (clan_id = <GUC> OR user_id = <a new app.user_id GUC>)` | This is the shape that fits the table's two real access patterns, and it clears every one of [ADR-047](047-rls-seam-sets-clan-id-only.md)'s five preconditions on paper. It is rejected on two grounds. **First, the GUC would mean two different things.** On `POST /auth/onboard` the value is the JWT subject; on `POST /auth/register` and `POST /auth/login` there is no authenticated identity at all when the query runs, so it would be a user id the request itself just minted from the identity provider's response. ADR-048 rejected its hybrid for exactly this — a GUC must mean one thing everywhere — and the objection transfers unchanged. **Second, it costs four population sites, not one.** ADR-047 Measurement 4 already counts a second ContextVar, a write in `rls.py:63-65`, a write beside `security.py:290` and a clear at `database.py:81-83`; the login and register paths add two more, inside `app/infrastructure/persistence/auth_repository.py`, which puts a seam writer in adapter code. **Third, its write half is a permissive clause wearing a hat.** `WITH CHECK (… OR user_id = <me>)` admits a self-insert of an approved admin row into any clan, which is the escalation a strict clan-keyed check exists to stop |
| **A deny-all tripwire**, as ADR-042 gives `identity_claims` | ADR-042 chose deny-all because **no** request-role path touches that table. Here nine of the eleven census rows are request-role paths with live traffic. Deny-all breaks login, onboarding, every role check and every clan member route |
| **Add the missing `clan_id` predicate to the four statements in row 8, and skip the policy** | Worth doing and it is not a substitute. Layer 2 exists because layer 1 can be forgotten; a fix that lives only in layer 1 is the thing layer 2 backs up. It is also a change to code seed S-052 was not asked to touch. Recorded as a finding below, not done here |
| **`USING (clan_id = <GUC> OR current_setting('app.clan_id', true) = '')`**, permissive when no clan is selected | ADR-048 priced this one already: it lets **any** clan-less request session read **every** clan's rows, including a route nobody has written yet, and it inverts ADR-008 § 3's default-deny. A permissive `USING (true)` that is written down and asserted is more honest than a predicate that looks like isolation and opens itself |

## Consequences

### What this buys

- The four statements that can grant, revoke or change authority in a clan are stopped at the
  database if they are ever handed a `ucr_id` from outside the clan-filtered read. Proven in both
  directions, at the database layer, in
  `backend/tests/integration/test_rls_phase11_user_clan_roles.py`.
- An UPDATE cannot move a membership row into another clan, which would hand that clan a member
  it never approved. That is the `WITH CHECK` half, and it has its own test.
- **The assertion S-010 named and could not run now exists.** A user who is admin in one clan and
  viewer in another gets `200` from an admin-only route in the first and `403
  insufficient_permissions` in the second, with a second test proving the viewer clan is a real
  membership and not simply invisible.
- No route changed session, so no route lost a layer.

### What this costs, stated plainly

- **Reads on this table have one layer of clan isolation, not two.** The application layer is
  that layer, and it is real: `clan_repository.py` carries an explicit `clan_id` filter on every
  list and count (`:84`, `:96`, `:100`, `:106`), and both permission gates filter on
  `clan_id` as well as `user_id`. But a missed `WHERE clan_id = …` on a SELECT here is not caught
  by the database. This is the same posture ADR-042 accepted for `identity_claims` and ADR-031
  for cross-clan edges, and it is written here rather than implied.
- **The gate's own read gains nothing.** `get_current_clan_id` remains the one query in the
  system whose result decides the GUC and which therefore cannot be protected by the GUC.
- **`promote_if_pending` on the invitation accept path stays uncovered**, because ADR-048 put
  that path on the privileged session. The fifth `ucr_id`-keyed mutation in the tree is the one
  this ADR does not reach.
- **`_CLAN_KEYED_MUTATION_TABLES` is a fourth set in a guard that had three.** Four postures is a
  lot to hold in the head, and the alternative — pushing a name into a set whose assertion it
  passes for the wrong reason — is the defect S-012, S-014 and now S-052 each found once.
- **`test_rls_login_two_clans.py` changed meaning.** It used to prove the table could not be
  covered. It now proves which half of it is not covered, and it is the test that fails if
  someone tightens `user_clan_roles_sel` or `user_clan_roles_ins`.

### A finding this ADR does not act on

The four statements in row 8 should also carry `clan_id` in their own `WHERE` clauses. That is a
layer-1 change in `app/infrastructure/persistence/clan_repository.py`, it is outside seed S-052's
scope, and it does not make this migration unnecessary — the point of layer 2 is that layer 1 can
be forgotten. It is reported to the coordinator as a candidate seed.

## What this ADR deliberately does not decide

- **Whether `app.user_id` is ever added to the seam.** ADR-047 owns that question and its five
  preconditions stand unchanged. Alternative (d) above is a rejection of one use for it, not of
  the GUC in general.
- **The read half of this table.** If the clan-less readers are ever moved off the request
  session, `user_clan_roles_sel` should be tightened and this ADR amended by dated note. The
  guard test says so in its own failure message.
- **`clan_settings`**, closed by S-010 and migration `035`.
- **The platform-admin role**, which is not clan-scoped.
- **`FORCE ROW LEVEL SECURITY`**, which ADR-008 § "Not yet" leaves until every table is covered.

## Related

- Seed **S-052** in [`../SEEDS.md`](../SEEDS.md), which this ADR closes, and seed **S-010**, which
  split it out. Seed **S-015** is unblocked by it.
- [ADR-008: Row-Level Security as Defense-in-Depth Layer-2](008-rls-defense-in-depth.md) — § 3's
  default-deny rule, which the two permissive policies here depart from by decision and with a
  measurement, and Phase 11 in its phase list.
- [ADR-048: Only `POST /invitations/{token}/accept` Moves to the System Session](048-invitation-accept-runs-on-the-system-session.md) —
  the worked precedent, the shape that did not transfer, and the reason `promote_if_pending`
  bypasses these policies.
- [ADR-043: `audit_logs` Is Inside Layer 2 with Per-Command Policies](043-audit-notification-rls-posture.md) —
  the per-command shape this ADR mirrors, with the halves reversed.
- [ADR-042: `identity_claims` Keeps Application-Layer Clan Isolation](042-identity-claims-app-layer-isolation-system-session-lockout.md) —
  the precedent for accepting one layer on a named surface and saying so.
- [ADR-047: The RLS Seam Sets `app.clan_id` Only](047-rls-seam-sets-clan-id-only.md) — the five
  preconditions alternative (d) was measured against.
- [ADR-035: Deterministic Login Membership Selection](035-deterministic-login-membership-selection.md) —
  why `get_login_profile` orders the way it does, and why the login tests assert a specific clan.
- `.claude/rules/seeds.md`, § "A test pins an outcome, not a setting" — the rule the fourth
  guard set and the two-clan role test are both written against.
