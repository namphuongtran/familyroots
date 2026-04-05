# backend

## Responsibility
Owns canonical business logic, persistence, and auth context validation. It is the sole owner of the PostgreSQL database and enforces all domain invariants and clan isolation checks. It does NOT handle heavy async tasks like tree exports (which belong to the worker).

## Stack
Python 3.14+, FastAPI, SQLAlchemy Async, asyncpg, Pydantic, Alembic

## Domain Model
- **Person:** Central entity. Represents a family member in a clan. (CRITICAL LANDMINE: Treat carefully)
- **Relationship:** Links between persons (parent/child, marriages).
- **Clan:** Multi-tenant boundary.
- **User:** Authentication identity mapped to Clan Roles. (CRITICAL LANDMINE: Treat carefully)

## API Surface
REST API under `/api/v1/`
- `/persons`, `/relationships`, `/clans`, `/auth`, `/tree`, `/documents`, `/events`, `/branches`

## Event Contracts
Publishes: Domain Events (e.g., `person.created`, `relationship.added`) → consumed by `worker` (via Redis Pub/Sub)

## Data Ownership
Exclusively owns the `public` schema in PostgreSQL (all tables including `persons`, `clans`, `relationships`, etc.).

## Key Commands
- dev: `make backend-dev`
- test: `make backend-test`
- lint: `make backend-lint`
- migrate: `make migrate`
- seed: `make seed`

## Error Handling Pattern
Standardized JSON envelope with `error.code`, `error.message`, and `error.detail`. Handled globally via custom exception handlers for `AppError` and `DomainError`.

## Don't Do
- Do not import FastAPI/SQLAlchemy inside `app/domain/`.
- Do not execute database queries inside API routers; use the application layer.
- Do not bypass `X-Current-Clan-Id` checks.

## Known Issues
- Currently relies on in-process domain events. Needs migration to Redis Pub/Sub.