# Notification / Scheduler Robustness — Design (2026-07-04)

**Status:** approved (owner) — proceeding to implementation plan.

## Goal

Make the anniversary notification job actually work correctly. Today: pushes render raw
i18n key strings, every user gets Vietnamese, the member query crashes outside Supabase
(joins `auth.users`), the FCM send blocks the event loop and commits mid-broadcast, one
bad event aborts the whole run, and lunar anniversaries fire on the wrong (solar) day.

This is **PR-H** of the demand-driven Important-tier remediation (seam-review §5, S2).
C2 (PR-H1, merged) already fixed the leap-date crash, the advisory-lock strand, and the
timezone/single-clock (S2-8). This PR fixes the remaining S2 Important items.

## Context — current post-C2 state (verified)

`app/services/scheduler.py::send_anniversary_notifications` runs on one dedicated
connection with a session-level advisory lock, a single `today` clock, tz-consistent
dedup, and leap-safe `next_anniversary_sql` (all from C2 — do NOT touch). The per-event
loop calls `send_to_clan` (`app/services/notification.py`) then inserts a
`notification_log` row and commits per event.

Recurring notified event types (CHECK-constrained): `death_anniversary`, `birthday`,
`wedding_anniversary`. i18n currently has only flat keys `notification.{type}` (body-like
sentences). `user_profiles.language` (String(10), default `"vi"`) is the local locale
source. `t()` is `def t(key, **kwargs)` reading the `current_locale` contextvar.

## Decisions (owner-approved)

- **Lunar (S2-4): exclude + document.** Add `AND e.is_lunar_calendar = false` to the job
  query; log a one-line deferred-count; doc-comment the deferral. Solar events still
  notify correctly; correct lunar support (structured lunar dates + conversion) is
  deferred to the data-model round 2. Rationale: sending on the wrong solar day is worse
  than not sending; the data model doesn't yet store structured lunar dates.
- **i18n (S2-2a): title/body pairs.** Replace the flat `notification.{type}` keys with
  `notification.{type}.title` + `notification.{type}.body` in all four locales (body = the
  existing sentence; title = a short label). Keeps the scheduler's existing `.title`/`.body`
  construction — no job-code change for keys.
- **Defer S2-10** (exact-day match drops missed runs) — widening the window safely needs
  a dedup redesign (per-occurrence-year, not per-day); out of scope, documented follow-up.

## Design

### 1. Lunar exclusion (S2-4) — `scheduler.py`
Add `AND e.is_lunar_calendar = false` to the recurring-events `WHERE`. After building
`events`, if any lunar recurring events exist for today, `logger.info` a one-line count
("N lunar recurring events skipped — lunar support deferred to data-model round 2"). A
cheap `COUNT` (or a second predicate query) is acceptable; keep it one extra read, not
per-event.

### 2. i18n title/body (S2-2a) — `i18n/{vi,en,zh,fr}.json`
For each of `death_anniversary`, `birthday`, `wedding_anniversary`: add
`notification.<type>.title` and `notification.<type>.body`. `body` = the existing flat
sentence verbatim (e.g. vi `notification.death_anniversary.body` = "Ngày giỗ của {name}
còn {days} ngày nữa"); `title` = a short localized label (vi: "Ngày giỗ" / "Sinh nhật" /
"Kỷ niệm ngày cưới"; en: "Death anniversary" / "Birthday" / "Wedding anniversary"; zh/fr
equivalents). Remove the now-orphaned flat `notification.<type>` keys **only after**
grep-confirming no other consumer (the scheduler is the only known one; the translator
docstring example is illustrative, not a call site — verify). The all-locale i18n guard
must stay green (all four locales get the same key set).

### 3. Per-user locale (S2-2b) — `translator.py`, `notification.py`
- `t(key, *, locale: str | None = None, **kwargs)` → resolve with `locale or current_locale.get()`. Backward-compatible (existing callers pass no `locale`).
- `send_push_notification(...)` already receives `locale`; pass it through: `t(title_key, locale=locale, **kwargs)` / `t(body_key, locale=locale, **kwargs)`.
- `send_to_clan` already selects a per-user locale and passes `locale=row["locale"]` — after §4 that value is `user_profiles.language`. Net: each user's push renders in their language.

