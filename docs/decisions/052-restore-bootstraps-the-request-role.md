# ADR-052: A Restore Bootstraps the `familyroots_app` Role and Its Grants, and the Drill Proves It Two-Sided

## Status

Accepted, shipped (2026-08-22). The failure was measured first and
declining to repair it, because the repair contained this decision.

**This ADR ships operations code, not application code**: `scripts/restore_bootstrap_role.sql` (new)
and a fourth check in `scripts/restore_drill.sh`. **No backend file changed**, and that absence is
part of the decision. Section "What was considered and rejected" says why a migration was the wrong
place for it.

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
added, and the fenced `backend/**` tree is untouched. Production has still never been dumped or
restored, which stays an open gap in [`../ops/backup-restore.md`](../ops/backup-restore.md).

## Sources

- `scripts/db_backup.sh:40` — the `pg_dump` line that drops owners and privileges.
- `scripts/restore_drill.sh` — the drill, its four checks, and the bootstrap invocation.
- `scripts/restore_bootstrap_role.sql` — the bootstrap itself.
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
