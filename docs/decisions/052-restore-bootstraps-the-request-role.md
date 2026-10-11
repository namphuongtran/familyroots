# ADR-052: A Restore Bootstraps the `familyroots_app` Role and Its Grants, and the Drill Proves It Two-Sided

## Status

Accepted, shipped (2026-08-22). The failure was measured first and
declining to repair it, because the repair contained this decision.

**Amended 2026-10-11 (#283): the bootstrap also replays migrations `041`, `042` and `043`, so a
restore into a Supabase project works, and it may be run there as `postgres`.** See
[the amendment](#amendment-2026-10-11-283-a-restore-into-a-supabase-project).

**This ADR ships operations code, not application code**: `scripts/restore_bootstrap_role.sql` (new)
and a fourth check in `scripts/restore_drill.sh`. **No backend file changed**, and that absence is
part of the decision. Section "What was considered and rejected" says why a migration was the wrong
place for it.

> **Amended 2026-10-11 (#283).** The amendment changed backend files, all of them tests: a new
> integration module, the Supabase-shaped fixture it reuses, and the scripts guards. No application
> code and no migration changed, so the decision above still holds.

Every measurement below was taken on **2026-08-22** in the worktree `.claude/worktrees/design`, on
branch `seed/s-057-restore-role-bootstrap`, from commit `8fb930a`.

## Context

### The question, in one sentence

A recovery restores a dump into a cluster that never held the `familyroots_app` role. Where does the
role, and the privilege behind it, come from?

### The failure, measured rather than argued

A dump taken at chain head, restored into a second Postgres container whose cluster held only the
`postgres` role, produced this:

```
==> tree query check (get_family_tree_flat)
  OK   — get_family_tree_flat returned 3 row(s) for person 22222222-2222-2222-2222-222222222221
DRILL: PASS
```

Exit code `0`. Then, on that same restored database:

```
BEGIN
ERROR:  role "familyroots_app" does not exist
psql exit: 1
```

Re-measured for this ADR on 2026-08-22 against the current head `036_rls_user_clan_roles`, with
`scripts/` byte-identical to `main` (`git diff --exit-code -- scripts/` clean). The drill first measured
it the same day at head `035_rls_clan_settings`. The full record is in
[`../ops/backup-restore.md`](../ops/backup-restore.md).

### Why that single statement breaks the whole product

`settings.RLS_ENABLED` defaults to `True` (`backend/app/core/config.py:71`), and
`apply_rls_context` issues `SET LOCAL ROLE familyroots_app` at the start of **every** request
transaction (`backend/app/core/rls.py:63`). The restored database is **armed but unusable**: 14
tables have RLS enabled and 21 policies exist, and there is no role to switch to and no grant behind
it. Every clan-scoped request fails.

### What a single-database dump can and cannot carry

Counted 2026-08-22 in both databases, source against restored:

| | source `familyroots_s057_head_stage` @5432 | restored `familyroots_restore_drill` @5433 |
|---|---|---|
| base tables | 18 | 18 |
| grant rows to `familyroots_app` | **72 on 18 tables** | **0** |
| `familyroots_app` exists in the cluster | **yes** | **no** |

The reason is structural, not a bug in either script. **A role is a cluster object and a grant is a
database object.** `scripts/db_backup.sh:40` runs `pg_dump --format=custom --no-owner
--no-privileges`, so the archive names no role and carries no `GRANT`. `pg_restore` emitted no
warning at all, because the policies target `PUBLIC` and nothing in the archive referred to the role.

### Why the drill did not notice

All three existing checks connect as the superuser that created the scratch database, and a
superuser bypasses RLS. Every one of them passes on a database the application cannot open.

## Decision

**Four parts. Read them together; each one alone leaves the failure open.**

1. **The restore path owns the bootstrap, and it lives in one file.**
   `scripts/restore_bootstrap_role.sql` creates the cluster-wide role, guarded by the same
   `IF NOT EXISTS` block migration 002 uses, and replays the seven grant statements from
   `backend/migrations/versions/002_rls_documents_pilot.py:44-50` and
   `backend/migrations/versions/026_rls_activation_grants.py:30-37`. Every statement is idempotent.

   > **Amended 2026-10-11 (#283).** The file now also replays `041`, `042` and `043`, for a restore
   > into a Supabase project, and declares four `ALTER TABLE ... DISABLE ROW LEVEL SECURITY`
   > statements besides its role and grant DDL. See
   > [the amendment](#amendment-2026-10-11-283-a-restore-into-a-supabase-project).

2. **It runs after `pg_restore`, not before.** `GRANT ... ON ALL TABLES IN SCHEMA public` needs the
   tables to exist. The current dumps carry no `GRANT`, so the restore itself does not need the role,
   and nothing is gained by creating it first. Running the file before the restore as well is
   harmless and insufficient.

3. **`scripts/restore_drill.sh` runs the bootstrap and then checks the outcome itself**, as check 4.
   The check drops to the request role, sets the `app.clan_id` GUC, and counts `persons` twice: once
   under the clan that owns the data and once under a clan that owns nothing. It passes only when the
   first count is above zero and the second is exactly zero.

4. **`DRILL: PASS` now means the application can use the restored database.** That sentence is the
   decision. It was not true before, and every earlier `PASS` in the drill log must be read with that
   in mind.

### The failure direction this ADR closes

**It closes the silent direction.** The defect was never that a restore lost the role — that is
structural and expected. The defect was that **nothing said so.** A restore produced a database that
failed every request, and the tool built to check restores reported success and exited `0`. A loud
failure at recovery time is recoverable in minutes. A green drill that is wrong is discovered by the
first user request after a real disaster.

### What happens when the bootstrap is absent

**The drill prints `DRILL: FAIL` and names the missing role, and exits 1. It does not warn, and it
does not skip.** Checks 1 and 3 already warn-and-continue for reasons that are defensible: an old
dump is still a valid backup, and an empty database has no tree to walk. **This one never warns for a
missing role or a missing grant**, because there is no state of the world in which a database the
application cannot open is an acceptable restore.

Verbatim, with the bootstrap call deleted from the script, 2026-08-22:

```
==> request-role check (SET LOCAL ROLE familyroots_app)
  FAIL — role "familyroots_app" does not exist in this cluster; every clan-scoped request would fail
DRILL: FAIL (1 check(s) failed)
```

Exit code `1`. The check has exactly one WARN branch, and it is a different question: a restored
database with **no `clan_memberships` rows** cannot demonstrate isolation two-sided, because there is
no owning clan to compare against. There it proves the role can query `persons` at all and says
plainly that isolation was not proven. A missing role or a missing grant still fails in that branch.

## What was considered and rejected

### A. A `pg_dumpall --roles-only` companion object beside each dump

Rejected on two counts, either of which is enough.

- **It does not reach the end state.** A roles dump carries the role. It does not carry the 72 grant
  rows, which are per-database and which `--no-privileges` drops. Probe B on 2026-08-22 measured what
  the role alone buys: `ERROR: permission denied for table persons`.
- **It puts cluster credential material in the backup bucket.** `pg_dumpall --roles-only` emits every
  role in the cluster, including the provider's, with their password hashes. The blast radius of a
  leaked backup would grow from clan data to cluster credentials. `docs/ops/secrets.md` owns that
  boundary and this would cross it for no gain.

### B. A documented step a human runs before `pg_restore`

Rejected as the **only** mechanism, and kept as part of the chosen one. A human step cannot be
checked by the drill, so `DRILL: PASS` would go on meaning less than it says, which is the whole
defect. It is also the step most likely to be skipped during an incident. The documentation still
exists, in [`../ops/backup-restore.md`](../ops/backup-restore.md), because a production recovery is
run by a person and they need the command.

### C. An idempotent bootstrap in the drill plus a production variant — **chosen**

Chosen, with one change to how the seed framed it. There is no separate "production variant". The
same file is the production step, run by hand against the restored database. **Two mechanisms that
mean to do the same thing are two places to drift**, and this ADR exists because of a drift between
what a script did and what the application needed.

### D. Rebuild the schema by running the Alembic chain, then restore `--data-only`

The fourth shape, and the one the seed asked to be considered before settling: the chain already
creates the role and the grants, so run the chain into the target database and restore only data.
Considered seriously, because it makes the migrations the single source of truth with no copying at
all. **Rejected on four counts.**

- **It stops testing the backup.** It tests the repository's schema plus the dump's data. A dump
  whose schema section is corrupt would pass. The drill exists to test the archive.
- **It only works when the dump sits exactly at head.** The drill deliberately treats an older dump
  as valid, warn-not-fail (`scripts/restore_drill.sh`, check 1), and two of the three recorded drill
  results restored a dump at `016_document_soft_delete` against a later head. This shape would fail
  both.
- **It needs the repository, `uv`, and a working Python toolchain at recovery time.** A restore
  should need `psql` and the archive.
- **It needs `--data-only --disable-triggers` and a hand-edited TOC to skip `alembic_version`**
  (the exact commands are in `../ops/backup-restore.md`, the staging build). That is more
  moving parts in the one procedure that must have fewest.

**What it is still good for**, and this is recorded rather than discarded: it is exactly how a
head-at-chain staging database gets built for a drill. Both the drill and the repair used it for that.

### E. Stop passing `--no-privileges`, so the dump carries its own grants

The most attractive of the rejected shapes, because the grants would then come from the source
database, which the chain wrote, with nothing copied and nothing to drift. **Rejected on three
counts.**

- **It repairs nothing already in the bucket.** Every existing object was dumped with
  `--no-privileges`. Restoring one would give a role with no grants, which is Probe B's
  `permission denied for table persons`. Rotation means that window lasts 7 days for daily objects
  and 4 weeks for weekly ones.
- **It would fail hard on a provider cluster.** A dump from Supabase carries grants to roles like
  `anon`, `authenticated`, and `service_role`. Restoring that into a plain Postgres cluster makes
  `pg_restore --exit-on-error` abort. Probe D measured the same shape on 2026-08-22 with
  `familyroots_app`: `pg_restore: error: ... role "familyroots_app" does not exist`, exit `1`.
- **It changes what the backup contains**, which is a second decision about what may leave the
  provider, and it is not needed to reach the end state.

**It is not incompatible with the chosen shape.** If `db_backup.sh` ever drops `--no-privileges`, the
bootstrap file keeps working: its statements are idempotent and the role would already exist. Only
the ordering in part 2 above would need to move.

## Consequences

### What is now true

- A restore into a cluster that never held the role produces a database the application can open.
  Measured 2026-08-22 into a container with `system_identifier` `7676709582699040807`, one non-builtin
  role (`postgres`), and `familyroots_app` absent before the restore: 72 grant rows on 18 tables
  afterwards, and 3 persons visible under the owning clan against 0 under a clan that owns nothing.
- `DRILL: PASS` is now evidence about the application, not only about the schema.
- The drill is unchanged for a same-cluster run, where the role already exists. Confirmed 2026-08-22
  on the dev cluster: `DRILL: PASS`, exit 0, and `family_roots` untouched.

### The drift this creates, stated plainly rather than waved away

`scripts/restore_bootstrap_role.sql` holds a copy of what migrations 002 and 026 do. **Nothing
enforces that they stay equal.** Three things reduce the cost, and none of them removes it:

> **Amended 2026-10-11 (#283).** The file now also copies `041`, `042` and `043`, and the first
> bullet below no longer holds for all of it: section 6 names four tables, the ones `043` names. A
> table the chain later leaves outside layer 2 needs a line there, in the same pull request as its
> migration. `backend/tests/integration/test_restore_bootstrap_on_supabase_shape.py` is a second
> backstop, for the three Supabase sections. See
> [the amendment](#amendment-2026-10-11-283-a-restore-into-a-supabase-project).

- **The copy is not a list of tables.** All seven statements are schema-wide
  (`ON ALL TABLES IN SCHEMA public`, `ON ALL FUNCTIONS`, `ON ALL SEQUENCES`) plus the matching
  `ALTER DEFAULT PRIVILEGES`. A new table, a new function, or a new sequence is covered with no edit.
  The copy goes stale only if a migration changes the **privilege set itself**.
- **Check 4 is the backstop, and it asserts an outcome.** It does not count grant rows, which is a
  setting the bootstrap already guarantees. It runs a real query as the real role and reads which
  rows come back. A missing `SELECT` or a missing `EXECUTE` surfaces as `permission denied` and turns
  the drill red. Measured 2026-08-22 by deleting the grants from the bootstrap and keeping the role:
  `FAIL — ERROR:  permission denied for table persons`, `DRILL: FAIL`, exit 1.
- **The rule is written where the change happens.** The bootstrap file says any migration that
  changes what `familyroots_app` may do must change it in the same pull request.

**What the backstop does not catch**: a privilege class no query in check 4 exercises, `TRUNCATE`
being the clearest example, and a second schema beside `public`. Neither exists today. If one
arrives, the migration adding it must extend the bootstrap, and check 4 will not remind anyone.

### The role name is spelled out, and that is a finding rather than a shortcut

`settings.RLS_APP_ROLE` (`backend/app/core/config.py:72`) reads like a knob. It is not one: migrations
002 and 026 hardcode `familyroots_app` in `_ROLE`, so a cluster built by the chain only ever holds
that role. The bootstrap file spells it out for the same reason, and says so in its header. Making the
name genuinely configurable is a backend change and is not this ADR's.

### What this ADR does not change

`db_backup.sh` still dumps with `--no-owner --no-privileges`. No RLS policy changed. No migration was
added, and the fenced `backend/**` tree is untouched.
**Amended 2026-10-11 (#283):** still no policy and no migration. The amendment's bootstrap turns RLS
off on four tables, which restores the state `043` left, and it changed backend tests. Production has still never been dumped or
restored, which stays an open gap in [`../ops/backup-restore.md`](../ops/backup-restore.md).

## Amendment 2026-10-11 (#283): a restore into a Supabase project

### What was wrong

[ADR-066](066-the-application-database-lives-in-the-supabase-project.md) moved the application
database into the Supabase project, and the chain gained three migrations whose work a dump does not
carry. The restored `alembic_version` already reads head, so none of them runs again:

- **`041`** grants the migrating login `SET` on `familyroots_app`. Supabase's `postgres` is not a
  superuser. As the role's creator it holds ADMIN without SET, so without the grant every request
  fails with `permission denied to set role "familyroots_app"`. Role membership is a cluster
  object, and the dump has none.
- **`042`** revokes everything `anon` and `authenticated` hold in `public`. `pg_restore
  --no-privileges` creates every table as the restoring login, so the login's default privileges
  hand both roles whatever the project's defaults grant, ALL at worst. `user_profiles` has no RLS,
  so the Data API could then read every user's email.
- **`043`** turns RLS off on `alembic_version`, `clans`, `user_profiles` and `user_fcm_tokens`. The
  project's `ensure_rls` event trigger fires on every `CREATE TABLE` that `pg_restore` issues, so
  the restore turns RLS back on for exactly those four, and the request role reads no row from them.

The file also said "Run as a superuser", and a Supabase project offers none.

### What changed

1. **The file replays all three**, as sections 4, 5 and 6, copied from the migrations. Section 4
   checks `pg_has_role(current_user, 'familyroots_app', 'SET')` first, so it grants nothing where
   the login can already enter the role. It names the login through `format('%I')` and never
   writes `CURRENT_USER`, for the `supautils` crash `041` records. Section 5 skips a role that does
   not exist. Section 6 is `ALTER TABLE IF EXISTS ... DISABLE ROW LEVEL SECURITY` on 043's four
   tables, and on no other.
2. **It may run as one of two logins.** On plain Postgres, a superuser, as before. On a Supabase
   project, `postgres`, the login the application and the migrations use, which holds CREATEROLE
   and ADMIN on `familyroots_app`. Run it as the login that ran `pg_restore`, because section 5 can
   change only that login's default privileges.
3. **On plain Postgres as a superuser, the three new sections change nothing.** A superuser may
   already `SET ROLE`, there is no `anon` or `authenticated`, and RLS is already off on the four
   tables. The drill restores into plain Postgres and is unchanged.
4. **`backend/tests/unit/test_scripts_sql_is_sanctioned.py` gains a class, `rls_off`,** split from
   `policy`, and sanctions this file for `role`, `grant` and `rls_off`. Sanctioning `policy` would
   also have admitted `DROP POLICY` and `CREATE POLICY` here.
5. **A test restores the chain into a Supabase-shaped database and reads the outcomes.**
   `backend/tests/integration/test_restore_bootstrap_on_supabase_shape.py` dumps the migrated chain
   with `--no-owner --no-privileges`, restores it as a non-superuser `CREATEROLE` login into a
   database where `anon` and `authenticated` hold Supabase's legacy default grants and `ensure_rls`
   is installed, and runs this file twice with `psql` as the same login. It reads, by running
   statements: the login enters the request role and each clan sees only its own rows; both Data
   API roles are refused every table privilege but `REFERENCES` on every relation, and on a table
   and a sequence created afterwards; the request role reads a row from each of the four tables. A fourth reading compares every
   table's RLS state with the dump's, and a fifth runs the file twice on plain Postgres as a
   superuser and finds no membership added. Backend CI installs `postgresql-client-18` for it,
   because the runner's own `pg_dump` is 16 (#282).

### Measured 2026-10-11

On the working tree over `3ef0b68`, branch `fix/283-restore-replays-041-043`.

- Against the file as it stood before this amendment, the test failed all three outcomes:
  `42501: permission denied to set role "familyroots_app"` for both clans; `INSERT audit_logs`
  reaching a `NOT NULL` check, so past the privilege layer, among 34 tries `anon` was not refused;
  and `ran, 0 row(s)` from each of the four tables.
- Removing section 4, 5 or 6 alone failed only the tests that read that section's outcome. Removing
  only the global default-privilege revokes failed only the `global` shape's created-afterwards
  test, and removing only the per-schema ones failed only the `per_schema` shape's. Adding
  `DISABLE ROW LEVEL SECURITY` on `persons` failed the RLS-state comparison. Dropping section 4's
  `SET` check failed the plain-Postgres test, which found a self-grant added for the superuser.
- Narrowing the table revoke to `SELECT, INSERT`, or to every privilege but `MAINTAIN`, or to every
  privilege but `TRUNCATE`, failed the every-relation test. Narrowing the per-schema default revoke
  to `SELECT, INSERT` failed the `per_schema` shape's created-afterwards test.
- **Four of section 5's statements, and one privilege, have no reading.** Removing all four together
  left every test green. The chain creates no sequence, so `REVOKE ALL ON ALL SEQUENCES` acts on
  nothing yet. `PUBLIC` keeps Postgres's default EXECUTE on functions, which `anon` inherits, so
  `REVOKE ALL ON ALL ROUTINES` and the two default-privilege revokes on routines change nothing a
  call can show. And a revoke that leaves `REFERENCES` stays green, because a foreign key needs a
  table to declare it on and these roles may create none in `public`. `042` carries all of it, and
  the file stays equal to `042`.

### What it still does not cover

- **A project that never held `familyroots_app`.** There section 1 creates the role, which gives
  `postgres` its creator's ADMIN, and section 4 grants SET. That is `041`'s own reading of 2026-10-10,
  not a measurement of this file: the role is a cluster object shared with the rest of the suite, so
  the test copies a creator's options onto the existing role.
- **Which schemas a backup holds**, and so whether a production dump restores at all. A dump taken
  with no `--schema` carries Supabase's own schemas, and on the hosted project `public` also holds
  `rls_auto_enable`, the function behind `ensure_rls`. That is #285. This file's test restores only
  what the chain creates.
- **A mechanical check that the file stays equal to the migrations.** The rule in its header now
  names five migrations, and still nothing enforces it. § Consequences above still owes that.

## Sources

- `scripts/db_backup.sh:40` — the `pg_dump` line that drops owners and privileges.
- `scripts/restore_drill.sh` — the drill, its four checks, and the bootstrap invocation.
- `scripts/restore_bootstrap_role.sql` — the bootstrap itself.
- `backend/migrations/versions/041_grant_app_role_to_login.py:64-87`,
  `042_close_data_api_on_public.py:69-98`, `043_rls_off_outside_layer_2.py:51-56` — what the
  2026-10-11 amendment replays.
- `backend/tests/integration/test_restore_bootstrap_on_supabase_shape.py` — the amendment's readings.
- `backend/migrations/versions/002_rls_documents_pilot.py:38,44-50` — role creation and the first
  four grant statements.
- `backend/migrations/versions/026_rls_activation_grants.py:30-37` — the function and sequence grants.
- `backend/migrations/versions/029_rls_persons.py:44-48,56` — the `persons_sel` predicate that check 4's
  two-sided reading depends on.
- `backend/app/core/rls.py:63` — `SET LOCAL ROLE`, issued on every request transaction.
- `backend/app/core/config.py:71-72` — `RLS_ENABLED` defaults `True`; `RLS_APP_ROLE`.
- [`../ops/backup-restore.md`](../ops/backup-restore.md) — the drill log, the 2026-08-22 fresh-cluster
  measurements, and the recovery runbook.
- [`008-rls-defense-in-depth.md`](008-rls-defense-in-depth.md) — the layer this protects.
- [`047-rls-seam-sets-clan-id-only.md`](047-rls-seam-sets-clan-id-only.md) — what the seam sets.
