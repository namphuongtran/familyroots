# ADR-066: The Application Database Lives in the Supabase Project, and the Data API Is Closed to It

## Status

Accepted (2026-10-10). Resolves issue #251, "The application database moves into the Supabase
project, and the Data API is closed to it". The maintainer took the decision in § 1 on 2026-10-10.
The rest of this ADR records what building it decided.

**This ADR ships with its code**, in the same pull request: migrations `041` and `042`, a fix to
`backend/migrations/env.py`, and `backend/tests/integration/test_supabase_shaped_database.py` and
`test_migrations_env_encoded_url.py`. Every reading below was taken on **2026-10-10**, from `c39ad2e`
on `main`. The image readings used `supabase/postgres:17.6.1.084`, the image the local stack runs.
Readings that could crash a cluster, or that needed the image's own defaults, were taken on private
containers of the same image. **The hosted project was not read.** This change
was fenced off it, so the hosted project's default privileges, extensions and dashboard are known here
only from the issue's own reading. Cite this ADR by section. Treat its line numbers as hints.

## Context

### The move

Until 2026-10-10, the application database was Render's Postgres 18, and the Supabase project served
only auth and storage (`docs/ops/supabase-hosted-project.md:3`). The maintainer moved the application
database into the Supabase project `xkmutzxdhdigyfisfrwd`. The issue read that project with
`supabase projects list` as `ap-southeast-1`, Postgres `17.11.0.003`. It also takes over auth and
storage from the Tokyo project. Nothing was live, so no data moves.

### Three things stood in the way

**1. The login could not enter the request role.** Migration `002` creates `familyroots_app NOLOGIN`
(`002_rls_documents_pilot.py:38`), and no migration grants it to anyone. Supabase's `postgres` is not
a superuser. Since Postgres 16, a role's non-superuser creator receives it
`WITH ADMIN TRUE, INHERIT FALSE, SET FALSE` while `createrole_self_grant` is empty, and it is empty on
the local stack. Read on Postgres 17.11:

```
   member   |      role       | grantor  | admin_option | inherit_option | set_option
 supa_login | familyroots_app | postgres | t            | f              | f
BEGIN; SET LOCAL ROLE familyroots_app;
ERROR:  permission denied to set role "familyroots_app"
```

The request seam issues exactly that statement at the start of every request transaction
(`app/core/rls.py:63`). The production boot gate (`app/main.py:127-147`) would refuse to start.

**2. ADR-059 § 5, item 2, fired.** That event is the application database moving into the Supabase
project. The Data API serves the exposed schemas, `public` by default, to anyone holding the anon key,
and that key ships in the web bundle. PostgREST switches into `anon` for a request without a session
and into `authenticated` for one with a session. Two things put the application's tables within their
reach:

- **Supabase's default privileges.** A fresh container of the image has these defaults for objects
  `postgres` creates in `public`: `anon=arwdDxtm` on tables, `anon=rwU` on sequences, `anon=X` on
  functions, with the same for `authenticated` and `service_role`. The running local stack has
  narrower defaults: `Dxtm` on tables and `w` on sequences. That matches the "not auto-exposed"
  default described at `supabase/config.toml:19-24` (`auto_expose_new_tables`). Which of the two the
  hosted project carries was not read.
- **Our policies name no role.** No `CREATE POLICY` in the chain has a `TO` clause, so every policy
  applies to `PUBLIC`, and that includes `anon`. A clan-keyed policy fails closed, because nothing on
  the Data API path sets `app.clan_id`. Three policies do not read the GUC at all:
  - `user_clan_roles_sel USING (true)` and `user_clan_roles_ins WITH CHECK (true)`, permissive by
    decision (ADR-050);
  - `audit_logs_ins WITH CHECK (true)` (ADR-043).

  `user_profiles` and `user_fcm_tokens` have no RLS (ADR-059).

  The issue said clan-keyed tables "fail closed only because no policy names `anon`". The outcome is
  right and the reason is not.

**The measurement.** This is a fresh container of the image, with its own defaults, and the chain
stopped at `041`:

```
SET LOCAL ROLE anon;  -- app.clan_id unset
SELECT current_user, current_setting('app.clan_id', true), email FROM user_profiles;
 anon         |          | victim@example.test
INSERT INTO user_clan_roles (clan_id, user_id, role, is_approved, approved_by, approved_at)
  VALUES ('1111…', '2222…', 'admin', true, '2222…', now());
INSERT 0 1
```

So anyone holding the anon key could read every user's email and push token. They could also make
any user an approved admin of any clan. GraphQL reached the same tables. As `anon` on that container,
`graphql.resolve('{ __type(name: "Query") { fields { name } } }')` listed a collection for every
application table, `user_profilesCollection` among them.