### 4. auth.users → user_profiles (S2-5) — `notification.py`
In `send_to_clan`, replace the `LEFT JOIN auth.users au ... COALESCE(au.raw_user_meta_data->>'preferred_locale','vi')` with
`LEFT JOIN public.user_profiles up ON up.id = ucr.user_id` and
`COALESCE(up.language, 'vi') AS locale`. Fixes the local/CI `UndefinedTable` crash and
reads the real local locale. (Keep `LEFT JOIN` — a member without a profile row still
gets the `'vi'` default.)

### 5. Off-load + no mid-broadcast commit (S2-6) — `notification.py`
- `await asyncio.to_thread(messaging.send, message)` instead of the direct sync call — the
  event loop is no longer blocked per token.
- Remove the `await db.commit()` from `_remove_invalid_token`: it must not commit the
  shared job session mid-broadcast. The stale-token `DELETE` stays staged on the session
  and is persisted by the job's existing per-event commit. (`send_push_notification` is
  only reached from `send_to_clan`, which the job commits per event — grep-verify no other
  caller relies on the old commit.)

### 6. Per-event error isolation (S2-3) — `scheduler.py`
Wrap the per-event body (dedup check → `send_to_clan` → `notification_log` insert →
`db.commit()`) in `try/except Exception`: on failure, `logger.exception` with the
`event_id`, `await db.rollback()` (clear the aborted tx so the next event's statements
run), and `continue`. One bad event no longer abandons the rest of the run. The outer
`finally` (rollback→unlock→commit) is unchanged.

### 7. Minors (same area)
- **S2-11 soft-deleted persons** — add `AND (e.person_id IS NULL OR p.is_deleted = false)`
  to the job query so a soft-deleted person's anniversary stops broadcasting.
- **S2-9 truthful log status** — `send_to_clan` returns `(sent, failed)` counts; the job
  writes `status = 'sent'` only when `sent > 0`, else `'failed'`, and populates
  `error_message` (e.g. "0/N delivered") on total failure. No more asserting success when
  every token failed.
- **S2-13 dead setting** — remove `NOTIFICATION_DAYS_BEFORE` from `core/config.py`,
  `.env.example`, and the `backend/CLAUDE.md` mention (the job uses per-event
  `notify_days_before`; the global setting is read by nothing — grep-verify).

## Tests (TDD)
- **Lunar exclusion** — seed a recurring lunar event due today + a solar one; assert only
  the solar one is sent (the lunar is skipped and counted).
- **i18n render** — with translations loaded, a push for each type renders a real
  title+body (not the raw `notification.<type>.title` key); a non-`vi` `language` renders
  that locale (drive `t(key, locale="en")` and a `send_to_clan` row with `language='en'`).
- **user_profiles join** — `send_to_clan` runs against the migrated test DB (no `auth`
  schema) without `UndefinedTable`, and picks up `user_profiles.language`.
- **Off-load / no mid-commit** — `messaging.send` invoked via `to_thread`
  (patch `messaging.send`, assert called); `_remove_invalid_token` does not call
  `db.commit`.
- **Per-event isolation** — two due events where the first raises in `send_to_clan`;
  assert the second still processes and the run completes.
- **Truthful status** — all sends fail → the `notification_log` row is `status='failed'`.
- **Regression** — the existing `tests/integration/test_scheduler_lock.py` and
  `tests/test_notifications.py` stay green (adjust mocks only where the signature genuinely
  changed, e.g. `send_to_clan` now returns counts).

## Out of scope (deliberate)
- Lunar→solar conversion / structured lunar dates (data-model round 2).
- S2-10 missed-run window widening (needs per-occurrence dedup redesign).
- Durable/queued delivery (ADR-004 Redis bus).
- **Populating `user_profiles.language`** — the per-recipient locale plumbing (S2-2b) is
  wired here, but the column is never written today (the login/profile flow stores the
  chosen locale only in Supabase user metadata). Until the **Auth PR** writes
  `user_profiles.language` (alongside the `preferred_locale` round-trip, S7-4), pushes
  default to `vi` — valid localized text, just not per-user language yet. Whole-branch
  review flagged this; deferred to the Auth work rather than pull auth-flow changes here.

## Files touched
`app/services/scheduler.py` · `app/services/notification.py` · `app/services/translator.py` ·
`app/i18n/{vi,en,zh,fr}.json` · `app/core/config.py` · `.env.example` · `backend/CLAUDE.md` ·
tests.

## Packaging
One PR `fix/notification-robustness`, TDD → full gate (`scripts/check.sh`) → subagent review → PR.
