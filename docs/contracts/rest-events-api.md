# Contract: events-api

## Type
REST API

## Owner
backend

## Consumers
- web
- mobile

## Schema
Base route: /api/v1/events

Core operations (create/update/delete require editor):
- POST /  (editor)
- GET /  (cursor-paginated; query params: cursor, limit, person_id, event_type, fields)
- GET /upcoming?days=N  (also accepts include=person)
- GET /{id}  (also accepts include, fields)
- PATCH /{id}  (editor; requires `expected_version`)
- DELETE /{id}  (editor; soft delete)
- POST /{id}/restore  (editor)

Optimistic concurrency + soft delete (ADR-022, matching persons/marriages):
- Every event response carries `"version": <int>` (≥1), bumped on every
  successful write to that row — including DELETE/restore.
- `PATCH /{id}` requires body field `expected_version: int (>=1)` (422 when
  missing); a stale value returns 409 `stale_write` with
  `detail.current_version`; success echoes `version` = expected + 1.
- `DELETE /{id}` is a soft delete: the row survives, flagged `is_deleted`,
  and disappears from GET/list/upcoming/timeline reads. `POST /{id}/restore`
  brings it back (404 when the event is not deleted). There is no retention
  purge for events — a deleted giỗ record is recoverable indefinitely.

List response envelope (cursor pagination):
```
{
  "data": [ ... ],
  "meta": { "cursor": "<base64|null>", "has_more": true, "limit": 20 }
}
```
- `GET /upcoming` returns a plain list (not paginated).
- `person_id` on create is validated to belong to the active clan (a soft-deleted
  person is rejected as `person_not_found`, same as nonexistent — M3, review
  2026-07-18); it is create-only.
- `GET /upcoming` also excludes an event whose linked `person_id` is currently
  soft-deleted (person-less clan-ceremony events are unaffected), matching the
  anniversary scheduler's own exclusion — the two no longer disagree on which
  events are due (M3, review 2026-07-18).

Behavior:
- Represents historical and reminder-style family events.
- Used for birthdays, anniversaries, ceremonies, and custom entries.
- `GET /upcoming` — for a recurring event with `is_lunar_calendar = true`, the
  returned `next_occurrence` is the **converted solar date of the next lunar
  anniversary**, not a solar month/day match on `event_date`. Conversion uses the
  in-house Vietnamese lunar calendar engine (UTC+7) with the traditional giỗ
  conventions: a death in a leap month (tháng nhuận) is observed every year in the
  regular month of the same number, and a death on lunar day 30 clamps to day 29
  in years where that month has only 29 days. See
  [ADR-018](../decisions/018-vietnamese-lunar-calendar.md). Non-recurring events
  (lunar or not) keep `next_occurrence = event_date`.

## Versioning & Compatibility Rules
- Adding new event fields or event types is generally non-breaking.
- Removing or renaming event types is breaking.
- Keep list and detail response envelopes stable for calendars and reminder views.