**3. The chain had only run on Postgres 18 and plain Postgres.** It now applies on 17.11 and on the
Supabase image. On the image, `001`'s `CREATE EXTENSION` puts `pg_trgm` and `unaccent` in `public`,
created as `supabase_admin` through `supautils`, while `uuid-ossp` stays where Supabase put it, in
`extensions`. `public.f_unaccent('Nguyễn Văn Ánh')` returns `Nguyen Van Anh`. No migration needed a
change for 17.

## Decision

### 1. The application database lives in the Supabase project

It replaces Render's Postgres, and the same project serves auth and storage. Serverless readiness and
the deploy pipeline are separate issues (§ "What this ADR does not decide").

### 2. Migration `041`: the migrating login may enter `familyroots_app`

- `upgrade` asks `pg_has_role(current_user, 'familyroots_app', 'SET')`. If the answer is yes, as it is
  for every superuser and so for CI and compose, it does nothing.
- Otherwise it grants the role to the login itself, `WITH INHERIT FALSE, SET TRUE`, using the ADMIN
  option the creator holds. INHERIT is false because the login needs to *become* the role, not to
  carry its privileges: it already owns every table.
- A login that can neither set the role nor grant it fails the upgrade, and the error names the
  login.
- `downgrade` revokes only that grant: member and grantor both the login, SET, no INHERIT, no ADMIN.
  The creator's ADMIN row, whose grantor is the bootstrap superuser (`supabase_admin` on Supabase), is
  never touched.

**The migrating login must be the runtime login.** `041` grants to whoever runs it. This repository
uses one `DATABASE_URL` for both. If a deploy ever migrates as one role and runs as another, the boot
gate is what will say so.

**Every role is named. None is written `CURRENT_USER`.** The first version of `041` wrote
`GRANT familyroots_app TO CURRENT_USER … GRANTED BY CURRENT_USER`. On the local stack, it crashed the
backend:

```
LOG:  server process (PID 1743) was terminated by signal 11: Segmentation fault
DETAIL:  Failed process was running: DO $$ … pg_has_role(current_user, 'familyroots_app', 'SET') …
LOG:  terminating any other active server processes
LOG:  database system was not properly shut down; automatic recovery in progress
```

The upgrade rolled back whole, and the stack recovered on its own. A private container of the same
image reproduced it one statement at a time:

| Statement | Result |
|---|---|
| `GRANT r TO postgres WITH INHERIT FALSE, SET TRUE` | ran |
| `GRANT r TO CURRENT_USER WITH INHERIT FALSE, SET TRUE` | signal 11 |
| `GRANT r TO postgres … GRANTED BY CURRENT_USER` | ran |
| `REVOKE r FROM CURRENT_USER GRANTED BY postgres` | signal 11 |
| `REVOKE r FROM postgres GRANTED BY postgres` | ran |

So it is a `CURRENT_USER` grantee in a role `GRANT` or `REVOKE`, under `supautils`, which the image
loads through `session_preload_libraries`. Plain Postgres accepts every form, so **CI cannot see this
class of failure**. `041` builds each statement with `format('%I', current_user)`.

### 3. Migration `042`: `anon` and `authenticated` hold nothing in `public`

For each of the two roles that exists, `042`:

- revokes ALL on every table, sequence and routine in `public`;
- revokes ALL from the login's default privileges in `public`;
- revokes ALL from the login's **global** default privileges, the form without `IN SCHEMA`.

The global form is there because Postgres adds per-schema defaults to global ones, and a per-schema
`REVOKE` cannot remove a privilege that a global default grants. Supabase was not seen to set one.
Without the global form, the test's `global` shape fails and its `per_schema` shape passes. That is
negative control 3 below.

Where neither role exists, as in CI, compose and plain Postgres, `042` does nothing. **Its `downgrade`
is a deliberate no-op.** A rollback must not re-open the Data API onto the application's tables. The
grants it would restore were never the application's.

**What `042` leaves alone, and why that is safe.**

- **`service_role`.** Only the backend holds that key.
- **`USAGE` on the schema.**
- **`PUBLIC`'s `EXECUTE` on functions,** which Postgres grants by default. Every routine in `public` is
  `SECURITY INVOKER`, so a call through `/rpc` reads its tables as the caller. Read on the local stack
  through Kong and PostgREST with the anon key:

  ```
  POST /rest/v1/rpc/get_children -> {"code":"42501",…,"message":"permission denied for table parent_child"} [HTTP 401]
  ```

  **A `SECURITY DEFINER` function in `public` would break this.** None exists today.
