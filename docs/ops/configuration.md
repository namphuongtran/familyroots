# Configuration Reference

Every backend setting lives in `backend/app/core/config.py` (`pydantic-settings`,
reads `.env` + environment, `extra="ignore"`). This is the complete field list;
secret *storage/rotation* is covered in [secrets.md](secrets.md).

## Settings fields

| Field | Default | Meaning | Production requirement |
|---|---|---|---|
| `APP_ENV` | `development` | Environment name; `production` arms the fail-fast validator | `production` (set in render.yaml) |
| `APP_SECRET_KEY` | `change-me-in-production` | App signing secret | **Boot fails** if left at the placeholder (render.yaml: `generateValue`) |
| `APP_DEBUG` | `false` | Debug mode; also gates `/docs` + `/redoc` | **Boot fails** if `true` |
| `APP_PORT` | `8000` | Dev port hint | — |
| `DATABASE_URL` | localhost DSN | Postgres DSN; normalized (see below) | **Boot fails** if it contains `localhost`/`127.0.0.1` (render.yaml: `fromDatabase`) |
| `SUPABASE_URL` | `""` | Supabase project URL (auth JWKS, storage) | **Boot fails** if empty |
| `SUPABASE_SERVICE_ROLE_KEY` | `""` | Service-role key (register/storage; bypasses RLS) | **Boot fails** if empty |
| `SUPABASE_ANON_KEY` | `""` | Anon key (sign-in) | **Boot fails** if empty |
| `SUPABASE_STORAGE_BUCKET` | `family-roots-files` | Blob bucket ([storage](../architecture/storage.md)) | Default is correct |
| `FIREBASE_CREDENTIALS_PATH` | `./firebase-credentials.json` | FCM service-account file | Optional — missing file just disables pushes (warning) |
| `SENTRY_DSN` | `""` | Sentry error reporting | Optional — empty disables Sentry |
| `CORS_ORIGINS` | localhost:3000/8080 | Allowed browser origins (JSON list) | **Boot fails** if `["*"]` or any localhost origin |
| `ALLOWED_HOSTS` | `["*"]` | TrustedHost allow-list (JSON list) | **Boot fails** if `["*"]` (render.yaml sets it) |
| `RATE_LIMIT_TRUST_FORWARDED_FOR` | unset (dev resolves `false`) | Trust `X-Forwarded-For` for rate-limit + audit IPs | **Required explicitly in production** (boot fails if unset): `true` behind a trusted proxy/LB (Render), `false` when directly exposed |
| `MAX_UPLOAD_SIZE_MB` | `50` (derived from domain policy) | Platform-wide upload cap; `max_upload_bytes` property is what handlers use | Tune as needed |
| `SCHEDULER_TIMEZONE` | `Asia/Ho_Chi_Minh` | Single platform clock for the cron **and** its date math | **Boot fails** on a non-IANA name (any env) |
| `NOTIFICATION_CRON_HOUR` | `7` | Daily anniversary-job hour in the platform zone (the `document_purge` job also keys off this hour, at `minute=30`) | — |
| `DOCUMENT_RETENTION_DAYS` | `30` | Days a soft-deleted document's row+blob survive before the daily `document_purge` job permanently removes them ([ADR-019](../decisions/019-document-soft-delete-purge.md)) | Tune per data-retention policy |
| `PASSWORD_RESET_REDIRECT_URL` | `""` | Recovery-email landing page | Empty → Supabase Site URL fallback |
| `EMAIL_VERIFY_REDIRECT_URL` | `""` | Signup-confirmation landing page | Empty → Supabase Site URL fallback |
| `INVITATION_TTL_DAYS` | `7` | Invitation link lifetime | — |

## Validators (fail-fast at boot)

- **`DATABASE_URL` driver normalization** (any env): every Postgres URL form —
  Render's bare `postgresql://` (historically `postgres://`), legacy `+asyncpg` or
  `+psycopg2` — is rewritten to the canonical `postgresql+psycopg://`, so the async
  engine and Alembic (sync) always see one psycopg v3 URL. Non-Postgres URLs pass
  through untouched.
- **`SCHEDULER_TIMEZONE`** (any env): must resolve via `ZoneInfo`, with a clear error
  instead of an opaque failure at scheduler import.
- **Production safety** (`APP_ENV=production` only) — the app **refuses to boot** on:
  placeholder `APP_SECRET_KEY`; `APP_DEBUG=true`; wildcard `ALLOWED_HOSTS`; a
  localhost `DATABASE_URL`; wildcard-or-localhost `CORS_ORIGINS` (`"*"` is also
  invalid with `allow_credentials=True`); missing `SUPABASE_URL`,
  `SUPABASE_ANON_KEY`, or `SUPABASE_SERVICE_ROLE_KEY`.

## What render.yaml sets today (`infra/render/render.yaml`)

Currently wired: `APP_ENV=production`, `DATABASE_URL` (`fromDatabase`),
`APP_SECRET_KEY` (`generateValue`), `ALLOWED_HOSTS`.

**Not yet set** (the file's own TODO): `SUPABASE_URL` + both Supabase keys,
`CORS_ORIGINS`, `SENTRY_DSN`, and Firebase credentials. Consequence: with today's
blueprint the production validator **will refuse to boot** (default `CORS_ORIGINS`
contains localhost; Supabase vars are empty) — the missing env vars are a hard
go-live blocker, not a nice-to-have. See the go-live checklist angle in
[secrets.md](secrets.md); note that secrets.md's "Known gaps" section predates the
current validator, which now *does* cover `DATABASE_URL`, `CORS_ORIGINS`, and the
Supabase keys.

Notes:

- List-typed vars (`ALLOWED_HOSTS`, `CORS_ORIGINS`) must be **JSON arrays** in env
  (pydantic-settings parses complex types as JSON), e.g. `'["https://app.example.com"]'`.
- `docker-compose.yml` also passes `SUPABASE_JWT_SECRET`, which is **not** a Settings
  field (silently ignored; JWT validation uses JWKS, not a shared secret).

## Related

- [secrets.md](secrets.md) — where each secret lives and how to rotate it
- [deployment.md](deployment.md) — Render blueprint, pre-deploy migrations
- [../architecture/notifications-scheduler.md](../architecture/notifications-scheduler.md) — scheduler knobs in context
- [../architecture/storage.md](../architecture/storage.md) — `DOCUMENT_RETENTION_DAYS` in the delete/purge lifecycle
