# Notifications & Scheduler

How anniversary push notifications work: an in-process APScheduler cron finds
upcoming recurring events (both solar and lunar) and broadcasts FCM pushes to
approved clan members. The same scheduler process also runs the document
retention purge job (ADR-019).

## Scheduler topology

`backend/app/services/scheduler.py` runs an **in-process `AsyncIOScheduler`** started in
the FastAPI lifespan (`app/main.py`) — no separate worker, no Redis, no durable queue.

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

## Multi-replica safety — Postgres advisory lock

Every replica runs the scheduler, so each job elects a single runner via its
own advisory lock (see the table above for lock keys):

- `pg_try_advisory_lock` on a **dedicated connection held for the whole job**. If not
  acquired → log and skip the run.
- The working `AsyncSession` is **bound to that same connection**, so mid-job commits
  can't return the connection to the pool and strand the session-level lock.
- The `finally` block **rolls back before unlocking**: the advisory lock survives
  rollback, and unlocking on an aborted transaction would raise
  `InFailedSqlTransaction` and mask the job's real error.

This topology is shared verbatim by `document_purge`
(`app/services/document_purge.py`) — see
[ADR-019](../decisions/019-document-soft-delete-purge.md) for that job's
per-item claim-row → delete-blob → commit ordering, which is a second,
independent safety property layered on top of this same lock/connection
pattern.

## The anniversary flow — two sources, merged in Python

The job pulls events from **two sources** and feeds both through the same
per-event loop (see [ADR-018](../decisions/018-vietnamese-lunar-calendar.md)):

1. **Solar SQL query**: recurring solar events (`is_recurring = true AND
   is_lunar_calendar = false`, linked person not soft-deleted). Each row already
   carries a precomputed `next_occurrence` (this year or next), calculated in SQL
   via `next_anniversary_sql` — cheap date arithmetic that cannot raise.
2. **Lunar raw-row query**: recurring lunar events (`is_recurring = true AND
   is_lunar_calendar = true`, same person join). This query selects only
   `event_date` — no `next_occurrence` in SQL, because a lunar anniversary cannot
   be expressed as solar date arithmetic.
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

## Ops knobs (see [ops/configuration.md](../ops/configuration.md))

| Setting | Default | Notes |
|---|---|---|
| `NOTIFICATION_CRON_HOUR` | `7` | Hour-of-day in the platform zone (both `anniversary_notifications` and `document_purge` key off it) |
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
