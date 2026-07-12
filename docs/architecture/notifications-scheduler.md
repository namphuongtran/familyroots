# Notifications & Scheduler

How anniversary push notifications work: an in-process APScheduler cron finds
upcoming recurring events and broadcasts FCM pushes to approved clan members.

> ⚠️ **Lunar events do not fire.** The job hard-filters `is_lunar_calendar = false`,
> so **giỗ âm lịch (lunar-calendar) reminders are currently never sent** — arguably
> the platform's most important notification. There is **no lunar↔solar conversion
> anywhere in the codebase**; support is explicitly deferred ("data-model round 2").
> Each run counts and logs the skipped lunar events so the gap stays visible.

## Scheduler topology

`backend/app/services/scheduler.py` runs an **in-process `AsyncIOScheduler`** started in
the FastAPI lifespan (`app/main.py`) — no separate worker, no Redis, no durable queue.

- Job `anniversary_notifications`: `CronTrigger(hour=NOTIFICATION_CRON_HOUR, minute=0)`
  with an explicit timezone, `misfire_grace_time=3600`.
- **Single clock**: `SCHEDULER_TIMEZONE` (default `Asia/Ho_Chi_Minh`) governs both when
  the cron fires *and* the job's date math — `today` is computed once in that zone and
  threaded into the SQL as `:today` (no `CURRENT_DATE`), so container/DB timezone drift
  cannot split the occurrence math from the "N days away" gate. This is one **global**
  platform zone; per-clan timezones are out of scope.

## Multi-replica safety — Postgres advisory lock

Every replica runs the scheduler, so the job itself elects a single runner:

- Fixed lock key `_JOB_LOCK_KEY = 728_115_001`; `pg_try_advisory_lock` on a **dedicated
  connection held for the whole job**. If not acquired → log and skip the run.
- The working `AsyncSession` is **bound to that same connection**, so mid-job commits
  can't return the connection to the pool and strand the session-level lock.
- The `finally` block **rolls back before unlocking**: the advisory lock survives
  rollback, and unlocking on an aborted transaction would raise
  `InFailedSqlTransaction` and mask the job's real error.

## The anniversary flow

1. Select recurring **solar** events (`is_recurring = true AND is_lunar_calendar =
   false`, linked person not soft-deleted), computing each event's next occurrence
   (this year or next) via `next_anniversary_sql`.
2. Gate: send only when `next_occurrence - today == notify_days_before`.
3. **Dedup**: skip if a `notification_log` row for (`event_id`, `notification_type`)
   was already created "today" in the platform zone. Dedup keys on the row's creation
   day, so replaying the job with a *past* `today` is NOT dedup-protected — the
   injectable `today` parameter is for deterministic tests only.
4. Broadcast via `send_to_clan`, log the outcome, `commit()` **per event**; a failing
   event is rolled back and skipped so one bad row can't abort the run.

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
| `NOTIFICATION_CRON_HOUR` | `7` | Hour-of-day in the platform zone |
| `SCHEDULER_TIMEZONE` | `Asia/Ho_Chi_Minh` | Validated as IANA name at boot (fail-fast) |
| `FIREBASE_CREDENTIALS_PATH` | `./firebase-credentials.json` | Absent → pushes disabled, app still boots |

## Related

- [Backend i18n](i18n.md) — per-recipient locale resolution for push text
- [Overview](overview.md) — in-process (non-durable) eventing caveats
- [ops/monitoring.md](../ops/monitoring.md) — where the skip/failure logs surface
