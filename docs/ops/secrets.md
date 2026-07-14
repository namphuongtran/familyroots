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
| `SUPABASE_URL` / keys, `SENTRY_DSN`, Firebase creds, `CORS_ORIGINS` | **TODO**: add to `render.yaml` env before go-live |
| `PROD_DATABASE_URL` | GitHub Actions secret (repo settings) — production Postgres DSN, read-only use by `db-backup.yml` to run `pg_dump`; **not yet set** (go-live item, see [backup-restore.md](backup-restore.md#go-live-checklist)) |
| `SUPABASE_URL` *(GitHub Actions)* | GitHub Actions secret (repo settings) — Supabase project URL, used by `db-backup.yml` / `scripts/db_backup.sh` and `scripts/restore_drill.sh --latest` to reach the Storage REST API; **not yet set** |
| `SUPABASE_SERVICE_ROLE_KEY` | GitHub Actions secret (repo settings) — Supabase service-role key, used by `db-backup.yml` / `scripts/restore_drill.sh` to upload/list/delete objects in the private `backups` bucket. **Not bucket-scoped**: this key is a **project-wide admin credential** — it bypasses RLS on every table and grants full read/write on every Storage bucket (including the live `documents` bucket) plus the Supabase auth admin API. A leak from this workflow compromises the *entire* Supabase project, not just backups, and requires rotating all Supabase project keys, not just this secret. **Not yet set**. Prefer provisioning a scoped Storage-only credential (Supabase S3 access keys, restricted to the `backups` bucket) for the backup job when available, keeping the service-role key out of CI entirely — tracked as a go-live follow-up in [backup-restore.md](backup-restore.md#go-live-checklist). |

## Repo-side gates (`.github/workflows/pr-checks.yml`)
- **gitleaks** secret scanning on every PR.
- A **no-committed-`.env`-files** check fails the PR if an env file is committed.
- Never commit secrets or plain `.env` files (repo-root rule).

## Production fail-fast (`app/core/config.py`)
When `APP_ENV=production`, the app **refuses to boot** if:
- `APP_SECRET_KEY` is still the default placeholder,
- `APP_DEBUG` is true (also gates `/docs` + `/redoc` exposure), or
- `ALLOWED_HOSTS` is `["*"]` (wildcard).
`render.yaml` supplies an explicit JSON `ALLOWED_HOSTS` to satisfy this.

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
- Several production secrets are not yet wired (`render.yaml` TODO) — the fail-fast
  validator currently covers secret/debug/host but **not** `DATABASE_URL` or
  `CORS_ORIGINS` presence (a forgotten DSN boots against localhost; tracked for
  hardening).
