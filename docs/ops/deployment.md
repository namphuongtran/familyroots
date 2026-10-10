# Deployment

## Overview
On 2026-10-10 the maintainer decided where FamilyRoots runs (#250, #251, #252):

- **backend** and **web** run on **Vercel**, as two projects under team `namtp` (Hobby), both
  pinned to function region `sin1` (Singapore).
- The **database, auth and storage** are one **Supabase** project, `xkmutzxdhdigyfisfrwd`, in
  `ap-southeast-1` (Singapore) on Postgres 17. See [supabase-hosted-project.md](supabase-hosted-project.md).
- **mobile** ships through Flutter build pipelines, with no deploy step.
- **Render is retired.** `infra/render/render.yaml` was deleted by #252. `backend/Dockerfile` stays,
  because `docker-compose.yml` and `image-e2e.yml` build it. Production no longer runs that image.

ADR-065 records the backend's move to Vercel Functions and ADR-066 the database's move into the
Supabase project. Both are listed in [../decisions/README.md](../decisions/README.md). Pulumi
still captures infra intent, and its resources are still stubs.

| | Value | Config in the repository |
|---|---|---|
| Vercel team | `namtp` (Hobby), orgId `team_POAVczQHAZ0182nbj5oQrQ0E` | |
| `familyroots-api` | projectId `prj_bvR27jsrEOWsD2q1vGeKxwkLAY3Z`, deployed from `backend/` | `backend/vercel.json`, `backend/.vercelignore` |
| `familyroots-web` | projectId `prj_TD73V51MFvGHzOYTeclsYVqaEfXT`, deployed from `web/` | `web/vercel.json` |
| Supabase | project `xkmutzxdhdigyfisfrwd`, `ap-southeast-1`, Postgres 17 | `supabase/config.toml` (buckets), `supabase/supabase/config.toml` (email templates) |

Both projects were created on 2026-10-10. The ids are not secrets, but CI reads them from GitHub
secrets ("Go-live checklist", B). Read the same day with `vercel project inspect <name> --scope namtp`,
which changes nothing. Both projects showed **Root Directory** `.`, **Framework Preset** `Other`,
and **Node.js Version** `24.x`. The preset is why each `vercel.json` names its framework
("What the Vercel files set").

## Pipeline (as implemented in `.github/workflows/`)

| Component | Trigger | Mechanism |
|-----------|---------|-----------|
| backend | push to `main` (after `lint-and-test` passes) | the `deploy` job (`backend-ci.yml`) runs three steps in order. (1) `alembic upgrade head` against `MIGRATION_DATABASE_URL`. (2) `npx vercel@63.1.0 deploy --prod` from `backend/`, with `VERCEL_ORG_ID` and `VERCEL_PROJECT_ID` (from the `VERCEL_API_PROJECT_ID` secret). (3) `GET $API_ORIGIN/health`, which fails the job unless `migrations` is `current`. If any of its four secrets or the `API_ORIGIN` variable is unset, it prints a `::warning::` naming each missing one, runs none of the three steps, and stays green |
| web | push to `main` (after `build-and-test`, `e2e` and `api-types-fresh` pass) | `pnpm dlx vercel@63.1.0 deploy --prod --token="$VERCEL_TOKEN"` from `web/`, with `VERCEL_ORG_ID` and `VERCEL_PROJECT_ID` (from the `VERCEL_WEB_PROJECT_ID` secret) (`web-ci.yml`). With any of the three secrets missing it skips with a `::warning::` naming them |
| mobile | push to `[main, develop]` | Flutter build + test (`mobile-ci.yml`); **no deploy step** |
| infra | push to `[main, develop]` | `pulumi preview` on PR / `pulumi up` on `main` (`infra-ci.yml`) — currently a **no-op** because the Pulumi resources are stubs |
| repo hygiene | pull request to `[main, develop]`, never push | gitleaks secret scan + no-committed-`.env` gate (`pr-checks.yml`) |
| images + authenticated e2e | pull request and push to `main` | builds `backend/Dockerfile` and `web/Dockerfile`, boots the backend image under `APP_ENV=production` and runs `pnpm test:e2e:auth` against it (`image-e2e.yml`, #193). A check, not a deploy: neither deploy job waits for it, and branch protection does not require it (`main` has no protection and no rulesets, read 2026-10-06). Production does not run this image. See [local-supabase.md](local-supabase.md), "The image e2e job in CI" |
| db-backup | **schedule** (`cron "15 17 * * *"` = 00:15 Asia/Ho_Chi_Minh) + `workflow_dispatch` — not push | `pg_dump` → gzip → upload to Supabase Storage `backups` bucket + rotation (`db-backup.yml`); skips green with a `::notice::` if the 3 backup secrets aren't set — see [backup-restore.md](backup-restore.md) |

The workflows do not share one trigger. `backend-ci.yml`, `mobile-ci.yml` and
`infra-ci.yml` run on push and pull request to `[main, develop]`.
`web-ci.yml` and `image-e2e.yml` run on `main` only. `pr-checks.yml` runs on pull requests
only. Every workflow but `pr-checks.yml` and `db-backup` filters on paths, so a change
outside a workflow's `paths:` runs none of its jobs. `db-backup` is schedule/dispatch-only
and never runs on push. The backend and web deploys are separate workflows, and neither waits
for the other.

**There is no staging gate today — `main` → production directly.** `develop` runs
CI (lint/test) but does not deploy. A dev → staging → prod promotion path is not yet
implemented; treat `main` as production. Preview deployments are not set up (#252, out of scope).

## The backend deploy job, step by step

**1. Migrate.** `uv sync --frozen --no-dev`, then `uv run --no-sync alembic upgrade head` and
`alembic current`, with `DATABASE_URL` set from `MIGRATION_DATABASE_URL` and nothing else.
`migrations/env.py` reads `settings.DATABASE_URL`, and `APP_ENV` is unset, so `Settings` reads
`development` and the production validator does not run. A failed migration fails the job before
anything is deployed. [migrations.md](migrations.md), "How migrations reach production", has why
this is the session pooler and which password breaks it.

**2. Deploy.** `vercel deploy --prod` uploads `backend/`, minus what `backend/.vercelignore` lists,
and Vercel builds it. The deployment becomes production when its build is ready. **Nothing
requests the app before that.** This repository configures no Vercel deployment checks. Render
held a deploy back until its `preDeployCommand` and its health check passed. On Vercel, the boot
gate in `app/main.py`'s lifespan no longer keeps the previous version serving. A deployment whose
lifespan raises is still production, and every cold start of it fails.

**3. Read `/health`.** Through `API_ORIGIN`, the production host, for two reasons:

- **Deployment Protection.** Under Standard Protection, the scope Vercel recommends, every URL
  but a production domain asks for a Vercel login ("Deployment Protection on Vercel", read
  2026-10-10). That includes the deployment's own generated URL, which step 2 prints.
- **`ALLOWED_HOSTS`.** It names the production host only, so `TrustedHostMiddleware` answers any
  other host with 400.

curl retries a refused connection and a 5xx five times, ten seconds apart, which covers a cold
start. Then the job fails unless the body's `migrations` is `current`. **A red step here means
production already serves the new deployment.** Roll it back (§ Rollback).

**Concurrency.** The job is in the `backend-production-deploy` concurrency group with
`cancel-in-progress: false`. Two pushes close together queue, rather than running two migrations
against one database at once. Alembic takes no lock of its own.

**Each secret reaches only its step.** The migration step sees `DATABASE_URL`. The deploy step
sees the three Vercel values. The health step sees `API_ORIGIN`. `uv sync` and `setup-node` see
none of them.

**The window this order leaves, read from source and not yet measured.** `migration_status`
(`backend/app/core/readiness.py:64-79`, read at `c39ad2e`) returns `current` only when
`alembic_version` equals the deployment's own head, exactly. Between step 1 and the moment step
2's deployment becomes production, the old deployment is still production, and the database is
already ahead of it. A warm instance of it keeps serving, because its lifespan ran before the migration.
A **cold start** of it in that window raises at the boot gate, and that request fails. This happens
only on a push that carries a migration, and the window lasts as long as step 2's upload and
build. Render's container was long-running, so it had no such window. A shorter one is possible:
deploy first with `vercel deploy --prod --skip-domain`, migrate, then `vercel promote` the
deployment (`vercel deploy` reference, read 2026-10-10). #252's issue body set the order used here,
so that change is left to a follow-up.

## What the Vercel files set

### `backend/vercel.json`

| Key | Value | Why |
|---|---|---|
| `framework` | `fastapi` | The project's preset reads `Other` (above). The file names the framework, so the build does not depend on a dashboard field. Vercel's schema lists `fastapi` among its values |
| `regions` | `["sin1"]` | Singapore, next to the Supabase project in `ap-southeast-1`. Hobby allows one region |
| `git.deploymentEnabled` | `false` | CI deploys through the CLI, after the migration. A Git-triggered build would deploy every push without migrating |
| `functions["app/main.py"].maxDuration` | `300` | The Hobby maximum. The key is the entrypoint file (`app/main.py`, which exports `app`) |
| `functions["app/main.py"].excludeFiles` | `tests/**` | Python functions bundle every file the build can reach, with no tree-shaking ("Using the Python Runtime", read 2026-10-10). The bundle limit is 500 MB |
| `crons` | `/internal/cron/anniversary-notifications` at `0 0 * * *`, `/internal/cron/document-purge` at `30 0 * * *` | The two jobs APScheduler ran in-process. Production sets `SCHEDULER_ENABLED=false` (#250, ADR-065) |

**What the crons do and do not guarantee**, read in Vercel's cron docs on 2026-10-10:

- **They run in UTC.** `0 0 * * *` is 07:00 in Asia/Ho_Chi_Minh.
- **Hobby fires anywhere in the named hour.** "An expression like `0 8 * * *` could trigger an
  invocation anytime between `08:00:00` and `08:59:59`." So the anniversary job runs between
  07:00 and 07:59 ICT. The `30` in the purge's expression does not order it after the anniversary
  job. The two do not depend on each other.
- **Delivery is best effort.** A run can be missed. "Cron delivery can also occasionally invoke the
  same scheduled run more than once." Vercel does not retry a failed run. The jobs' locks and
  dedup are what make a second delivery harmless (ADR-065).
- **Each request carries `Authorization: Bearer $CRON_SECRET`.** The endpoints answer anything else
  with the same bare 404 as `/internal/metrics` (#250).
- **The request goes to the production deployment's own generated host, not to the alias.**
  Measured 2026-10-10 (#265): `vercel crons run /internal/cron/document-purge` reached
  `familyroots-9xtnrccz1-namtp.vercel.app`, and `TrustedHostMiddleware` answered `400`, because
  `ALLOWED_HOSTS` names `familyroots-api.vercel.app`. Vercel gives the function that host as the
  system variable `VERCEL_URL`. Since #265 `Settings.trusted_hosts` adds it to `ALLOWED_HOSTS`, so
  `ALLOWED_HOSTS` still names only the production alias. This works only while the project keeps
  "Automatically expose System Environment Variables" on, which is Vercel's default.
- **A path is not checked at build time.** For a path that does not exist, "Vercel still executes
  your cron job" and logs a 404. So a planted wrong path is no negative control for a build. The
  live control is the first scheduled run, read in the function logs.
- **A rollback reverts the crons** to the set the rolled-back deployment declared.

### `backend/.vercelignore`

It lists what `vercel deploy`, run from `backend/`, must never upload: virtualenvs, caches,
`.env*`, credential files (`firebase-credentials.json`, `*credentials*.json`, `*.pem`, `*.key`),
`.vercel/`, and the `Dockerfile`. It must **not** list `migrations/`. `app/core/readiness.py` reads
the head revision from the `migrations` package at run time, and without it every production
boot fails ([migrations.md](migrations.md), "Boot-time migration gate").

`backend/.gitignore` ignores `.vercel`, which `vercel link` writes in `backend/`. The `.env.local`
that `vercel link` also writes is already ignored by the root `.gitignore`.

### `web/vercel.json`
- `"framework": "nextjs"`, for the same reason as the backend's: the project's preset reads `Other`.
- `"git": {"deploymentEnabled": false}`: CI deploys after its gates pass.
- `"regions": ["sin1"]` (Singapore), so the web app's functions run next to the API's functions
  and the database. Every server render that calls the backend goes through
  `apiFetch` (`web/src/shared/http/api-client.ts`), so the distance between the two
  regions is paid on every such request, in both directions.
- Without the file, Vercel runs functions in `iad1` (Washington, D.C.). That is its
  default for new projects ("Configuring regions for Vercel Functions", Vercel docs,
  read 2026-10-10).
- The Hobby plan allows a single function region, so this list must stay at one
  entry until the project moves to Pro. A deployment that names more regions than
  the plan allows fails before the build.
- `regions` does not move `src/middleware.ts`. Vercel deploys Routing Middleware to
  every region whatever this setting says.
- The deploy job runs `vercel deploy` with `working-directory: web`
  (`web-ci.yml`), which is why the file lives in `web/` and not at the repository
  root. The same holds for `backend/`. Both projects' Root Directory must therefore stay `.`.
- **What proves it is a live reading, not the file.** Vercel's schema types
  `regions` only as an array of strings, so a typo such as `sni1` still validates.
  Request a dynamic page on the production deployment
  (`curl -sI https://<prod-host>/vi/login | grep -i x-vercel-id`). The
  `x-vercel-id` header lists the regions the request passed through, including the
  one the function ran in, and that region must be `sin1`. A deployment without the
  file reads `iad1` in the same position. The same read on `$API_ORIGIN/health` checks the API.

### How the files were checked (2026-10-10)

- **Schema.** Both files validate against `https://openapi.vercel.sh/vercel.json` (fetched
  2026-10-10, sha256 `c2b8f703…09e6a0`), under `jsonschema` 4.25.1's Draft 4, Draft 7 and 2020-12
  validators. Two planted defects in a copy of `backend/vercel.json` are each rejected. A cron
  path without its leading slash fails `does not match '^/.*'`. `maxDuration` as the string
  `"300"` fails `is not valid under any of the given schemas`. The schema cannot catch a wrong
  region name or a wrong cron path.
- **Workflows.** `actionlint` 1.7.12, with ShellCheck 0.11.0, reports 0 errors on `backend-ci.yml`
  and `web-ci.yml`. Planted in a copy, a step condition naming a step id that does not exist and an
  unquoted `$url` are both reported.
- **`vercel build` was not run** (Reading 2 of #252). It needs the directory linked to
  `familyroots-api`, and linking was left to the owner. When it runs, it must report
  `app/main.py:app` on Python 3.14 and a function under 500 MB. `backend/.python-version` reads
  `3.14.2`. Vercel's own example writes only `3.13`, and Vercel falls back to 3.12 for a version it
  does not support. On 3.12, `requires-python = ">=3.14"` would then fail the install loudly.

## Migrations relative to deploy
The deploy job's first step runs `alembic upgrade head` and **blocks the deploy on failure**,
the same contract Render's `preDeployCommand` gave. See [migrations.md](migrations.md),
"How migrations reach production".

## Rollback
- **Backend: a code rollback across a migration cannot boot. Downgrade the schema first.** The boot
  gate demands exact equality between `alembic_version` and the deployment's head
  (`readiness.py:79`). Run `alembic downgrade <that deployment's head>` from `backend/`, with
  `DATABASE_URL` set to the session-pooler string. Then roll back the code with
  **Instant Rollback** in the dashboard, or `vercel rollback`. Destructive migrations may not
  reverse cleanly. Prefer a forward fix.
- **Hobby rolls back to the immediately previous deployment only** ("Performing an Instant
  Rollback", read 2026-10-10). After a rollback, Vercel **turns off auto-assignment of production
  domains**. The next CI `vercel deploy --prod` then builds, but does not go live, and the health
  read checks the rolled-back deployment instead. To undo that, promote a deployment:
  `vercel promote <deployment-url>`, or **Undo Rollback** in the dashboard.
- A rollback restores the earlier deployment's build. Environment variables changed since then
  are not applied to it. Its crons replace the current ones.
- **Web:** the same Instant Rollback, with the same Hobby limit and the same domain-assignment
  rule. The web has no migration.

## Go-live checklist

Every step below is an **owner action**. #252 performed none of them. Hosts written `<api-host>`
and `<web-host>` are each project's production domain, from Vercel → Project → Settings → Domains.
Every variable is set for the **Production** environment only. Preview deployments are not set up.

### A. Supabase project `xkmutzxdhdigyfisfrwd` (dashboard and CLI)
- [ ] **A database password with no character that needs URL encoding.** Dashboard → Database →
  Settings → reset the password if it has one. A percent-encoded password breaks
  `migrations/env.py`, which hands the URL to Alembic's `config.set_main_option`. Alembic's config
  parser reads `%` as interpolation. Measured 2026-10-10 with Alembic 1.18.5, the version in
  `backend/uv.lock`: `p%40ss` raises `ValueError: invalid interpolation syntax`, and an
  alphanumeric password is accepted.
- [ ] **Asymmetric JWT signing keys are current.** Dashboard → Project Settings → JWT Keys. The
  backend verifies tokens **only** through the project's JWKS
  (`backend/app/core/security.py:66`), and accepts only the `alg` values the JWKS lists, or ES256
  and RS256 when none is listed (`:93-96`). A token signed with the legacy HS256 secret is refused,
  so every authenticated request would answer 401. Check:
  `curl -s https://xkmutzxdhdigyfisfrwd.supabase.co/auth/v1/.well-known/jwks.json` must list at
  least one key whose `alg` is `ES256` or `RS256`.
- [ ] **Remove `public` from the Data API's exposed schemas.** Dashboard → Project Settings →
  Data API. This is the second lock beside migration `042_close_data_api_on_public`'s revokes
  (ADR-066). The anon key ships in the web bundle. Check by outcome, with the anon key:
  `curl -s "https://xkmutzxdhdigyfisfrwd.supabase.co/rest/v1/user_profiles?select=id&limit=1" -H "apikey: <anon key>"`
  must answer an error, never a JSON array.
- [ ] **Auth URLs.** Dashboard → Authentication → URL Configuration. Set **Site URL** to
  `https://<web-host>`. Add `https://<web-host>/**` under **Redirect URLs**. Since #202 the email
  templates build every link from `{{ .SiteURL }}`, so a wrong Site URL breaks every auth email
  (ADR-063). Google sign-in redirects to `https://<web-host>/api/auth/callback`. The wildcard
  covers it.
- [ ] **Auth providers and email settings**, read and recorded in
  [supabase-hosted-project.md](supabase-hosted-project.md) § 3: Confirm email, OTP length, MFA. If
  Google sign-in is to stay on, enable the provider with its client id and secret. Google's
  console must also list `https://xkmutzxdhdigyfisfrwd.supabase.co/auth/v1/callback`. The retired
  project had Google on (read 2026-10-04). Nothing carried that over.
- [ ] **Buckets.** `supabase link --project-ref xkmutzxdhdigyfisfrwd`, then
  `supabase seed buckets --linked`, which creates the private `family-roots-files` and the public
  `family-roots-avatars` with its MIME list from `supabase/config.toml`. Read them back with
  `supabase db query --linked "select id, public, allowed_mime_types from storage.buckets order by id;"`.
- [ ] **The private `backups` bucket**, by hand. It is not in `config.toml`, so the seed does not
  make it ([backup-restore.md](backup-restore.md), "Go-live checklist").
- [ ] **Email templates (#203).** Push them from `supabase/supabase/config.toml` with
  `--project-ref xkmutzxdhdigyfisfrwd`, then read them back
  ([supabase-hosted-project.md](supabase-hosted-project.md) § 4a, § 4b). #203's body still names
  the retired project's ref.

### B. GitHub repository settings
Secrets (Settings → Secrets and variables → Actions → Secrets):

| Secret | Value | Read by |
|---|---|---|
| `MIGRATION_DATABASE_URL` | Supavisor **session** pooler, port **5432**: `postgresql://postgres.xkmutzxdhdigyfisfrwd:<password>@<pooler-host>:5432/postgres`. Copy the host from Dashboard → Connect → Session pooler | `backend-ci.yml` deploy, step 1 |
| `VERCEL_TOKEN` | a Vercel access token for team `namtp` | both deploy jobs |
| `VERCEL_ORG_ID` | `team_POAVczQHAZ0182nbj5oQrQ0E` | both deploy jobs |
| `VERCEL_API_PROJECT_ID` | `prj_bvR27jsrEOWsD2q1vGeKxwkLAY3Z` | `backend-ci.yml` |
| `VERCEL_WEB_PROJECT_ID` | `prj_TD73V51MFvGHzOYTeclsYVqaEfXT` | `web-ci.yml` |
| `PROD_DATABASE_URL` | the same session-pooler string as `MIGRATION_DATABASE_URL` | `db-backup.yml` |
| `SUPABASE_URL` | `https://xkmutzxdhdigyfisfrwd.supabase.co` | `db-backup.yml` |
| `SUPABASE_SERVICE_ROLE_KEY` | the project's service-role key | `db-backup.yml` |

Variable (Settings → Secrets and variables → Actions → **Variables**). It is not a secret, and the
job prints it:

| Variable | Value | Read by |
|---|---|---|
| `API_ORIGIN` | `https://<api-host>`, no path | `backend-ci.yml` deploy, step 3 |

- [ ] Delete `RENDER_DEPLOY_HOOK` if it was ever set. Nothing reads it now.

### C. Vercel `familyroots-api` → Settings → Environment Variables (Production)

| Variable | Value | What happens without it |
|---|---|---|
| `APP_ENV` | `production` | the production validator and boot gates do not run |
| `APP_SECRET_KEY` | `openssl rand -hex 32` | boot fails on the placeholder |
| `DATABASE_URL` | Supavisor **transaction** pooler, port **6543**: `postgresql://postgres.xkmutzxdhdigyfisfrwd:<password>@<pooler-host>:6543/postgres`. The same `postgres` login as the migration, which migration `041` made a member of `familyroots_app` (ADR-066) | boot fails on a localhost DSN |
| `DB_EXTERNAL_POOLER` | `true` | the engine keeps a QueuePool and psycopg's prepared statements, which break on a transaction pooler (#250) |
| `SCHEDULER_ENABLED` | `false` | APScheduler starts in a function that is frozen between requests (#250) |
| `CRON_SECRET` | `openssl rand -hex 32` | with `SCHEDULER_ENABLED=false`, boot fails below the `METRICS_TOKEN` floor, 32 characters and 8 distinct (#250). Vercel sends it on every cron request |
| `ALLOWED_HOSTS` | `["<api-host>"]` | boot fails on `["*"]` |
| `CORS_ORIGINS` | `["https://<web-host>"]` | boot fails on the localhost defaults |
| `INVITE_LINK_ORIGIN` | `https://<web-host>` | boot fails on empty or localhost (ADR-062) |
| `SUPABASE_URL` | `https://xkmutzxdhdigyfisfrwd.supabase.co` | boot fails |
| `SUPABASE_ANON_KEY` | the project's anon key | boot fails |
| `SUPABASE_SERVICE_ROLE_KEY` | the project's service-role key | boot fails |
| `RATE_LIMIT_TRUST_FORWARDED_FOR` | `true` | boot fails while unset. Vercel overwrites `X-Forwarded-For` "and **do not forward external IPs**. This restriction is in place to prevent IP spoofing" ("Request headers", read 2026-10-10), so the rightmost entry the limiter reads is the client |
| `MAX_UPLOAD_SIZE_MB` | `4` | the server admits 50 MB, and Vercel refuses any body over 4.5 MB with its own 413, which never reaches the app's envelope (#250) |
| `FIREBASE_CREDENTIALS_JSON` *(optional)* | the service-account JSON, inline | push notifications are off, with a warning, not a boot failure (#250) |
| `SENTRY_DSN` *(optional)* | the DSN | Sentry is off |

Leave unset: `APP_DEBUG` (defaults to false; true fails boot), `RATE_LIMIT_AUTH_MAX_REQUESTS`
(production keeps 20, ADR-021), `METRICS_ENABLED` (off until something scrapes), and the pool
sizes, which `DB_EXTERNAL_POOLER=true` makes irrelevant. The full table is
[configuration.md](configuration.md).

### D. Vercel `familyroots-web` → Settings → Environment Variables (Production)

| Variable | Value |
|---|---|
| `NEXT_PUBLIC_API_ORIGIN` | `https://<api-host>`. `apiFetch` appends `/api/v1` |
| `NEXT_PUBLIC_API_URL` | `https://<api-host>/api/v1`. The legacy `src/lib/api/axios.ts` still reads it, for the admin and platform pages |
| `NEXT_PUBLIC_SUPABASE_URL` | `https://xkmutzxdhdigyfisfrwd.supabase.co` |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | the project's anon key |
| `NEXT_PUBLIC_APP_ENV` | `production` |
| `NEXT_PUBLIC_SENTRY_DSN`, `SENTRY_DSN`, `SENTRY_AUTH_TOKEN` *(optional)* | Sentry; source maps upload only with the token |

`NEXT_PUBLIC_*` values are inlined at build time, so a change needs a redeploy. Do **not** set
`API_URL`. It is compose's network-internal backend, and unset on Vercel the server shares the
browser's origin (ADR-056). Do **not** set `SUPABASE_SERVICE_ROLE_KEY` on the web project.
`web/.env.example` lists it, but nothing under `web/src` reads it (`grep`, 2026-10-10). It is a
project-wide admin key.

### E. Vercel project settings (both projects)
- [ ] **Root Directory** stays `.` (read 2026-10-10). The CLI uploads from `backend/` and `web/`.
- [ ] **Deployment Protection** stays at Standard Protection or looser. "All Deployments" would put
  the production host behind a Vercel login, and the health read and the crons with it.
- [ ] **Git**: connecting the repository is optional. Both `vercel.json` files turn Git-triggered
  deployments off.
- [ ] Note each project's production domain. It feeds `API_ORIGIN`, `ALLOWED_HOSTS`,
  `CORS_ORIGINS`, `INVITE_LINK_ORIGIN`, both `NEXT_PUBLIC_API_*` values and the Site URL. Custom
  domains are not covered (#252, out of scope).

### F. First deploy: the readings to take, in order
Do A to E first. A backend deploy with its variables unset fails its own health read.

1. [ ] **The migration log.** In the first `backend-ci` deploy run, `alembic upgrade head` applies
   `001` to `042` to the empty database, and `alembic current` prints
   `042_close_data_api_on_public (head)`.
2. [ ] **Reading 2 of #252**, if it was not taken before: `vercel build` in a `backend/` linked to
   `familyroots-api`. Quote the detected entrypoint, the Python version and the function size.
3. [ ] **`/health`.** The job's own read: `200` with `"migrations":"current"`.
4. [ ] **Regions.** `x-vercel-id` reads `sin1` on `https://<web-host>/vi/login` and on
   `https://<api-host>/health` (§ "web/vercel.json").
5. [ ] **The crons.** Trigger each once with `vercel crons` or the dashboard's Cron Jobs page, or
   wait for 00:00 UTC. Then read the function logs for both paths. Each must show `204`. A `400`
   means the cron's host was refused: check that `VERCEL_URL` reaches the function (#265). A `404`
   means `CRON_SECRET` differs between Vercel and the app, or the route did not ship.
6. [ ] **Auth end to end.** Sign up on `https://<web-host>`. The confirmation email's link must begin
   with `https://<web-host>/verify-email/confirm?token_hash=`.
7. [ ] **Backups.** Run `db-backup` once by hand ([backup-restore.md](backup-restore.md), "Go-live
   checklist"), and read the Supabase-schema caveat there first.

## Known risks
- Pulumi resources are not fully implemented (`infra/` drift risk).
- No staging environment — changes reach production on merge to `main`.
- **The boot gate no longer guards production.** On Vercel a deployment whose lifespan raises is
  production anyway, and the health read in step 3 is the first thing to notice (§ step 2).
- **A deploy that carries a migration leaves a cold-start window** in which the old deployment
  cannot boot (§ "The window this order leaves").
- The rate limiter and the metrics throttle hold their state per instance on serverless. ADR-065
  accepts that.
