# Contract: auth-api

## Type
REST API

## Owner
backend

## Consumers
- web
- mobile

## Schema
Base route: /api/v1/auth

Core operations:
- POST /register
- POST /login
- POST /logout
- POST /refresh
- GET /me
- PATCH /me
- POST /me/fcm-token
- DELETE /me/fcm-token

Request/response expectations:
- Bearer JWT is required after login.
- Register can either join an existing clan or create a new clan.
- Login returns authenticated session/profile data for client bootstrap.
- FCM token endpoints are used by mobile and any push-enabled clients.

## Versioning & Compatibility Rules
- Adding optional auth/profile fields is non-breaking.
- Changing login/register payload requirements is breaking.
- Keep error envelopes and token semantics stable across client releases.
