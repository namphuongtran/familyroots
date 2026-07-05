# Contract: notifications-api

## Type
REST API

## Owner
backend

## Consumers
- mobile
- web if push/token support expands

## Status
There is no dedicated `/api/v1/notifications` router. The empty stub previously mounted
there was removed (2026-07-05, PR #37) — it exposed no routes. Device-token lifecycle is
served by the auth router; a `/notifications` API (preferences/history) can be added when
that feature is built.

## Schema
Base routes (actual):
- `POST /api/v1/auth/me/fcm-token` — register a device token
- `DELETE /api/v1/auth/me/fcm-token` — remove a device token

Core operations:
- token registration and removal flows are the authenticated endpoints above
- notification delivery is mediated by backend side effects and FCM (the anniversary
  scheduler job → `send_to_clan`), not a client-facing route

Behavior:
- The backend owns notification delivery logic and audit logging.
- Clients mainly manage device token lifecycle.

## Versioning & Compatibility Rules
- Adding token metadata is non-breaking.
- Changing token registration semantics or payload format is breaking.
- Keep notification failure handling recoverable and explicit.
