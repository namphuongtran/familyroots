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
| `DB_POOL_SIZE` | `10` | Async engine `pool_size` ([ADR-028](../decisions/028-no-external-io-holding-db-connection.md)) | Tune with headroom math below |
| `DB_MAX_OVERFLOW` | `20` | Async engine `max_overflow` ([ADR-028](../decisions/028-no-external-io-holding-db-connection.md)) | Tune with headroom math below |

## DB connection pool headroom (ADR-028)

`DB_POOL_SIZE` / `DB_MAX_OVERFLOW` are sourced by `make_engine(settings)`
(`backend/app/core/database.py`) into `create_async_engine(...)` — env-tunable
so pool sizing can change per environment without a code change. Defaults
(`10`/`20`) match the values that were previously hardcoded.

Sizing them safely means keeping the platform's **total possible connection
count** under the database provider's ceiling:

```
(DB_POOL_SIZE + DB_MAX_OVERFLOW + N_background_jobs) × instances ≤ provider connection ceiling
```

- `N_background_jobs = 2` — the in-process scheduler's `anniversary_notifications`
  and `document_purge` jobs (`app/services/scheduler.py`,
  `app/services/document_purge.py`) each open their **own** dedicated
  `engine.connect()` outside the pooled sessionmaker (see
  [notifications-scheduler.md](../architecture/notifications-scheduler.md) — the
  advisory-lock topology requires a connection dedicated to the job, not one
  borrowed from a request's session), so they add to the per-instance
  connection count on top of the pool.
- `instances` — the number of running app replicas (Render service instance
  count).
- Supabase's **small-tier direct-connection ceiling is roughly 60**. With the
  defaults (`10 + 20 = 30` per instance) and 2 background-job connections, two
  instances already reach `(30 + 2) × 2 = 64` — over that ceiling. Lower
  `DB_POOL_SIZE`/`DB_MAX_OVERFLOW`, or point at Supabase's transaction-mode
  pooler (pgbouncer, see the note in `app/core/database.py` about
  `prepare_threshold`) for higher effective headroom, before scaling instance
  count on the small tier.
- This formula caps the **connection budget**; it does not by itself prevent a
  connection from being held idle-in-transaction across slow external I/O —
  that's the separate hygiene rule in [ADR-028](../decisions/028-no-external-io-holding-db-connection.md)
  (no external network I/O while holding a pooled connection), which is what
  actually stops uploads/exports from starving the pool regardless of size.

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

## What render.yaml sets (`infra/render/render.yaml`)

The blueprint now declares **every** var the production validator requires — so a
fresh blueprint apply boots once the dashboard values below are filled.

**Set directly in the blueprint (committed):**
`APP_ENV=production`, `APP_DEBUG=false`, `DATABASE_URL` (`fromDatabase`),
`APP_SECRET_KEY` (`generateValue`), `ALLOWED_HOSTS`, `RATE_LIMIT_TRUST_FORWARDED_FOR=true`
(Render terminates TLS at a trusted proxy, so `X-Forwarded-For` is trustworthy),
`DB_POOL_SIZE=10` / `DB_MAX_OVERFLOW=20` (ADR-028 defaults, documented — not
secrets — tune per the headroom formula above before scaling instance count).

**Declared `sync: false` — you set the value in the Render dashboard, never in git**
(Render prompts on first apply and won't overwrite):
`CORS_ORIGINS` (JSON list of the web origin(s), e.g. `["https://app.example.com"]`),
`SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, and `SENTRY_DSN`
(optional — leave blank to disable Sentry).

**Firebase FCM** (`FIREBASE_CREDENTIALS_PATH`) is **optional for boot** — a missing
file only disables push notifications (warning, not a boot failure). To enable,
add the service-account JSON as a Render **Secret File** and point
`FIREBASE_CREDENTIALS_PATH` at its mount path.

Verified: with the six committed vars + the four required dashboard vars set, the
production validator boots; omitting any one of `CORS_ORIGINS` / the three Supabase
vars / `RATE_LIMIT_TRUST_FORWARDED_FOR` makes it refuse to boot. The go-live
dashboard checklist lives in [secrets.md](secrets.md#go-live-env-checklist).

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
