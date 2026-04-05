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

Core operations:
- POST /
- GET /
- GET /upcoming?days=N
- GET /{id}
- PATCH /{id}
- DELETE /{id}

Behavior:
- Represents historical and reminder-style family events.
- Used for birthdays, anniversaries, ceremonies, and custom entries.

## Versioning & Compatibility Rules
- Adding new event fields or event types is generally non-breaking.
- Removing or renaming event types is breaking.
- Keep list and detail response envelopes stable for calendars and reminder views.
