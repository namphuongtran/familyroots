# Secrets

## Overview
Secrets stay out of the repo by construction (CI gates) and are injected at runtime by
Vercel (both apps) and GitHub Actions (migrations, deploys, backups). Config lives in
`app/core/config.py` (`pydantic-settings`, reads `.env`); required vars are in
`backend/.env.example`. Render injected them until 2026-10-10. It is retired, and
`infra/render/render.yaml` is deleted (#252). The go-live checklist with every value is
[deployment.md](deployment.md), "Go-live checklist".

## Where secrets live
| Secret | Source |
|--------|--------|
| `APP_SECRET_KEY` | Vercel `familyroots-api` env, Production. Generate with `openssl rand -hex 32` |
| `DATABASE_URL` | Vercel `familyroots-api` env. Supavisor's **transaction** pooler (`:6543`) on Supabase project `xkmutzxdhdigyfisfrwd`, with `DB_EXTERNAL_POOLER=true` |
| `CRON_SECRET` | Vercel `familyroots-api` env. Vercel sends it as `Authorization: Bearer …` on every cron request, and the app refuses to boot below the `METRICS_TOKEN` floor while `SCHEDULER_ENABLED=false` (#250). Generate with `openssl rand -hex 32` |
| `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY` | Vercel `familyroots-api` env. Boot-required |
| `CORS_ORIGINS`, `INVITE_LINK_ORIGIN`, `ALLOWED_HOSTS` | Vercel `familyroots-api` env. Not secrets, but boot-required and different per deployment |
| `SENTRY_DSN` | Vercel `familyroots-api` env, optional |
| Firebase FCM creds | Optional (push only). `FIREBASE_CREDENTIALS_JSON`, the service-account JSON inline, in Vercel `familyroots-api` env (#250). A function has no secret file to mount |
| `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_API_ORIGIN`, `NEXT_PUBLIC_API_URL` | Vercel `familyroots-web` env. Inlined into the browser bundle at build time, so none of them is secret. The web project holds **no** service-role key |
| `SENTRY_AUTH_TOKEN` | Vercel `familyroots-web` env, optional. Uploads source maps at build time |
| `MIGRATION_DATABASE_URL` | GitHub Actions secret, in the `production` environment. Supavisor's **session** pooler (`:5432`), read only by `release.yml`'s `deploy` job to run `alembic upgrade head` ([migrations.md](migrations.md), "How migrations reach production") |
| `VERCEL_TOKEN` | GitHub Actions secret, in the `production` environment. Both deploy steps of `release.yml` |
| `VERCEL_ORG_ID`, `VERCEL_API_PROJECT_ID`, `VERCEL_WEB_PROJECT_ID` | GitHub Actions secrets, in the `production` environment. Not secret values (they are in [deployment.md](deployment.md)), but CI reads them from secrets |
| `API_ORIGIN` | GitHub Actions **variable**, not a secret, in the `production` environment. The production API origin `release.yml` reads `/health` from |
| `PROD_DATABASE_URL` | GitHub Actions secret (repo settings) — production Postgres DSN, read-only use by `db-backup.yml` to run `pg_dump`. Since 2026-10-10 it is the same session-pooler string as `MIGRATION_DATABASE_URL`; **not yet set** (go-live item, see [backup-restore.md](backup-restore.md#go-live-checklist)) |
| `SUPABASE_URL` *(GitHub Actions)* | GitHub Actions secret (repo settings) — Supabase project URL, used by `db-backup.yml` / `scripts/db_backup.sh` and `scripts/restore_drill.sh --latest` to reach the Storage REST API; **not yet set** |
| `SUPABASE_SERVICE_ROLE_KEY` | GitHub Actions secret (repo settings) — Supabase service-role key, used by `db-backup.yml` / `scripts/restore_drill.sh` to upload/list/delete objects in the private `backups` bucket. **Not bucket-scoped**: this key is a **project-wide admin credential** — it bypasses RLS on every table and grants full read/write on every Storage bucket (including the live `documents` bucket) plus the Supabase auth admin API. **Since 2026-10-10 the application database lives in the same project**, so it also bypasses RLS on every application table. A leak from this workflow compromises the *entire* Supabase project, not just backups, and requires rotating all Supabase project keys, not just this secret. **Not yet set**. Prefer provisioning a scoped Storage-only credential (Supabase S3 access keys, restricted to the `backups` bucket) for the backup job when available, keeping the service-role key out of CI entirely — tracked as a go-live follow-up in [backup-restore.md](backup-restore.md#go-live-checklist). |

## Repo-side gates (`.github/workflows/pr-checks.yml`)
- **gitleaks** secret scanning on every PR.
- A **no-committed-`.env`-files** check fails the PR if an env file is committed.
- Never commit secrets or plain `.env` files (repo-root rule).
- `vercel link` writes `.vercel/project.json` and a `.env.local` holding a `VERCEL_OIDC_TOKEN`.
  `backend/.gitignore` and `web/.gitignore` ignore `.vercel`, and the root `.gitignore` ignores
  `.env.local`. `backend/.vercelignore` keeps `.env*` and credential files out of an upload.

## Production fail-fast (`app/core/config.py`)
When `APP_ENV=production`, the app **refuses to boot** if any of these is wrong:
placeholder `APP_SECRET_KEY`; `APP_DEBUG=true` (also gates `/docs`+`/redoc`);
wildcard `ALLOWED_HOSTS`; a localhost `DATABASE_URL`; wildcard/localhost
`CORS_ORIGINS`; an empty or localhost `INVITE_LINK_ORIGIN`; missing `SUPABASE_URL` / `SUPABASE_ANON_KEY` /
`SUPABASE_SERVICE_ROLE_KEY`; unset `RATE_LIMIT_TRUST_FORWARDED_FOR`; or, with
`SCHEDULER_ENABLED=false`, a `CRON_SECRET` under the floor (#250). The full
field-by-field table is in [configuration.md](configuration.md).

**On Vercel, "refuses to boot" does not keep the old version serving.** Nothing requests a
deployment before it goes live, so a production deployment with a missing variable is live and
fails every cold start. The release's `/health` read is the first thing to see it
([deployment.md](deployment.md), "The release workflow, step by step"). Set every variable
before the first deploy.

## Go-live env checklist
Moved to [deployment.md](deployment.md), "Go-live checklist", which names every variable per
Vercel project, every GitHub secret and variable, and every Supabase dashboard setting. There was
no blueprint step left to keep here: Vercel has no equivalent of `render.yaml`'s
`generateValue` or `fromDatabase`, so `APP_SECRET_KEY` and `DATABASE_URL` are now set by hand like
the rest.

## Rotation
- `APP_SECRET_KEY`: set a new value in the Vercel project, then redeploy (invalidates anything
  signed with it). A changed variable does not reach a deployment built before it ("Performing an
  Instant Rollback", read 2026-10-10, says the same of a rolled-back build).
- `DATABASE_URL` / `MIGRATION_DATABASE_URL` / `PROD_DATABASE_URL`: they share one database
  password. Reset it in the Supabase dashboard (letters and digits only, see
  [migrations.md](migrations.md)), then update the Vercel variable, redeploy, and update both
  GitHub secrets.
- `CRON_SECRET`: set the new value in Vercel and redeploy. Then read the next cron run's log
  for a `200`. Which value a cron request carries between the change and the redeploy was not
  checked.
- `VERCEL_TOKEN`: create a new token in Vercel, update the GitHub secret, revoke the old one.
- `SUPABASE_SERVICE_ROLE_KEY` / `SUPABASE_ANON_KEY`: rotate in the Supabase project, then update
  the Vercel variables (both projects for the anon key; the web needs a rebuild because it is
  inlined) and the GitHub secret.

## Known gaps
- App-boot env is no longer declared in a file. With `render.yaml` gone, the list lives only in
  [deployment.md](deployment.md)'s checklist and in `config.py`'s validator. Nothing compares the
  Vercel project's variables with that list. A missing one shows at the first cold start.
- Still outstanding (owner go-live actions): every Vercel variable, the deploy secrets
  (`MIGRATION_DATABASE_URL`, `VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_API_PROJECT_ID`,
  `VERCEL_WEB_PROJECT_ID`, the `API_ORIGIN` variable), and the backup secrets
  (`PROD_DATABASE_URL` / `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` for `db-backup.yml`).
- The backup credential should ideally be a Storage-scoped key, not the project-wide
  service-role key (tracked in backup-restore.md).
