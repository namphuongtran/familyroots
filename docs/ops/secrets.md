# Secrets

## Overview
Secrets stay out of the repo by construction (CI gates) and are injected at runtime by
Render / GitHub Actions / Vercel. Config lives in `app/core/config.py`
(`pydantic-settings`, reads `.env`); required vars are in `backend/.env.example`.

## Where secrets live
| Secret | Source |
|--------|--------|
| `APP_SECRET_KEY` | Render `generateValue: true` (per-service) |
| `DATABASE_URL` | Render `fromDatabase` (the managed Postgres connection string) |
| `RENDER_DEPLOY_HOOK` | GitHub Actions secret (backend deploy trigger) |
| `VERCEL_TOKEN` | GitHub Actions secret (web deploy) |
| `CORS_ORIGINS`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SENTRY_DSN` | Declared `sync: false` in `render.yaml` — **set the value in the Render dashboard** (never committed). First four are boot-required; `SENTRY_DSN` optional. See [go-live checklist](#go-live-env-checklist). |
| Firebase FCM creds | Optional (push only) — add the service-account JSON as a Render **Secret File**, point `FIREBASE_CREDENTIALS_PATH` at it |
| `PROD_DATABASE_URL` | GitHub Actions secret (repo settings) — production Postgres DSN, read-only use by `db-backup.yml` to run `pg_dump`; **not yet set** (go-live item, see [backup-restore.md](backup-restore.md#go-live-checklist)) |
| `SUPABASE_URL` *(GitHub Actions)* | GitHub Actions secret (repo settings) — Supabase project URL, used by `db-backup.yml` / `scripts/db_backup.sh` and `scripts/restore_drill.sh --latest` to reach the Storage REST API; **not yet set** |
| `SUPABASE_SERVICE_ROLE_KEY` | GitHub Actions secret (repo settings) — Supabase service-role key, used by `db-backup.yml` / `scripts/restore_drill.sh` to upload/list/delete objects in the private `backups` bucket. **Not bucket-scoped**: this key is a **project-wide admin credential** — it bypasses RLS on every table and grants full read/write on every Storage bucket (including the live `documents` bucket) plus the Supabase auth admin API. A leak from this workflow compromises the *entire* Supabase project, not just backups, and requires rotating all Supabase project keys, not just this secret. **Not yet set**. Prefer provisioning a scoped Storage-only credential (Supabase S3 access keys, restricted to the `backups` bucket) for the backup job when available, keeping the service-role key out of CI entirely — tracked as a go-live follow-up in [backup-restore.md](backup-restore.md#go-live-checklist). |

## Repo-side gates (`.github/workflows/pr-checks.yml`)
- **gitleaks** secret scanning on every PR.
- A **no-committed-`.env`-files** check fails the PR if an env file is committed.
- Never commit secrets or plain `.env` files (repo-root rule).

## Production fail-fast (`app/core/config.py`)
When `APP_ENV=production`, the app **refuses to boot** if any of these is wrong:
placeholder `APP_SECRET_KEY`; `APP_DEBUG=true` (also gates `/docs`+`/redoc`);
wildcard `ALLOWED_HOSTS`; a localhost `DATABASE_URL`; wildcard/localhost
`CORS_ORIGINS`; missing `SUPABASE_URL` / `SUPABASE_ANON_KEY` /
`SUPABASE_SERVICE_ROLE_KEY`; or unset `RATE_LIMIT_TRUST_FORWARDED_FOR`. The full
field-by-field table is in [configuration.md](configuration.md). `render.yaml`
satisfies every one of these (committed values + `sync: false` dashboard vars).

## Go-live env checklist
The blueprint declares everything; the only manual step is filling the
`sync: false` values in the **Render dashboard** on first apply:

- [ ] `CORS_ORIGINS` → JSON list of the web app's production origin(s), e.g.
  `["https://app.example.com"]` (must be valid JSON; no wildcard/localhost).
- [ ] `SUPABASE_URL` → `https://<project>.supabase.co`.
- [ ] `SUPABASE_ANON_KEY` → Supabase anon/publishable key.
- [ ] `SUPABASE_SERVICE_ROLE_KEY` → Supabase service-role key (project-wide admin — treat as top secret).
- [ ] `SENTRY_DSN` *(optional)* → leave blank to run without Sentry.
- [ ] *(optional, push)* Firebase service-account JSON as a Render Secret File + `FIREBASE_CREDENTIALS_PATH`.

`APP_SECRET_KEY` (generated), `DATABASE_URL` (from the managed DB), `ALLOWED_HOSTS`,
`APP_DEBUG=false`, and `RATE_LIMIT_TRUST_FORWARDED_FOR=true` are handled by the
blueprint — no manual entry. Separate go-live tracks: GitHub Actions backup secrets
(`PROD_DATABASE_URL` etc., see [backup-restore.md](backup-restore.md#go-live-checklist))
and `RENDER_DEPLOY_HOOK` / `VERCEL_TOKEN` for the deploy workflows.

## Rotation
- `APP_SECRET_KEY`: regenerate in Render (invalidates anything signed with it).
- `DATABASE_URL`: rotate the DB credential in Render; the service picks it up on
  redeploy.
- Deploy hooks / tokens: rotate in the provider, update the GitHub Actions secret.
- `PROD_DATABASE_URL` / `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` (backup):
  rotate at the source (Render DB credential / Supabase project settings),
  then update the GitHub Actions secret — no app redeploy needed since only
  the nightly `db-backup.yml` workflow reads them.

## Known gaps
- App-boot env is fully wired: `render.yaml` declares every fail-fast var, and the
  validator now covers `DATABASE_URL` (localhost), `CORS_ORIGINS`, the Supabase
  keys, and `RATE_LIMIT_TRUST_FORWARDED_FOR` in addition to secret/debug/host. The
  only remaining go-live step is filling the `sync: false` dashboard values above.
- Still outstanding (separate tracks, not app-boot): GitHub Actions backup secrets
  (`PROD_DATABASE_URL` / `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` for
  `db-backup.yml`) and deploy secrets (`RENDER_DEPLOY_HOOK`, `VERCEL_TOKEN`).
- Firebase service-role backup credential should ideally be a Storage-scoped key,
  not the project-wide service-role key (tracked in backup-restore.md).