- **Objects `supabase_admin` owns in `public`.** These are the `pg_trgm` and `unaccent` functions,
  which keep `anon`'s EXECUTE because `postgres` cannot revoke on objects it does not own. They are
  pure. On the image, `show_limit` still appears in `anon`'s GraphQL `Query` type after `042`, beside
  `node` and nothing else.

### 4. The dashboard step: remove `public` from the Data API's exposed schemas

This is the second lock. The grants in § 3 are the first. The step is in the hosted project's API
settings, and SQL cannot do it. It is owed to whoever configures the hosted project, under the deploy
issue.

**It does not replace § 3.** GraphQL reaches `public` through the `graphql_public` schema, which stays
exposed. Per the reading in Context, `pg_graphql` reflects every table the role can read. So the
exposed-schemas list closes REST, and only the grants close both. Turning the Data API off entirely
would be stronger. It is not decided here, because it would also switch off `graphql_public`, and
nothing has been checked against that.

### 5. `migrations/env.py` doubles `%` in the URL it hands Alembic

Alembic's `Config` is a `ConfigParser` with interpolation. `set_main_option` refuses an undoubled `%`
with `ValueError: invalid interpolation syntax`. A password containing `@`, `:` or `/` is
percent-encoded in a URL, and the Supabase pooler URL that the deploy migrates through carries one.
The #252 agent measured this with Alembic 1.18.5. **The error message prints the whole URL, password
included.** `env.py` now passes `settings.DATABASE_URL.replace("%", "%%")`, and `get_main_option` and
`get_section` undo the doubling.

## Verification

Readings taken 2026-10-10. All of `backend/tests/integration/test_supabase_shaped_database.py`'s
verdicts come from statements run as a role. It runs the real chain through the Alembic CLI, as a
login shaped like Supabase's `postgres`: `NOSUPERUSER CREATEROLE CREATEDB BYPASSRLS`. That login holds
the membership options the server gives a role's creator, read by having the login create a probe
role. `anon` and `authenticated` hold Supabase's legacy `GRANT ALL` defaults before the chain runs, in
two shapes, `per_schema` and `global`.

| Negative control | Result |
|---|---|
| 1. Drop `041` from the chain, re-linking `042` to `040` | `test_the_login_enters_the_request_role_and_two_clans_stay_apart` fails at `SET LOCAL ROLE familyroots_app` with `InsufficientPrivilege: permission denied to set role "familyroots_app"`. All six `041` cases fail |
| 2. Drop `042` from the chain | All 12 `042` cases fail. For `anon`, the table test lists 34 statements that were not refused, among them `'SELECT user_profiles': 'ran, 1 row(s)'`, `'SELECT user_fcm_tokens': 'ran, 1 row(s)'` and `'SELECT user_clan_roles': 'ran, 1 row(s)'`. `INSERT user_clan_roles` and `INSERT audit_logs` passed both the privilege check and RLS, and stopped at `NOT NULL` |
| 3. Remove only `042`'s three global `ALTER DEFAULT PRIVILEGES` lines | The objects-created-later test passes in `per_schema` and fails in `global`, with `'SELECT': 'ran, 1 row(s)'` |
| 4. Let `041`'s downgrade revoke any self-grant | The downgrade test fails at index 2: a hand-made self-grant was revoked |
| 5. Make `041`'s downgrade a no-op | The downgrade test fails at index 1: the role could still be entered after the downgrade |
| 6. Remove the `%` doubling from `env.py` | `test_alembic_reaches_a_database_whose_url_has_a_percent_encoded_password` fails with `ValueError: invalid interpolation syntax in '…p%40ss%3Aw%2Frd%251@…' at position 47` |

The full suite passed on **Postgres 17.11**, via `TEST_PG_ADMIN_URL`, with 1729 passed. The local
Supabase stack read as follows:

- `alembic upgrade head` applied all 42 revisions.
- Through the Data API with the anon key, `GET /rest/v1/user_profiles` answered
  `{"code":"42501",…,"message":"permission denied for table user_profiles"}`. A `POST` to
  `user_clan_roles` was refused the same way.
- As `postgres`, `SET LOCAL ROLE familyroots_app` gave `current_user = familyroots_app` and
  `rolbypassrls = f`.

The stack was then downgraded and returned to its prior state. The commit and issue #251 carry the
full output.

## Consequences

Easier:

- The production boot gate can pass on Supabase. RLS layer 2 runs there as it does on a superuser.
- ADR-059's § 4 risk does not grow with the move. `user_profiles` and `user_fcm_tokens` are still
  protected by the application layer alone *against the request role*, but the Data API holds nothing
  on them.

