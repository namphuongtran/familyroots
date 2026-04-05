# Contract: me-api

## Type
REST API

## Owner
backend

## Consumers
- web
- mobile

## Schema
Base route: /api/v1/me

Core operations:
- GET /clans
- POST /switch-clan

Behavior:
- Returns the current user's clan memberships.
- Switch-clan updates the active clan context used by clan-scoped APIs.
- Clients must persist the chosen clan context and send X-Current-Clan-Id on subsequent requests.

## Versioning & Compatibility Rules
- Adding new membership metadata is non-breaking.
- Changing the clan-switch flow requires coordinated client updates.
- The selected clan context contract should remain explicit and stable.
