# ADR-074: The Nightly Dump Stays Whole, and a Restore Takes `public` Whole and the Data of `auth`

## Status

Accepted (2026-10-18), decision only. Resolves issue #285, "Which schemas does the nightly dump of
the Supabase database hold?". The maintainer settled each question in a grilling session the same
day. **#258 implements it.** This pull request changes no script, workflow or database.

Repository readings were taken on `main` at `be6bcdc`. The first production dump's table of
contents and the production row counts were read on 2026-10-18 (§ The reading). Supabase's docs and
source, and PostgreSQL's, were read on 2026-10-18 by the research behind this ADR, and are cited
where they are used.

## Context

`scripts/db_backup.sh:40` runs `pg_dump --format=custom --no-owner --no-privileges` with no
`--schema`. Against the Supabase project `xkmutzxdhdigyfisfrwd` that takes Supabase's own schemas
along with `public`. `scripts/restore_drill.sh:130` restores with `--exit-on-error` into plain
Postgres, which has none of Supabase's roles or extensions, so `docs/ops/backup-restore.md` expected
the first drill of a production dump to fail. A `public`-only dump is no way out either. Every
account lives in `auth.users`, so a `public`-only restore gives back data no one can sign in to.

Two facts in the code decide how accounts come back:

- **`user_profiles.id` is `auth.users.id`, with no foreign key.** `docs/architecture/data-model.md:366`
  says so. `user_clan_roles`, `user_fcm_tokens` and `identity_claims` reach accounts only through
  `user_profiles.id`.
- **A new `sub` with a known email gets a 500.** `ensure_user_profile`
  (`backend/app/core/security.py:143`) inserts with `ON CONFLICT DO NOTHING` on `id` only, and
  `user_profiles.email` carries `uq_user_profiles_email`. An account that comes back with a new
  UUID and its old email would fail its first request. That is #297.

## The reading

**The table of contents of `db/daily/familyroots-2026-10-11.dump.gz`, read 2026-10-18** with
`gunzip -c <dump.gz> | docker run --rm -i postgres:18.6 pg_restore -l`. The dump was deleted from
the machine as soon as the listing was taken. Header:

```
; Archive created at 2026-10-11 13:52:28 UTC
;     TOC Entries: 616
;     Dumped from database version: 17.11
;     Dumped by pg_dump version: 18.6 (Ubuntu 18.6-1.pgdg24.04+2)
```

Grouped by schema and object type. `-` is an object that belongs to no schema.

| Schema | Entries |
|---|---|
| `-` | SCHEMA 8, EXTENSION 6, COMMENT 6, EVENT TRIGGER 7, PUBLICATION 1 |
| `public` | TABLE 17, TABLE DATA 17, CONSTRAINT 24, FK CONSTRAINT 29, INDEX 59, FUNCTION 11, TRIGGER 12, POLICY 20, ROW SECURITY 13 |
| `auth` | TABLE 27, TABLE DATA 27, TYPE 9, FUNCTION 4, CONSTRAINT 39, FK CONSTRAINT 24, INDEX 72, ROW SECURITY 16, COMMENT 28, SEQUENCE 1, SEQUENCE OWNED BY 1, SEQUENCE SET 1, DEFAULT 1 |
| `storage` | TABLE 8, TABLE DATA 8, TYPE 1, FUNCTION 19, CONSTRAINT 9, FK CONSTRAINT 5, INDEX 11, TRIGGER 7, ROW SECURITY 8, COMMENT 2 |
| `realtime` | TABLE 3, TABLE DATA 2, TYPE 5, FUNCTION 18, CONSTRAINT 3, CHECK CONSTRAINT 1, INDEX 3, TRIGGER 1, ROW SECURITY 1, SEQUENCE 1, SEQUENCE SET 1 |
| `vault` | TABLE DATA 1 (`secrets`, a table its extension creates) |
| `extensions` | FUNCTION 6, COMMENT 4 |
| `graphql_public` | FUNCTION 1 |
| `pgbouncer` | FUNCTION 1 |

The entries that belong to no schema, by name:

- **Schemas:** `auth`, `extensions`, `graphql`, `graphql_public`, `pgbouncer`, `realtime`, `storage`,
  `vault`.
- **Extensions:** `pg_stat_statements`, `pg_trgm`, `pgcrypto`, `supabase_vault`, `unaccent`,
  `uuid-ossp`.
- **Event triggers:** `ensure_rls`, owned by `postgres`. And six owned by `supabase_admin`:
  `issue_graphql_placeholder`, `issue_pg_cron_access`, `issue_pg_graphql_access`,
  `issue_pg_net_access`, `pgrst_ddl_watch` and `pgrst_drop_watch`.
- **Publication:** `supabase_realtime`.

