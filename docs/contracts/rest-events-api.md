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
- GET /upcoming?days=N
- GET /{id}
- PATCH /{id}  (editor)
- DELETE /{id}  (editor)

List response envelope (cursor pagination):
```
{
  "data": [ ... ],
  "meta": { "cursor": "<base64|null>", "has_more": true, "limit": 20 }
}
```
- `GET /upcoming` returns a plain list (not paginated).
- `person_id` on create is validated to belong to the active clan; it is create-only.

Behavior:
- Represents historical and reminder-style family events.
- Used for birthdays, anniversaries, ceremonies, and custom entries.

## Versioning & Compatibility Rules
- Adding new event fields or event types is generally non-breaking.
- Removing or renaming event types is breaking.
- Keep list and detail response envelopes stable for calendars and reminder views.
