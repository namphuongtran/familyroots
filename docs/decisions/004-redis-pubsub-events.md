# ADR-004: Redis for Distributed Domain Events

## Status
Accepted

## Context
The backend currently uses an in-process event dispatcher. As the system scales and we introduce a dedicated worker service for heavy tasks, in-process events lack durability and cannot cross process boundaries.

## Decision
Introduce Redis as the standard message broker for domain events and background task queues. The backend Unit of Work will publish events to Redis after successfully committing to PostgreSQL.

## Consequences
Easier:
- Integrating separate services (like the new worker).
- Guaranteeing background tasks don't get lost on API restart.

Harder:
- Requires Redis infrastructure locally (`docker-compose`) and in production.
- Need to implement robust retry and DLQ (Dead Letter Queue) mechanisms.