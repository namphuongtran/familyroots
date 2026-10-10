# Notifications & Scheduler

How anniversary push notifications work: a daily job finds upcoming recurring
events (both solar and lunar) and broadcasts FCM pushes to approved clan members.
A second daily job runs the document retention purge (ADR-019). Each job is
triggered by one of two paths (see below).

## Two trigger paths, one live per deployment (ADR-065)

The jobs are two plain async functions, `send_anniversary_notifications`
(`backend/app/services/scheduler.py`) and `purge_expired_documents`
(`backend/app/services/document_purge.py`). `SCHEDULER_ENABLED` picks what calls them:

| `SCHEDULER_ENABLED` | Where | What calls the jobs |
|---|---|---|
| `true` (default) | a long-running process: local, Docker | the in-process APScheduler, started and stopped by the FastAPI lifespan (`app/main.py`), at the cron triggers in the table below |
| `false` | Vercel Functions, where an instance is frozen between requests and an in-process timer never fires | **Vercel Cron**, by `GET /internal/cron/anniversary-notifications` and `GET /internal/cron/document-purge` (`backend/app/api/cron.py`) |

The cron routes run a job only for `Authorization: Bearer <CRON_SECRET>`, compared in
constant time. Every refusal is the same 404 a path that does not exist gets, the
`/internal/metrics` rule of ADR-021 and ADR-040. Success is 204 with no body, and a
job that fails answers 500. Production refuses to boot with `SCHEDULER_ENABLED=false`
unless `CRON_SECRET` clears the `metrics_token_weakness` floor
([ops/configuration.md](../ops/configuration.md)).

**What changes under Vercel Cron**, all read from Vercel's docs on 2026-10-10:

