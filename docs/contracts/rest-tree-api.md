# Contract: tree-api

## Type
REST API

## Owner
backend

## Consumers
- web
- mobile

## Schema
Base route: /api/v1/tree

Core operations:
- GET /
- GET /subtree/{person_id}
- GET /ancestors/{person_id}
- GET /path?from_id=&to_id=

Query parameters:
- root_person_id
- max_generations
- profile
- fields
- include

Behavior:
- Returns graph-oriented responses for family tree exploration.
- Used by web tree visualization and mobile tree interactions.

## Versioning & Compatibility Rules
- Adding optional graph metadata is non-breaking.
- Changing node/edge identifiers or path semantics is breaking.
- Keep traversal responses compatible with visualization clients.
