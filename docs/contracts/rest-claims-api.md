# Contract: claims-api

## Type
REST API

## Owner
backend

## Consumers
- web
- backend admin workflows

## Schema
Base route: /api/v1/claims and /api/v1/clans/{clan_id}/claims

Core operations:
- user claims submission and review flows
- clan-scoped claim review and admin decisions
- platform/admin support for identity governance

Behavior:
- Supports identity claim workflows for users and clan admins.
- Contains both user-facing and admin-facing surfaces.

## Versioning & Compatibility Rules
- Adding claim metadata is non-breaking.
- Changing approval state transitions is breaking.
- Keep review workflow contracts explicit and documented.