- **The schedule is UTC and lives in the deploy configuration** (#252), not in
  `NOTIFICATION_CRON_HOUR`, which only APScheduler reads. The jobs still compute
  "today" in `SCHEDULER_TIMEZONE`, so the clock of the date math is unchanged.
- **On Hobby a run fires anywhere within the scheduled hour.**
- **A run may be delivered twice.** A concurrent duplicate skips on the advisory lock
  (below). A later one is a no-op: the anniversary job dedups on
  `notification_log.sent_on`, and the purge finds nothing left to purge.
- **A failed run is not retried.** The anniversary job sends only on the day an event is
  exactly `notify_days_before` away, so a missed or failed day is not caught up the next
  day. That was already true under APScheduler: a run missed by more than its
  `misfire_grace_time` of 3600 s, for example because no process was up at the hour,
  was skipped as well.

Neither path is a durable queue: no separate worker, no Redis.

## Scheduler topology

When `SCHEDULER_ENABLED` is true, `backend/app/services/scheduler.py` runs an
**in-process `AsyncIOScheduler`** started in the FastAPI lifespan (`app/main.py`).

| Job | Trigger | Lock key | Purpose |
|---|---|---|---|
| `anniversary_notifications` | `CronTrigger(hour=NOTIFICATION_CRON_HOUR, minute=0, timezone=SCHEDULER_TIMEZONE)`, `misfire_grace_time=3600` | `728_115_001` | Solar + lunar giỗ/anniversary FCM pushes (see below) |
| `document_purge` | `CronTrigger(hour=NOTIFICATION_CRON_HOUR, minute=30, timezone=SCHEDULER_TIMEZONE)`, `misfire_grace_time=3600` | `728_115_002` | Permanently remove soft-deleted documents past `DOCUMENT_RETENTION_DAYS` (ADR-019) |

Both jobs share `NOTIFICATION_CRON_HOUR` and `SCHEDULER_TIMEZONE` — the purge
job is offset 30 minutes after the anniversary job (same hour, `minute=30`) so
the two never race each other on the same replica, and each has its own
advisory lock key so the two jobs also never contend with each other, only
with concurrent runs of themselves.

- **Single clock**: `SCHEDULER_TIMEZONE` (default `Asia/Ho_Chi_Minh`) governs both when
  the cron fires *and* the job's date math — `today` is computed once in that zone and
  threaded into the SQL as `:today` (no `CURRENT_DATE`), so container/DB timezone drift
  cannot split the occurrence math from the "N days away" gate. This is one **global**
  platform zone; per-clan timezones are out of scope.

## Multi-replica safety — a transaction-scoped advisory lock

Every replica running the scheduler races for each job. So does every Vercel Cron
delivery, which may arrive twice. Each job therefore elects a single runner through
its own advisory lock (see the table above for the keys). Since
[ADR-065](../decisions/065-the-backend-runs-on-vercel-functions.md) (2026-10-10) that
lock is **transaction-scoped**:

- `pg_try_advisory_xact_lock` runs in **one transaction on a dedicated lock
  connection**, and that transaction stays open, doing nothing else, for the whole
  job. If the lock is not acquired, the job logs it and skips the run.
- The work runs on a **separate system session**, a plain `AsyncSession(bind=engine)`.
  Its per-item commits and rollbacks therefore happen on another connection, and can
  neither release the lock early nor strand it.
- **The lock ends when the lock transaction ends.** On success or on error, the
  `finally` block closes the work session first and then rolls the lock transaction
  back. If the process dies, its connection drops, the server ends the transaction,
  and the lock goes with it. The lock connection runs nothing after the lock, so its
  rollback cannot meet `InFailedSqlTransaction` and mask the job's own error.
- While a job runs it holds **two** connections: the lock connection and its work
  session's.
- **Why not the session-level lock this replaced** (the C2 topology,
  seam-review-2026-07-04). `pg_try_advisory_lock` was taken in one transaction,
  committed, and unlocked in a later transaction. Behind a transaction pooler
  (Supavisor on `:6543`, which is how the backend reaches Postgres from Vercel
  Functions) only a transaction stays on one server connection. The unlock could
  run on a different server connection and miss. The lock then stayed on a server
  connection that outlives the client, and every later run skipped without raising.
  Clans would simply have stopped getting giỗ reminders.
- **One precondition.** The lock transaction sits idle in transaction for the job's
  whole run. A server-side `idle_in_transaction_session_timeout` shorter than the job
  would end it early, freeing the lock mid-run, and the final rollback would then
  raise on the dead connection. Keep any such timeout longer than a job takes. Vercel
  ends a function at 300 s on Hobby.

`backend/tests/integration/test_job_lock_survives_a_pooler.py` reads both outcomes
against real Postgres, for both jobs. First, a concurrent second run skips. Second, a
later run on a **second engine** takes the lock and does the work, while the first
engine's connections, like a pooler's server connections, live on. Restoring the
session-level lock with its unlock on another connection fails the second test.

This topology is shared verbatim by `document_purge`
(`app/services/document_purge.py`) — see
[ADR-019](../decisions/019-document-soft-delete-purge.md) for that job's
per-item claim-row → delete-blob → commit ordering, which is a second,
independent safety property layered on top of this same lock/connection
pattern.

## The anniversary flow — two sources, merged in Python

The job pulls events from **two sources** and feeds both through the same
per-event loop (see [ADR-018](../decisions/018-vietnamese-lunar-calendar.md)).
**Both source queries require `event_date_precision = 'exact'`** (ADR-011; M4,
review 2026-07-18): a recurring event recorded with an estimated date is
recorded and still visible elsewhere (list/detail/timeline, and
`GET /events/upcoming` filters it out too — see
[rest-events-api.md](../contracts/rest-events-api.md)), but never reaches this
job — a placeholder date cannot anchor a real yearly anniversary. One-off
(`is_recurring = false`) events have no notification path at all, independent
of precision.

1. **Solar SQL query**: recurring solar events (`is_recurring = true AND
   is_lunar_calendar = false AND event_date_precision = 'exact'`, linked person
   not soft-deleted). Each row already carries a precomputed `next_occurrence`
   (this year or next), calculated in SQL via `next_anniversary_sql` — cheap
   date arithmetic that cannot raise.
2. **Lunar raw-row query**: recurring lunar events (`is_recurring = true AND
   is_lunar_calendar = true AND event_date_precision = 'exact'`, same person
   join). This query selects only `event_date` — no `next_occurrence` in SQL,
   because a lunar anniversary cannot be expressed as solar date arithmetic.
3. The two row sets are concatenated (`[*events, *lunar_events]`) into one loop.
   For each event:
   - If the row already has `next_occurrence` (a solar row), use it directly.
   - Otherwise (a lunar row) compute it **lazily, inside this per-event
     `try`**, by calling `next_lunar_anniversary(event_date, today)`
     (`app/services/lunar_calendar.py`, Hồ Ngọc Đức's algorithm at UTC+7). This
     call is deliberately made inside the per-event error boundary rather than
     up front: the lunar conversion is the one piece of math in this flow that
     can raise on a pathological date, so a bad lunar row hits the
     rollback-and-continue path below instead of aborting the whole run before
     any event (solar or lunar) is processed.
4. Gate: send only when `next_occurrence - today == notify_days_before`.
5. **Dedup**: skip if a `notification_log` row for (`event_id`, `notification_type`)
   was already created "today" in the platform zone. Dedup keys on the row's creation
   day, so replaying the job with a *past* `today` is NOT dedup-protected — the
   injectable `today` parameter is for deterministic tests only.
6. Broadcast via `send_to_clan`, log the outcome, `commit()` **per event**; a failing
   event (solar or lunar) is rolled back and skipped so one bad row can't abort the
   run.

## FCM delivery (`backend/app/services/notification.py`)

- `send_to_clan(clan_id, title_key, body_key, …)` fans out to every **approved** member
  (`user_clan_roles.is_approved`) with a registered token in `user_fcm_tokens`, sending
  **per-recipient language** from `user_profiles.language` (default `vi`) via
  `t(key, locale=…)`. Returns `(sent, failed)`.
- `send_push_notification` never raises — a notification failure must not break the
  calling flow.
- **Invalid-token pruning**: `messaging.UnregisteredError` stages a `DELETE` of that
  `user_fcm_tokens` row; the scheduler's per-event commit persists it.
- Firebase Admin is initialized once at startup from `FIREBASE_CREDENTIALS_PATH`;
  missing/invalid credentials log a warning and pushes silently fail (dev-friendly).

## `notification_log` lifecycle

`backend/app/models/notification_log.py` — one row per event per run-day:

- `status`: `sent` (≥1 delivery) or `failed` (0 deliveries; `error_message` records
  `0/N delivered`). `sent_at = NOW()`.
- `user_id` is the zero-UUID sentinel for clan-wide broadcasts (no per-recipient rows).
- `clan_id` FK is `RESTRICT`, `event_id` FK is `SET NULL` — the log outlives events.
- The same table is the dedup source (see above), so **never backdate rows manually**.

### The table carries an RLS policy, and this job is not subject to it

Since 2026-08-22 (migration `034_rls_audit_notification`,
[ADR-043](../decisions/043-audit-notification-rls-posture.md) § 2) `notification_log` has RLS
enabled with the ordinary clan-isolation policy,
`USING (clan_id = <app.clan_id GUC>) WITH CHECK (same)`.

**That does not narrow this job, and the reason is worth holding onto.** The policy applies
only to sessions that ran `SET LOCAL ROLE familyroots_app`, which is the `after_begin` seam on
`RlsSession` (`backend/app/core/rls.py:63-65`). This job builds its work session as a plain
`AsyncSession(bind=engine)` (`backend/app/services/scheduler.py:116`; until ADR-065 it was
bound to a bare `engine.connect()`), which is not an `RlsSession`. So no seam fires, the
connection keeps the `DATABASE_URL` login role, and RLS does not apply. One run still scans every clan's events and writes a row per due event
whatever clan it belongs to.

**The failure this would cause is silent, so it is tested rather than argued.** If the seam
ever reached this job, the dedup `SELECT` would return nothing and the `INSERT` would be
rejected — and nothing would raise where anyone looks. Clans would simply stop receiving giỗ
reminders. `backend/tests/integration/test_scheduler_cross_clan_notification_log.py` runs the
job once against two clans, asserts a row and a `send_to_clan` call for each, and then reads
the same two rows back **under the request role** to prove the policy was live the whole time.
Without that last step the test would pass equally well against a database where migration
`034` never ran.

**If you ever move this job onto a request session, the policy is the first thing that breaks.**
It is also why the job must stay one of the sanctioned out-of-band writers described in
`backend/CLAUDE.md`.

## Ops knobs (see [ops/configuration.md](../ops/configuration.md))

| Setting | Default | Notes |
|---|---|---|
| `SCHEDULER_ENABLED` | `true` | `true`: the lifespan runs APScheduler. `false`: it does not, and Vercel Cron calls `/internal/cron/*` (ADR-065) |
| `CRON_SECRET` | `""` | Bearer secret for `/internal/cron/*`. Empty or below the `METRICS_TOKEN` floor: both routes 404. Production with `SCHEDULER_ENABLED=false` refuses to boot without a strong one |
| `NOTIFICATION_CRON_HOUR` | `7` | Hour-of-day in the platform zone (both `anniversary_notifications` and `document_purge` key off it). APScheduler only. Vercel Cron's schedule lives in the deploy configuration |
| `SCHEDULER_TIMEZONE` | `Asia/Ho_Chi_Minh` | Validated as IANA name at boot (fail-fast) |
| `FIREBASE_CREDENTIALS_PATH` | `./firebase-credentials.json` | Absent → pushes disabled, app still boots |
| `DOCUMENT_RETENTION_DAYS` | `30` | `document_purge` job's retention window (ADR-019) |

## Related

- [ADR-018](../decisions/018-vietnamese-lunar-calendar.md) — Vietnamese lunar
  calendar engine, giỗ conventions, why the conversion is in-house and computed
  lazily in Python
- [Backend i18n](i18n.md) — per-recipient locale resolution for push text
- [Overview](overview.md) — in-process (non-durable) eventing caveats
- [ops/monitoring.md](../ops/monitoring.md) — where failure logs surface
