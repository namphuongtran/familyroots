# Contract: Redis Domain Events

> ⚠️ **DESIGN TARGET — NOT IMPLEMENTED.** There is no Redis anywhere in the codebase
> (no dependency, no docker service, no publisher/consumer). Domain events today are
> dispatched in-process inside the Unit of Work transaction (see
> [domain-events-catalog.md](domain-events-catalog.md) and ADR-004, which is
> explicitly deferred). Treat this file as the future integration contract only.

## Type
Redis Pub/Sub / Queue

## Owner
backend (Publisher)

## Consumers
- worker (Consumer)
- audit-logger (Consumer)

## Schema
Base Event Envelope:
```json
{
  "event_id": "uuid",
  "event_type": "domain.entity.action",
  "timestamp": "iso8601",
  "clan_id": "uuid",
  "actor_id": "uuid",
  "payload": { ... }
}
```

Key Event Types:
- `person.created`
- `person.updated`
- `person.deleted`
- `relationship.added`
- `export.tree_pdf.requested`

Example `export.tree_pdf.requested` payload:
```json
{
  "clan_id": "...",
  "root_person_id": "...",
  "options": {
    "generations_up": 3,
    "generations_down": 3
  }
}
```

## Compatibility Rules
- Non-breaking: add fields to payload.
- Breaking: remove fields or change `event_type` naming convention.
- Breaking changes require consumers to be updated and deployed before publishers.