`public`'s 11 functions include `rls_auto_enable`, the function behind the project's `ensure_rls`
trigger ([ADR-066's 2026-10-10 amendment](066-the-application-database-lives-in-the-supabase-project.md)).
No migration creates it. The 27 tables of `auth` with data include `users`, `identities`,
`sessions`, `refresh_tokens` and `schema_migrations`.

**Production's row counts, read 2026-10-18** with `supabase db query --linked`:

- `auth.users` 1, with 1 email identity, 1 session and 1 refresh token. `auth.mfa_factors` 0.
- `public.user_profiles` 0, `public.clans` 0, `public.persons` 0, `public.documents` 0.
- `storage.objects` 2, both in `backups`. `vault.secrets` 0, `realtime.subscription` 0.

## Decision

### 1. The dump stays whole

`pg_dump` keeps its flags and its single file. The choice of what to bring back is made at restore
time, where the drill (§ 4) reads it.

- **One file keeps ADR-073 as written.** Its encryption, its two destinations and its rotation each
  handle one object per night.
- **`pg_dump` cannot do the split itself.** With `-n`, "No extensions are dumped if
  include_everything is false (i.e., a --schema or --table switch was given)", and "publications
  are only dumped when we are dumping everything". `-a` is global, so one run cannot be data-only
  for `auth` and whole for `public` (`src/bin/pg_dump/pg_dump.c`, `REL_18_STABLE`).
- **The archive keeps what the restore leaves.** If `storage` metadata is ever wanted, it is there.

### 2. A restore takes `public` whole and the data of `auth`, and nothing else

**`public`: schema and data,** with `pg_restore -n public`, minus one entry,
`public.rls_auto_enable`. That function is the project's own, not the chain's. A hosted project
created with automatic RLS already holds it, and `pg_restore` would fail on `CREATE FUNCTION`
there. The local stack has no such function. Leaving the entry out in both places keeps the drill
and a real recovery on one restore list.

- **`-n` restores no `CREATE EXTENSION`.** The extensions entries belong to no schema. The target
  must already hold every extension `public` uses. `pg_trgm` and `unaccent` sit in `public` in
  production. #258 builds the list from the dump, not from this sentence.

**`auth`: data only, from every table except `auth.schema_migrations`.** The target is a Supabase
project, which already owns its `auth` schema at its own GoTrue version.

- **The mechanism.** Supabase's documented restore runs the data with
  `SET session_replication_role = replica`, because it "disables triggers during the migration,
  preventing columns from being double encrypted"
  ([backup and restore](https://supabase.com/docs/guides/platform/migrating-within-supabase/backup-restore)).
  So the `auth` data comes out of `pg_restore --data-only -n auth -L <list> -f -` as SQL, and
  `psql` runs it in one transaction after that `SET`. **Not tested.** #258 proves it.
- **Why `schema_migrations` stays out.** Supabase's CLI leaves it out of every data dump
  (`--exclude-table "auth.schema_migrations"`, `supabase/cli` `pg-dump.env.ts`). Hosted projects
  block `INSERT`, `UPDATE`, `DELETE` and `TRUNCATE` on it
  ([2025-04-21 changelog](https://supabase.com/changelog/34270-restricting-access-on-auth-storage-and-realtime-schemas-on-april-21-2025)).
- **Sessions and refresh tokens come back, and are inert.** A new project signs with a new key, so
  every user signs in again. Supabase's self-hosting guide says the same of its own path: "JWT
  secrets differ… Users will need to re-authenticate"
  ([restore from platform](https://supabase.com/docs/guides/self-hosting/restore-from-platform)).
  Restoring them costs nothing. Leaving them out would mean a list of tables to keep, and a table
  GoTrue adds later for account data would then be missed without a sound.

**Not restored:**

| What | Why |
|---|---|
| `storage` data | Rows are metadata. The files live outside Postgres, so in a new project the rows would point at nothing. Bucket definitions come from `supabase/config.toml:131,143`. Backing up the files is #296 |
| `realtime`, `vault` data | `realtime` holds nothing to keep. `vault.secrets` held 0 rows, and a secret is encrypted with a key that belongs to its project |
| Supabase's extensions, the 7 event triggers and the publication | The target project ships its own. `ensure_rls` is the project's too |
| Supabase's schemas' DDL | Owned by the target project, at its version |

### 3. Accounts re-link by keeping their UUIDs

Restoring `auth.users` and `auth.identities` keeps every UUID and every password hash. Supabase
documents it: "You can migrate all tables in the auth schema—including users and their hashed
passwords—from one Supabase project to another"
([migrating auth users](https://supabase.com/docs/guides/troubleshooting/migrating-auth-users-between-projects)).
`user_profiles` and everything keyed by it then match with no rewrite.

- **`postgres` can write those rows on a hosted project.** The April 2025 restriction covers DDL
  and the three migration tables. `GRANT ALL ON ALL TABLES IN SCHEMA auth TO postgres` still stands
  (`supabase/postgres`, `10000000000000_demote-postgres.sql:7`). `postgres` may set
  `session_replication_role` through `supabase_privileged_role`
  (`20260211120934_supabase_privileged_role.sql`, `supautils.conf.j2:14-15`).
- **The `auth` data is restored before traffic opens.** An account created in the new project
  first would hold a new UUID, and a later restore of its old row would leave two accounts for one
  email. The 500 in #297 is the same collision seen from the API.
- **The order of a real recovery:**
  1. create the project;
  2. apply its settings: buckets from `supabase/config.toml`, Auth settings, SMTP
     ([ADR-071](071-hosted-auth-email-goes-out-through-resend-on-the-owners-domain.md));
  3. create the extensions `public` needs;
  4. restore `public`;
  5. restore the `auth` data;
  6. run `scripts/restore_bootstrap_role.sql`
     ([ADR-052](052-restore-bootstraps-the-request-role.md));
  7. prove it, the way the drill does;
  8. repoint the API, the web app and the mobile build at the new URL and keys;
  9. open traffic.
- **An `auth` schema newer than the dump may refuse rows.** Supabase documents only the opposite
  direction, a newer dump into an older target, where the fix is to "comment out the relevant
  `COPY ... FROM stdin;` line" (restore from platform, above). A dump's `COPY` names its columns,
  so a column added since takes its default. A column renamed or dropped breaks the restore and is
  fixed by hand. The drill (§ 4) is where that shows first.

### 4. The drill restores into the local Supabase stack, as `postgres`

`supabase start`, the database on `:54322`, Postgres 17 (`supabase/config.toml:35,42`). It runs the
same commands as § 3's steps 3 to 7, as the same login.

- **The local image has the hosted privilege model.** It applies the same migrations,
  `COPY migrations/db /docker-entrypoint-initdb.d/`, and preloads `supautils`
  (`supabase/postgres`, `Dockerfile-17:145-146,158`). Read at source. Not yet tested.
- **One difference is known.** The local image has no `ensure_rls` trigger (ADR-066's 2026-10-10
  amendment). § 2's restore list leaves out `rls_auto_enable`, and the bootstrap's `043` section is
  a no-op where RLS is already off, so the same commands serve both.
- **Plain Postgres is dropped as a target.** It has no `auth` schema, so it can prove nothing about
  accounts. A recovery never lands there either: leaving Supabase means replacing Auth, which is not
  a restore.
- **`supabase db start --from-backup` is not this path.** It restores as `supabase_admin` with
  `postgres` rewritten `WITH SUPERUSER` (`supabase/cli`, `internal/db/start/templates/restore.sh:25`),
  which a hosted recovery never has.

### 5. `DRILL: PASS` proves accounts sign in, not only that rows exist

Two checks join the four the drill has today. Each is an outcome, with a control whose reading
differs (`.claude/rules/testing.md`).

**The link check.** After the restore:

- `auth.users` holds as many rows as the dump's `auth.users` data;
- no `user_profiles` row lacks its `auth.users` row;
- no `user_clan_roles` row points at such a profile.

The control deletes one linked `auth.users` row and reads `DRILL: FAIL`.

**The canary sign-in.** A dedicated production account exists for the drill.

- **The account.** `drill-canary@getnami.dev`, on the owner's domain. It is created with the
  dashboard's "Add user", already confirmed, so no email is sent. It signs in once through the
  production API, so `ensure_user_profile` gives it a `user_profiles` row and the link check has a
  row to fail on. Production held 0 profiles on 2026-10-18, so without one that check would pass
  with nothing to read.
- **It belongs to no clan.** No clan is planted in production. Check 4, the request-role check,
  keeps reading `WARN` until a real clan exists, which is what it already says when a dump has no
  `clan_memberships` rows.
- **Its password lives in the password manager,** beside the `age` working identity
  ([ADR-073](073-the-off-provider-dump-copy-lives-in-backblaze-b2-encrypted-with-age.md) § 5). The
  drill reads it from an environment variable #258 names.
- **The check.** The drill asks the local GoTrue for a token with the password grant,
  `POST :54321/auth/v1/token?grant_type=password`. It requires the token's `sub` to equal the
  canary's UUID in the restored `auth.users`. The control signs in with a wrong password and must
  be refused.
- **Without the password, the drill reads `DRILL: FAIL`.** A `WARN` would let a pass without the
  sign-in read the same as a pass with it.

### 6. The drill is a step in cutting a release

The operator runs it on their own machine, since no `age` identity lives in CI (ADR-073 § 5).

- **When.** Before approving a release, as a step in `docs/ops/deployment.md`, "Cutting a release".
  A release is already a manual ceremony with a checklist, and it is when a migration can first
  break a restore.
- **Not added yet.** #258 adds the step with the drill it describes. Today's drill would fail on a
  production dump, as the backup doc expects.
- **The dump it reads.** The maintainer disabled `db-backup.yml`'s schedule on 2026-10-11
  (`disabled_manually`) to save Actions minutes. Until it is enabled again, the drill reads the
  2026-10-11 dump.

## Consequences

- **#258 is unblocked, and gains this scope**, beside ADR-073's:
  - the restore split of § 2, in `scripts/restore_drill.sh` and in "Restoring for real";
  - the drill's target moves to the local Supabase stack;
  - the link check and the canary sign-in of § 5, each with its control;
  - § 3's recovery order, written into `docs/ops/backup-restore.md`;
  - the release step of § 6, in `docs/ops/deployment.md`.
- **The maintainer creates the canary account** and stores its password. That is a dashboard step,
  not an agent's.
- **The dump carries password hashes, session tokens and refresh tokens.** It did since #252.
  ADR-073's encryption is what protects them, and until #258 ships it the Supabase copy is not
  encrypted.
- **The drill needs Docker and the local Supabase stack running,** not only `pgdb`.
- **A recovery moves every client.** A new project means a new URL and new keys for the API, the
  web app and the mobile build, and the mobile app needs a new build. `docs/ops/backup-restore.md`'s
  "RTO ≈ 1h" did not count that, and this ADR does not re-estimate it.
- **The files in the two buckets are still in no backup.** #296.
- **A sign-up that reuses a deleted account's email still gets a 500.** #297. § 3's order keeps a
  recovery clear of it.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Dump `public` only | No one can sign in after a restore. Re-linking by email needs a rewrite of every table keyed by `user_profiles.id`, and a new `sub` with a known email hits #297's 500 |
| Supabase CLI's three files: `roles.sql`, `schema.sql`, `data.sql` | Needs the Supabase CLI in Actions and three files a night, and ADR-073's single encrypted object would have to change. Its data file also carries the `storage` rows § 2 leaves out |
| Two `pg_dump` runs, `public` whole and `auth` data-only | Two files a night for the same result as § 1's one |
| Restore only the account tables of `auth` | A table GoTrue adds later for account data would be missed without a sound. Sessions are inert anyway |
| Restore every `auth` table, `schema_migrations` too | The target owns its own migration history, and hosted projects refuse writes to that table |
| Restore the `storage` rows | They would point at files the new project does not have (#296) |
| Drill into plain Postgres | No `auth` schema, and not a place a recovery lands |
| Drill into both plain Postgres and the local stack | The plain-Postgres half proves a path no recovery takes |
| `supabase db start --from-backup` as the drill | Restores as a superuser, which a hosted recovery never is |
| Link check only, no sign-in | Rows that exist are a setting. Only a sign-in shows the hash still works and GoTrue accepts the restored rows |
| The owner's own account as the canary | Their real password would sit in the drill's environment, and changing it would break the drill |
| A missing canary password reads `WARN` | A pass without the sign-in would read the same as a pass with it |
| Drill monthly, or once at go-live | A date on a calendar is easier to skip than a step in a checklist that is already run, and neither date follows the migrations that can break a restore |

## Verification

**No gate: documentation only.** The reading is this ADR merged with the dump's table of contents
in it, and #258's body naming it.

**Owed by #258**, each as an outcome rather than a setting (`.claude/rules/testing.md`):

- `scripts/restore_drill.sh --latest` reads `DRILL: PASS` on a production dump restored into the
  local Supabase stack, with the canary sign-in returning the canary's UUID.
- **Each control reads `DRILL: FAIL`:** a linked `auth.users` row deleted before the link check, a
  wrong canary password, and the canary variable unset.
- **The restore list holds against a hosted-shaped target.** The restore completes into a database
  that already holds `public.rls_auto_enable`.

## Related

- [ADR-073](073-the-off-provider-dump-copy-lives-in-backblaze-b2-encrypted-with-age.md): where the
  dump goes, and the encryption that now guards password hashes.
- [ADR-066](066-the-application-database-lives-in-the-supabase-project.md): the move that put
  `auth` beside `public`, and the `ensure_rls` amendment.
- [ADR-052](052-restore-bootstraps-the-request-role.md): the bootstrap, step 6 of a recovery.
- [ADR-071](071-hosted-auth-email-goes-out-through-resend-on-the-owners-domain.md): the owner's
  domain, and the SMTP a new project must be given.
- [ADR-067](067-production-ships-on-a-published-release.md): the release that § 6's drill step
  joins.
- Issues #285 (this decision), #258 (implements it), #296 (the bucket files) and #297 (the
  same-email 500).
