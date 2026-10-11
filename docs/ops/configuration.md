# Configuration Reference

Every backend setting lives in `backend/app/core/config.py` (`pydantic-settings`,
reads `.env` + environment, `extra="ignore"`). This is the complete field list;
secret *storage/rotation* is covered in [secrets.md](secrets.md).

## Settings fields

| Field | Default | Meaning | Production requirement |
|---|---|---|---|
| `APP_ENV` | `development` | Environment name; `production` arms the fail-fast validator | `production` |
| `APP_SECRET_KEY` | `change-me-in-production` | App signing secret | **Boot fails** if left at the placeholder. Generate with `openssl rand -hex 32` |
| `APP_DEBUG` | `false` | Debug mode; also gates `/docs` + `/redoc` | **Boot fails** if `true` |
| `APP_PORT` | `8000` | Dev port hint | — |
| `DATABASE_URL` | localhost DSN | Postgres DSN; normalized (see below) | **Boot fails** if it contains `localhost`/`127.0.0.1`. On Vercel it is Supavisor's transaction pooler, with `DB_EXTERNAL_POOLER=true` |
| `SUPABASE_URL` | `""` | Supabase project URL (auth JWKS, storage) | **Boot fails** if empty |
| `SUPABASE_SERVICE_ROLE_KEY` | `""` | Service-role key (register/storage; bypasses RLS) | **Boot fails** if empty |
| `SUPABASE_ANON_KEY` | `""` | Anon key (sign-in) | **Boot fails** if empty |
| `SUPABASE_STORAGE_BUCKET` | `family-roots-files` | **Private** blob bucket ([storage](../architecture/storage.md)) | Default is correct. The bucket must **exist** in each environment: `supabase seed buckets --linked` creates it from `supabase/config.toml`. On the hosted project it was created on 2026-10-04 ([supabase-hosted-project.md](supabase-hosted-project.md) § 2) |
| `SUPABASE_AVATAR_BUCKET` | `family-roots-avatars` | **Public-read** avatars bucket (ADR-036). Must differ from `SUPABASE_STORAGE_BUCKET` | Default is correct. The bucket must exist **and be public**, or set-avatar returns `503 storage_bucket_not_configured`. `supabase seed buckets --linked` creates it public from `supabase/config.toml`. On the hosted project it was created on 2026-10-04 and verified by an anonymous fetch ([supabase-hosted-project.md](supabase-hosted-project.md) § 2) |
| `AVATAR_CACHE_CONTROL_SECONDS` | `300` | `Cache-Control: max-age` on published avatars. The path is stable per person, so this is how long a replaced portrait can still be served stale | Tune for cacheability vs freshness |
| `FIREBASE_CREDENTIALS_PATH` | `./firebase-credentials.json` | FCM service-account file. Read only when `FIREBASE_CREDENTIALS_JSON` is empty | Optional — missing file just disables pushes (warning) |
| `FIREBASE_CREDENTIALS_JSON` | `""` | The FCM service-account key file's **whole content, inline** ([ADR-065](../decisions/065-the-backend-runs-on-vercel-functions.md)), for hosts with no file mount, such as Vercel Functions. When set it wins over `FIREBASE_CREDENTIALS_PATH`. A value that is not a JSON object, or not a valid service account, disables pushes with a warning that never quotes the value | Optional. On Vercel, set it as a sensitive environment variable (deploy issue, #252). Empty means the path is used |
| `SENTRY_DSN` | `""` | Sentry error reporting | Optional — empty disables Sentry |
| `CORS_ORIGINS` | localhost:3000/8080 | Allowed browser origins (JSON list) | **Boot fails** if `["*"]` or any loopback origin, `localhost` or `127.0.0.1` (#231) |
| `ALLOWED_HOSTS` | `["*"]` | TrustedHost allow-list (JSON list) | **Boot fails** if `["*"]`. On Vercel it names the production alias |
| `VERCEL_URL` | `""` | Set by Vercel, never by hand: this deployment's own generated host. `trusted_hosts` adds it to an explicit `ALLOWED_HOSTS`, because Vercel Cron calls that host (#265) | — |
| `RATE_LIMIT_TRUST_FORWARDED_FOR` | unset (dev resolves `false`) | Trust `X-Forwarded-For` for rate-limit + audit IPs | **Required explicitly in production** (boot fails if unset): `true` behind a trusted proxy that overwrites `X-Forwarded-For`, as Vercel does ([deployment.md](deployment.md), "Go-live checklist" C), `false` when directly exposed |
| `RATE_LIMIT_AUTH_MAX_REQUESTS` | `20` | Requests one client IP may send to `/api/v1/auth` and `/api/v1/invitations`, one shared bucket, per 60-second window ([ADR-021](../decisions/021-non-enumerating-auth-surfaces.md) Decision 3, amended by #226). The window is fixed. **Boot fails** below 1, in any environment, because 0 refuses every sign-in | **Leave unset**: production's budget is 20, and raising it weakens the mitigations ADR-021 cites, so it needs an ADR. Not refused under `production`, because the image e2e job boots that way with it raised. Only the authenticated e2e harness's backend sets it, to `1000` (`web/CLAUDE.md`, `image-e2e.yml`) |
| `MAX_UPLOAD_SIZE_MB` | `50` (derived from domain policy) | Platform-wide upload cap; `max_upload_bytes` property is what handlers use. Enforced twice: at signing, on the declared size, and at confirm, on the size Storage recorded (ADR-068) | Tune as needed. Keep it at or under the bucket's `file_size_limit` (50 MiB), which refuses a larger PUT first |
| `SCHEDULER_TIMEZONE` | `Asia/Ho_Chi_Minh` | Single platform clock for the cron **and** its date math | **Boot fails** on a non-IANA name (any env) |
| `NOTIFICATION_CRON_HOUR` | `7` | Daily anniversary-job hour in the platform zone (the `document_purge` job also keys off this hour, at `minute=30`). Read by APScheduler only; under Vercel Cron the schedule lives in the deploy configuration, in UTC | — |
| `SCHEDULER_ENABLED` | `true` | Which trigger path runs the two scheduled jobs ([ADR-065](../decisions/065-the-backend-runs-on-vercel-functions.md), [notifications-scheduler.md](../architecture/notifications-scheduler.md)). `true`: the lifespan starts and stops the in-process APScheduler. `false`: it does not, and Vercel Cron calls `GET /internal/cron/anniversary-notifications` and `GET /internal/cron/document-purge` | `false` on Vercel Functions, where a frozen instance's timer never fires (set by the deploy issue, #252). `true` for a long-running process. **Boot fails** in production with `false` unless `CRON_SECRET` is strong |
| `CRON_SECRET` | `""` | The bearer secret Vercel Cron sends as `Authorization: Bearer <CRON_SECRET>` to the two `/internal/cron/*` routes, compared in constant time. Empty, or below the `METRICS_TOKEN` floor (≥32 characters, ≥8 distinct, ADR-040): both routes answer 404 to everything, in any environment | **Boot fails** in production with `SCHEDULER_ENABLED=false` unless it clears the floor. Generate with `openssl rand -hex 32`. Vercel sends the project's `CRON_SECRET` environment variable, so the backend and Vercel Cron read one value |
| `DOCUMENT_RETENTION_DAYS` | `30` | Days a soft-deleted document's row+blob survive before the daily `document_purge` job permanently removes them ([ADR-019](../decisions/019-document-soft-delete-purge.md)) | Tune per data-retention policy |
| `INVITATION_TTL_DAYS` | `7` | Invitation link lifetime | — |
| `INVITE_LINK_ORIGIN` | `http://localhost:3000` | Origin of the **web** app that `invite_url` in the create-invitation response is built on: `<origin>/<locale>/invitations/<token>` ([ADR-062](../decisions/062-the-backend-composes-the-invitation-link.md)). A trailing slash is tolerated. Not the API origin: the API answers that path with a 404 | **Boot fails** if empty or it names `localhost`/`127.0.0.1`. Set it in the Vercel `familyroots-api` env before the first deploy, or every cold start of that deployment fails |
| `DB_POOL_SIZE` | `10` | Async engine `pool_size` ([ADR-028](../decisions/028-no-external-io-holding-db-connection.md)) | Tune with headroom math below |
| `DB_MAX_OVERFLOW` | `20` | Async engine `max_overflow` ([ADR-028](../decisions/028-no-external-io-holding-db-connection.md)) | Tune with headroom math below |
| `DB_EXTERNAL_POOLER` | `false` | `DATABASE_URL` points at a **transaction pooler**: Supabase's Supavisor on `:6543`, which is how the backend reaches Postgres from Vercel Functions ([ADR-065](../decisions/065-the-backend-runs-on-vercel-functions.md)). `true` builds the engine with `NullPool` and passes `prepare_threshold=None` to psycopg, and `DB_POOL_SIZE`/`DB_MAX_OVERFLOW` are then ignored. `false` keeps the sized QueuePool exactly as ADR-028 built it | `true` wherever `DATABASE_URL` names a transaction pooler, so on Vercel (set by the deploy issue, #252). Leave `false` for a direct Postgres or Docker's `pgdb`. Nothing validates the pairing, so a pooler URL with `false` boots and then fails per request with `DuplicatePreparedStatement` |

## DB connection pool headroom (ADR-028)

`DB_POOL_SIZE` / `DB_MAX_OVERFLOW` are sourced by `make_engine(settings)`
(`backend/app/core/database.py`) into `create_async_engine(...)` — env-tunable
so pool sizing can change per environment without a code change. Defaults
(`10`/`20`) match the values that were previously hardcoded.

Sizing them safely means keeping the platform's **total possible connection
count** under the database provider's ceiling:

```
(DB_POOL_SIZE + DB_MAX_OVERFLOW) × instances ≤ provider connection ceiling
```

- **The background jobs draw from the same pool; they do not add to it.**
  Corrected 2026-10-10 (#250): this section used to add `N_background_jobs = 2`
  on top, saying each job's `engine.connect()` sat "outside the pooled
  sessionmaker". It does not. `engine.connect()` checks out of the very pool
  `make_engine` built (`app/core/database.py`), as every request session does.
  Since ADR-065 each job holds **two** of them while it runs: its lock connection
  and its work session (see
  [notifications-scheduler.md](../architecture/notifications-scheduler.md)). So
  a job in progress takes headroom away from requests, but it cannot push an
  instance past `DB_POOL_SIZE + DB_MAX_OVERFLOW`.
- `instances` — the number of app processes running at once, each with its own
  pool.
- Supabase's **small-tier direct-connection ceiling is roughly 60**. With the
  defaults (`10 + 20 = 30` per instance), two instances already reach `60`, the
  whole ceiling. Lower `DB_POOL_SIZE`/`DB_MAX_OVERFLOW` before scaling instance
  count on the small tier, or move behind Supabase's transaction pooler with
  `DB_EXTERNAL_POOLER=true`.
- **Behind a transaction pooler (`DB_EXTERNAL_POOLER=true`, ADR-065) this
  formula does not apply.** The engine uses `NullPool`, so an instance holds
  a connection only while a request or a job is using it, and the pooler
  multiplexes those client connections onto its own server pool. The limit
  that matters there is the pooler's client-connection limit, and the number
  of instances Vercel runs at once, not `DB_POOL_SIZE`.
- This formula caps the **connection budget**; it does not by itself prevent a
  connection from being held idle-in-transaction across slow external I/O —
  that's the separate hygiene rule in [ADR-028](../decisions/028-no-external-io-holding-db-connection.md)
  (no external network I/O while holding a pooled connection), which is what
  actually stops uploads/exports from starving the pool regardless of size.

## Validators (fail-fast at boot)

- **`DATABASE_URL` driver normalization** (any env): every Postgres URL form —
  the bare `postgresql://` that Supabase's connection strings carry, `postgres://`,
  legacy `+asyncpg` or `+psycopg2` — is rewritten to the canonical
  `postgresql+psycopg://`, so the async engine and Alembic (sync) always see one
  psycopg v3 URL. Non-Postgres URLs pass
  through untouched.
- **`SCHEDULER_TIMEZONE`** (any env): must resolve via `ZoneInfo`, with a clear error
  instead of an opaque failure at scheduler import.
- **Production safety** (`APP_ENV=production` only) — the app **refuses to boot** on:
  placeholder `APP_SECRET_KEY`; `APP_DEBUG=true`; wildcard `ALLOWED_HOSTS`; a
  localhost `DATABASE_URL`; wildcard-or-loopback `CORS_ORIGINS` (`"*"` is also
  invalid with `allow_credentials=True`); an empty or localhost `INVITE_LINK_ORIGIN`;
  missing `SUPABASE_URL`, `SUPABASE_ANON_KEY`, or `SUPABASE_SERVICE_ROLE_KEY`; and,
  with `SCHEDULER_ENABLED=false`, a `CRON_SECRET` that is empty or below the
  `metrics_token_weakness` floor (ADR-065), because the cron routes are then the only
  trigger of the scheduled jobs.

## Where production sets them

No file in the repository declares production's values. Every one is set by hand in the Vercel
`familyroots-api` project's environment variables, and the list with each value is
[deployment.md](deployment.md), "Go-live checklist" C. [secrets.md](secrets.md), "Known gaps",
records that nothing compares the project's variables with that list.

**Firebase FCM** is **optional for boot** — no credentials only disables push notifications
(warning, not a boot failure). A function has no file to mount, so on Vercel the service-account
JSON goes inline in `FIREBASE_CREDENTIALS_JSON`.

`tests/unit/test_config_validation.py` pins the boot refusals for a wildcard or loopback
`CORS_ORIGINS`, an unset `RATE_LIMIT_TRUST_FORWARDED_FOR`, and (since #191) an empty or loopback
`INVITE_LINK_ORIGIN`. The validator in `app/core/config.py` also refuses each of the
three Supabase vars when empty, and no test pins those three.

Notes:

- List-typed vars (`ALLOWED_HOSTS`, `CORS_ORIGINS`) must be **JSON arrays** in env
  (pydantic-settings parses complex types as JSON), e.g. `'["https://app.example.com"]'`.
- `docker-compose.yml` also passes `SUPABASE_JWT_SECRET`, which is **not** a Settings
  field (silently ignored; JWT validation uses JWKS, not a shared secret).

## Related

- [secrets.md](secrets.md) — where each secret lives and how to rotate it
- [deployment.md](deployment.md) — Vercel projects, the release workflow, migrations before deploy
- [../architecture/notifications-scheduler.md](../architecture/notifications-scheduler.md) — scheduler knobs in context
- [../architecture/storage.md](../architecture/storage.md) — `DOCUMENT_RETENTION_DAYS` in the delete/purge lifecycle