Harder:

- **CI cannot catch a `supautils`-class failure.** Its Postgres is plain `postgres:18-alpine`. The
  one CI job that starts the Supabase image is `image-e2e`, and it migrates `pgdb`, not
  `supabase_db`.
- **A future `SECURITY DEFINER` function in `public` would be callable by `anon`** through `PUBLIC`'s
  EXECUTE, and it would read as its owner.
- **Role membership is a cluster object.** Two databases in one cluster, migrated by one non-superuser
  login, share `041`'s grant, and downgrading one revokes it for both.

## Owed, outside this change's fence

- **`scripts/restore_bootstrap_role.sql` (ADR-052) does not cover a Supabase restore.** It says
  "Run as a superuser", and a Supabase project offers none. Run as `postgres` against a project that
  never held the role, its `CREATE ROLE` leaves `postgres` with ADMIN and no SET. The restored
  `alembic_version` already reads `042`, so `041` never runs again, and the app cannot
  `SET LOCAL ROLE`. A restore there also needs the self-grant
  `GRANT familyroots_app TO postgres WITH INHERIT FALSE, SET TRUE`.
  **It needs `042`'s revokes replayed too.** `db_backup.sh` dumps with `--no-privileges`, so restored
  tables take the restoring role's default privileges, which on a project with the legacy defaults
  grant `anon` ALL. The scripts are guarded by `test_scripts_sql_is_sanctioned.py` and its two
  siblings, which constrain role DDL, so this belongs to whoever owns ADR-052.
- **The § 4 dashboard step on the hosted project,** under the deploy issue.
- **`supabase/config.toml` `[api] schemas`** still lists `public` for the local stack.
- **Reading the hosted project's default privileges** in `public`, legacy or narrowed. `042` closes
  both, so this is a record, not a blocker.
- **Running `alembic upgrade head` against `supabase_db` in `image-e2e`** would put the one CI job
  that has `supautils` in front of the chain.

## What this ADR does not decide

- **Serverless readiness:** the pool, the scheduler, the cron endpoints and the lock topology. Its
  own issue.
- **The deploy pipeline:** migrations through the session pooler, `vercel.json`, the hosted-project
  ops docs. Its own issue (#252).
- **Moving the application's tables out of `public`.**
- **`service_role`'s grants.**
- **Revoking `PUBLIC`'s `EXECUTE`** on functions in `public`.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Rely on the dashboard's exposed-schemas setting alone | It is a setting outside the repository that no test reads, and it does not cover GraphQL, which reflects every table `anon` can read (Context, the `graphql.resolve` reading) |
| Give `user_profiles` and `user_fcm_tokens` RLS policies that deny `anon` | ADR-059 § 3 still holds for the request role. A policy keyed on role would leave every *other* table's permissive policies (`user_clan_roles_ins`, `audit_logs_ins`) open to `anon`. A grant is the one lock that covers every table at once |
| Add `TO familyroots_app` to every policy | Rewrites thirteen tables' policies to fix what a grant fixes. It also leaves `user_profiles` and `user_fcm_tokens`, which have no policy, open |
| Revoke from `PUBLIC` as well | Out of the issue's scope. It changes what every role in the cluster may call, Supabase's own included, and today it buys nothing, because every function is `SECURITY INVOKER` |
| Grant `familyroots_app` to the login in `002`, by editing it | `002` is applied, and applied migrations are immutable |
| `041` with `GRANT … TO CURRENT_USER` | Crashes the backend under `supautils` (§ 2) |
| Make `042`'s downgrade re-grant what Supabase granted | A rollback would re-open the Data API, and the migration cannot know what the project granted before it ran |

## Related

- [ADR-008: Row-Level Security as Defense-in-Depth Layer-2](008-rls-defense-in-depth.md), the request
  role `041` makes enterable.
- [ADR-043: `audit_logs` Is Inside Layer 2 with Per-Command Policies](043-audit-notification-rls-posture.md)
  and [ADR-050: `user_clan_roles` Clan-Keyed Mutations](050-user-clan-roles-clan-keyed-mutations.md),
  whose permissive halves `042` keeps away from `anon`.
- [ADR-052: Restore Bootstraps the Request Role](052-restore-bootstraps-the-request-role.md), owed a
  Supabase path (§ "Owed").
- [ADR-059: `user_profiles` and `user_fcm_tokens` Are User-Owned and Stay Outside Layer 2](059-user-owned-tables-stay-outside-layer-2.md),
  whose § 5 item 2 this answers. Its dated amendment points here.
