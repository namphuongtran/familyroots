# Contract: platform-admin-api

## Type
REST API

## Owner
backend

## Consumers
- web
- ops/admin workflows

## Schema
Base route: /api/v1/platform

Core operations:
- GET /clans
- GET /clans/{clan_id}
- other super-admin operations exposed by router

Behavior:
- Restricted to super-admin identity checks.
- Used for platform-wide oversight rather than clan-scoped business workflows.

## Versioning & Compatibility Rules
- Any change to super-admin authorization is high risk and should be treated as breaking.
- Keep platform-wide admin responses stable.
