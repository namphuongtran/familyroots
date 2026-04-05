# Contract: notifications-api

## Type
REST API

## Owner
backend

## Consumers
- mobile
- web if push/token support expands

## Schema
Base route: /api/v1/notifications

Core operations:
- token registration and removal flows are supported through authenticated client endpoints
- notification delivery is mediated by backend side effects and FCM

Behavior:
- The backend owns notification delivery logic and audit logging.
- Clients mainly manage device token lifecycle.

## Versioning & Compatibility Rules
- Adding token metadata is non-breaking.
- Changing token registration semantics or payload format is breaking.
- Keep notification failure handling recoverable and explicit.
