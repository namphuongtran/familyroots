# ADR-065: The Backend Runs on Vercel Functions

## Status

Accepted, shipped (2026-10-10). Resolves issue #250, "The backend runs on Vercel Functions:
external pooler, cron endpoints, and a lock that survives a pooler".

The maintainer took the hosting decision on 2026-10-10. The backend runs on **Vercel
Functions**: project `familyroots-api`, team `namtp`, Hobby plan, region `sin1`. The application
database is in the Supabase project `xkmutzxdhdigyfisfrwd` (`ap-southeast-1`, Postgres 17),
reached through Supavisor's **transaction pooler on `:6543`**. Render is retired. This ADR
records what making the backend run there decided.

**This ADR ships with its code**, in the same pull request. Source readings were taken at
`c39ad2e` on `main` on 2026-10-10, before the change. Vercel's documentation was read the same
day. Two sibling issues own the rest of the move, and this ADR assumes their outcomes without
recording them. **#251** is the Supabase side: role membership for `familyroots_app`, closing
the Data API, and Postgres 17 compatibility. **#252** is the deploy: `vercel.json`, the cron
schedule, the environment values, CI, and retiring `render.yaml`.

**Amended 2026-10-10 (#265): Vercel Cron calls the deployment's own host, so the host check
admits it.** The first manual cron run (`vercel crons run /internal/cron/document-purge`) reached
`familyroots-9xtnrccz1-namtp.vercel.app`, the production deployment's generated URL, and the
function log read `400`. `TrustedHostMiddleware` refused it, because `ALLOWED_HOSTS` names the
alias `familyroots-api.vercel.app`, so neither job would ever have run.

`Settings.trusted_hosts` now adds Vercel's system variable `VERCEL_URL`, this deployment's own
hostname, to an explicit `ALLOWED_HOSTS`, and `create_app` passes that list to the middleware.
- **No other deployment is admitted.** Vercel routes by `Host`, so the name reaches only this
  deployment.
- **The deployment URL stays protected.** Vercel's deployment protection guards it for browsers.
- **No path is exempted from the host check**, which keeps #230's rule.

## Context

### What Vercel provides, read 2026-10-10

- **FastAPI runs zero-config** from `app/main.py:app`, on Python 3.12 to 3.14, in a bundle of up
  to 500 MB, with `uv.lock` support. The **ASGI lifespan runs**, once per cold instance, and
  "Cleanup logic during shutdown is limited to a maximum of **500ms**"
  (vercel.com/docs/frameworks/backend/fastapi).
- **An instance is frozen between requests.** Nothing in the process runs unless a request is in
  flight.
- **Request and response bodies are capped**: "The maximum payload size for the request body or
  the response body of a Vercel Function is **4.5 MB**". Above it, Vercel answers
  `413 FUNCTION_PAYLOAD_TOO_LARGE` itself, and the request never reaches the app
  (vercel.com/docs/functions/limitations). Hobby's maximum duration is **300 s**.
- **Vercel Cron** "makes an HTTP GET request" to a path on a schedule, and "The timezone is always
  UTC". When the project has a `CRON_SECRET`, "The value of the variable will be automatically
  sent as an `Authorization` header", with "the `Bearer` prefix". On Hobby, "Vercel may invoke
  these cron jobs at any point within the specified hour". "Cron delivery can also occasionally
  invoke the same scheduled run more than once", and "Vercel will not retry an invocation if a
  cron job fails" (vercel.com/docs/cron-jobs, …/manage-cron-jobs).

### Five places the backend assumed a long-running process

| Assumption | Where, at `c39ad2e` | What happens on Vercel |
|---|---|---|
| **The scheduler.** APScheduler starts in the lifespan | `app/main.py:91`, `_safe("scheduler", start_scheduler)` | The timer lives in a frozen process and never fires |
| **The pool.** A QueuePool of 10 + 20, with psycopg's default server-side prepares | `app/core/database.py:35-42`, and the NOTE at `:24-28`, which says a transaction pooler breaks those prepares with `DuplicatePreparedStatement` | Prepared statements break. Parked connections in a frozen instance hold the pooler's client slots |
| **The job locks.** A session-level `pg_try_advisory_lock`, committed, then `pg_advisory_unlock` in a later transaction | `app/services/scheduler.py:91, 100, 232`; `app/services/document_purge.py:72-74, 139` | The unlock can run on another server connection and miss. The lock leaks, every later run skips, and nothing raises |
| **Firebase.** Credentials come only from a file path | `app/services/notification.py:30`, `credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)` | A Function has no file mount to name |
| **The body limit.** Documents allow 50 MB | `app/core/config.py:144` (`MAX_UPLOAD_SIZE_MB`); `web/src/lib/api/documents.ts:10` | A body over 4.5 MB meets Vercel's 413, which carries no error envelope |

The third one is the dangerous one, because it fails silently. It is the giỗ reminder stopping,
with no error anywhere a person would look.

## Decision

Each change is behind a setting whose default is today's behaviour, so **local and Docker
deployments are unchanged** unless they opt in.

### 1. Render is replaced by Vercel Functions

This was taken by the maintainer, not by this ADR. Everything below is what it requires of the
backend.

### 2. `DB_EXTERNAL_POOLER=true` builds a `NullPool` engine with no server-side prepares

`Settings.DB_EXTERNAL_POOLER`, default `false`, picks between two shapes in `make_engine`
(`app/core/database.py`):

- **`true`**: `poolclass=NullPool` and `connect_args={"prepare_threshold": None}`.
  - **NullPool, because the pooler is the pool.** A frozen instance that parked connections in
    a pool of its own would hold them open against Supavisor's client limit, possibly for good,
    since a frozen instance may never thaw. `DB_POOL_SIZE` and `DB_MAX_OVERFLOW` are ignored.
  - **`prepare_threshold=None`, because transaction mode moves the server connection between
    transactions.** psycopg 3 prepares a query on the server after five runs on one
    connection. A statement prepared on one server connection is then missing on the next, or
    already exists there (`DuplicatePreparedStatement`).
- **`false`**: the QueuePool exactly as ADR-028 built it.

Nothing else had to change for a transaction pooler. Every setting the app makes per
connection is already transaction-local: `SET LOCAL ROLE` at `app/core/rls.py:63`, and
`set_config(..., true)` at `:65` and `app/core/security.py:291`. Nothing in `app/` uses
`LISTEN` or a session-level setting.

### 3. Two trigger paths for the scheduled jobs, one live per deployment

`Settings.SCHEDULER_ENABLED`, default `true`, decides which trigger path calls
`send_anniversary_notifications` and `purge_expired_documents`:

- **`true`**: the lifespan starts and stops APScheduler, as before.
- **`false`**: the lifespan leaves APScheduler alone, and **Vercel Cron** calls two routes in
  `app/api/cron.py`, mounted by `create_app` outside `/api/v1`:
  - `GET /internal/cron/anniversary-notifications` runs `send_anniversary_notifications()`.
  - `GET /internal/cron/document-purge` runs `purge_expired_documents()`.

The routes are guarded like `/internal/metrics` (ADR-021, ADR-040):

- **Each runs only for `Authorization: Bearer <CRON_SECRET>`**, compared as the exact bytes in
  constant time, with `secrets.compare_digest`.
- **Every refusal is the same bare 404** that a path which does not exist gets, byte for byte.
  That covers a missing header, a wrong secret, and a `CRON_SECRET` that is empty or below
  `metrics_token_weakness`'s floor of 32 characters and 8 distinct. The floor is re-checked on
  every request, as `/internal/metrics` re-checks its token, so a weak secret serves nothing in
  any environment and a bypassed validation fails closed.
- **Success is 204 with no body.** That keeps the routes inside the frozen envelope rather than
  exempt from it. A job-fatal error answers the standard 500 envelope, because Vercel reads only
  the status and retries nothing, so a run that failed must not report success.
- **They are hidden from OpenAPI and excluded from the Prometheus instrumentator**, beside
  `/internal/metrics`.
- **They are registered where `lint-imports` permits**: `app.api` may import `app.services`.

`Settings.CRON_SECRET`, default `""`. **Production refuses to boot with
`SCHEDULER_ENABLED=false` unless `CRON_SECRET` clears `metrics_token_weakness`**, in
`_enforce_production_safety`. The routes are then the jobs' only trigger. An empty secret would
mean the reminders never run and nothing says so, and a weak one would guard them with a
guessable value. Vercel recommends "at least 16 characters", and this floor is 32.

**What Vercel Cron changes, accepted:**

- **The schedule is UTC and lives in the deploy configuration** (#252), not in
  `NOTIFICATION_CRON_HOUR`, which only APScheduler reads. The jobs still compute "today" in
  `SCHEDULER_TIMEZONE`, so the date math is unchanged. 07:00 in `Asia/Ho_Chi_Minh` is 00:00 UTC.
- **On Hobby a run fires anywhere within the scheduled hour.**
- **A run may be delivered twice.** A concurrent duplicate skips on the lock (§ 4). A later
  duplicate is a no-op: the anniversary job dedups on `notification_log`'s unique
  `(event_id, notification_type, sent_on)`, and the purge finds no eligible row left.
- **A failed run is not retried, and a missed day is not caught up.** The anniversary job sends
  only on the day an event is exactly `notify_days_before` away. This was already true under
  APScheduler, for a run missed by more than `misfire_grace_time`.

### 4. Both jobs take a transaction-scoped advisory lock on a dedicated lock connection

Each job opens a **lock connection** and runs `pg_try_advisory_xact_lock(key)` there, in one
transaction that stays open, doing nothing else, for the whole job. The work runs on a
**separate system session**, `AsyncSession(bind=engine)`, so its per-item commits happen on
another connection and can neither release the lock early nor strand it. The `finally` block
closes the work session, then rolls the lock transaction back. **The lock ends when the lock
transaction ends**: on success, on error, or when the process dies, its connection drops, and
the server or the pooler ends the transaction. A concurrent second run cannot take the lock, and
skips.

This works behind a transaction pooler because a pooler keeps a transaction on one server
connection, and nothing longer. The session-level lock it replaces was taken in one transaction
and released in a later one, and that is exactly what a pooler does not keep together.

- **The work cannot itself be the lock's transaction.** Per-item commits are each job's
  isolation property. The anniversary job commits per event, and the purge commits per document
  under ADR-019's claim → blob → commit. One transaction for the whole job would make one bad
  item undo the run.
- **The work session is built in the job**, not taken from `AsyncSessionLocal`, so
  `tests/integration/test_scheduler_cross_clan_notification_log.py`, which replaces
  `AsyncSessionLocal`, still exercises the job's own seam-free session class (ADR-043 § 2).
- **The lock is still needed although both jobs dedup.** The anniversary job sends the push
  before it inserts the dedup row. Without the lock, two concurrent runs would both send to
  every device, and only the second insert would then fail on the unique index.
- **A running job now holds two connections**, the lock connection and its work session. Under
  QueuePool both come out of the instance's one pool (`docs/ops/configuration.md`).
- **One precondition.** The lock transaction sits idle in transaction for the job's whole run.
  A server-side `idle_in_transaction_session_timeout` shorter than the job would end it early,
  freeing the lock mid-run, and the final rollback would then raise on a dead connection. Keep
  any such timeout longer than a job takes. Vercel stops a function at 300 s on Hobby anyway.

### 5. Firebase credentials may arrive inline

`Settings.FIREBASE_CREDENTIALS_JSON`, default `""`, holds the service-account key file's whole
content. When it is set, `init_firebase` builds the credentials from it. Otherwise it uses
`FIREBASE_CREDENTIALS_PATH`, as before. The value is a secret, so anything that is not a JSON
object is refused **without quoting it**. `firebase_admin`'s `Certificate` reads a string as a
path, which shows up in a `FileNotFoundError`, and echoes any other non-dict in its
`ValueError`. `init_firebase` logs both, so the secret itself would land in the logs.

### 6. Uploads are capped at 4 MB, and direct-to-Storage uploads are deferred

The maintainer chose 4 MB for now. Production sets `MAX_UPLOAD_SIZE_MB=4` (#252), and the
server's limit stays env-driven. Because Vercel's 413 never reaches the API's envelope, the
client must refuse a larger file before sending it. `web/src/lib/api/documents.ts` refuses a
file over 4 MB with "File size exceeds the 4 MB limit". The multipart body around a 4 MiB file
fits under Vercel's 4.5 MB.

**Deferred:** direct-to-Storage signed uploads, which would lift the cap by sending the file
past the Function. **Not handled:** a response over 4.5 MB, which in practice means
`GET /exports/clan` for a large clan.

### 7. The rate limiter and the metrics throttle are per instance, and that is accepted

`RateLimitMiddleware` (ADR-021 § 3) and `MetricsFailureThrottle` (ADR-040) keep their counters in
process memory. ADR-040 already accepted "5×N failures per window" for N replicas. On Vercel, N
is however many instances Vercel runs at once, and a cold instance starts with an empty bucket.
So the auth budget of 20 per minute per IP holds per instance, not overall. Accepted for now.
Replacing the in-memory limiter with a shared store is a follow-up, not part of #250. The cron
routes have no failure throttle at all. Their guard is the secret's floor, and a failure costs
an attacker a request that returns the same 404 as a missing path.

## Consequences

- **Local and Docker behave as before.** Every new setting defaults to today's behaviour:
  `DB_EXTERNAL_POOLER=false`, `SCHEDULER_ENABLED=true`, `CRON_SECRET=""` (both routes 404), and
  `FIREBASE_CREDENTIALS_JSON=""`. The lock change applies everywhere. On a direct connection it
  behaves as the old lock did, at the cost of a second connection while a job runs.
- **Vercel needs four values set** (#252): `DB_EXTERNAL_POOLER=true`, `SCHEDULER_ENABLED=false`,
  a strong `CRON_SECRET` (the same project variable Vercel Cron sends), and `MAX_UPLOAD_SIZE_MB=4`.
  `FIREBASE_CREDENTIALS_JSON` is needed only if pushes are wanted. **Nothing validates
  `DB_EXTERNAL_POOLER` against the URL**, so a pooler URL with `false` boots and then fails per
  request with `DuplicatePreparedStatement`.
- **Every cold instance pays the lifespan.** That is the translations, Firebase, the migration
  readiness check, and the RLS readiness check, each on a fresh `NullPool` connection.
- **A non-GET request to a cron route answers 405, not 404**, as `/internal/metrics` already
  does. That tells a scanner the path exists. It is a pre-existing shape of both routes, left as
  it is.
- **Stale descriptions this change could not edit**, because they sit outside its file fence:
  - `docs/architecture/data-model.md:949-950`, and ADR-043's table at `:52`, still say the
    anniversary job binds its session to a bare `engine.connect()`.
  - `backend/.env.example` and `docs/ops/secrets.md` do not name the four new settings.
  - `web/src/components/documents/DocumentUpload.tsx:11` still refuses only at 20 MB. A 4-20 MB
    file passes it and is then refused by `documents.ts` with an unlocalized `Error` that
    `handleSubmit` does not catch.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Keep the session-level lock, behind Supavisor's **session** pooler on `:5432` | Session mode pins a server connection per client for the client's life, so the old lock would work. But every warm instance would hold a server connection, and session mode's pool size caps concurrency at that. Transaction mode is the one meant for serverless clients. And the lock would still leak the day someone pointed it at `:6543` |
| No lock, relying on the jobs' dedup | The anniversary job pushes before it inserts its dedup row, so two concurrent runs both push to every device. The unique index only fails the second insert |
| One transaction for the whole job, holding the lock | It breaks each job's per-item isolation (ADR-019's claim → blob → commit; the per-event commit) |
| A small QueuePool (`pool_size=1`) instead of NullPool | A frozen instance still parks its connection against the pooler's client limit. It also leaves psycopg's prepares to break unless `prepare_threshold=None` is set anyway |
| 401 or 403 for a cron request without the secret | It confirms the route exists. ADR-021 and ADR-040 already answer this with the bare 404 |
| Allow a weak `CRON_SECRET` outside production | The handler refuses it in every environment, as `/internal/metrics` does. Settings validation is production-only and scoped to `SCHEDULER_ENABLED=false`, because only there is an empty secret an outage |
| `POST` for the cron routes | Vercel Cron sends `GET` |
| Direct-to-Storage uploads now, instead of the 4 MB cap | A larger change across backend, web and Storage policy. Deferred by the maintainer |

## Verification

The backend full quality gate, and the full web gate, because `documents.ts` changed. The
readings and negative controls are in each commit's message on the branch for #250. The tests
are:

- **Pool**: `tests/unit/test_engine_pooler_selection.py` reads the pool class and the kwargs that
  reach `psycopg.AsyncConnection.connect`. `tests/integration/test_external_pooler_engine.py`
  reads the outcomes on real Postgres: `pg_prepared_statements` after ten runs of one query, and
  whether a closed connection's backend lingers. The direct engine is the control.
- **Lock**: `tests/integration/test_job_lock_survives_a_pooler.py`, parametrized over both
  jobs. A concurrent second run skips. A later run on a second engine takes the lock and does
  the work, while the first engine's connections live on, the way a pooler's server connections
  do. Restoring the session-level lock, with the unlock on another connection, fails the second
  test.
- **Cron**: `tests/unit/test_cron_endpoints.py` drives both routes over HTTP and reads the
  status and whether the job ran. `tests/integration/test_cron_endpoints_run_the_jobs.py` runs
  the real jobs through them. Making the check accept any header fails 33 of the 38 unit cases.
- **Scheduler switch**: `tests/unit/test_lifespan_scheduler_switch.py` runs the real lifespan.
- **Validator**: `tests/unit/test_config_validation.py`, the CRON_SECRET block.
- **Firebase**: `tests/unit/test_firebase_credentials_source.py`.
- **Upload cap**: `web/src/lib/api/documents.test.ts`.
- `tests/integration/test_scheduler_cross_clan_notification_log.py` stays green, with only its
  docstring changed for the new topology.

## Related

- [ADR-019](019-document-soft-delete-purge.md): the purge job's per-item ordering, which the lock
  sits beside
- [ADR-021](021-non-enumerating-auth-surfaces.md): the 404 rule, and the rate limiter's scope.
  Amended 2026-10-10 by this ADR
- [ADR-028](028-no-external-io-holding-db-connection.md): the pool this makes optional. Amended
  2026-10-10 by this ADR
- [ADR-040](040-metrics-token-floor-and-throttle.md): the secret floor the cron routes reuse
- [ADR-043](043-audit-notification-rls-posture.md): why the jobs' sessions must stay seam-free
- [architecture/notifications-scheduler.md](../architecture/notifications-scheduler.md),
  [ops/configuration.md](../ops/configuration.md), [contracts/README.md](../contracts/README.md)
