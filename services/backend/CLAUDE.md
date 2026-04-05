# backend

## Responsibility
Owns the canonical business logic and persistence for clan genealogy data, auth context validation, and audit logging.
It does not own presentation concerns, mobile/web UI state, or client-side caching semantics.

## Stack
- Python 3.14+
- FastAPI
- SQLAlchemy 2.x async + asyncpg
- PostgreSQL (Supabase + local Docker PG)
- Alembic migrations
- Pydantic v2
- Supabase Auth JWT validation
- Firebase Admin (notifications)
- APScheduler (scheduled reminders)

## Domain Model
Key entities:
- Clan, ClanMembership, UserClanRole, UserProfile
- Person (global person identity)
- Marriage and ParentChild (relationship graph)
- Document and Event (person/clan attachments)
- Branch (family branch metadata)
- IdentityClaim and ChangeRequest (governance)
- AuditLog and NotificationLog

Relationship summary:
- A user can belong to many clans.
- A person can exist in many clans through memberships and links.
- Marriage and parent-child links form genealogy graph edges.
- Documents/events attach to person/clan contexts and are clan-scoped.

## API Surface
Main REST routes under /api/v1:
- /auth
- /me
- /clans
- /persons
- /relationships
- /tree
- /documents
- /events
- /branches
- /claims
- /platform-admin
- /notifications

Cross-cutting headers:
- Authorization: Bearer JWT
- X-Current-Clan-Id
- Accept-Language

## Event Contracts
Consumes:
- HTTP requests from web and mobile clients
- Supabase JWT claims for user identity

Publishes:
- In-process domain events via InMemoryEventDispatcher
- AuditableEvent records to audit_log table
- Push notification side effects via Firebase service (selected flows)

## Data Ownership
Owns PostgreSQL schema objects and migration history in backend/migrations and infra/supabase.
Primary ownership includes persons, relationships, clans, memberships, documents, events, claims, and audit tables.

## Key Commands
- Dev: cd backend && .venv/bin/uvicorn app.main:app --reload
- Test: cd backend && .venv/bin/pytest
- Lint: cd backend && .venv/bin/ruff check .
- Type check: cd backend && .venv/bin/mypy app
- Migrate: cd backend && .venv/bin/alembic upgrade head

## Error Handling Pattern
Raise domain exceptions in domain/application layers and map them in core/exceptions to stable HTTP error envelopes:
- entity not found -> 404
- business rule violation/conflict -> 409/422
- auth/permission errors -> 401/403

## Don't Do
- Do not import framework libraries in domain layer.
- Do not bypass Unit of Work for writes.
- Do not access infrastructure adapters directly from application commands.
- Do not skip clan-context checks on clan-scoped endpoints.

## Known Issues / Landmines
- In-memory event dispatcher is not durable across process restarts. <!-- TODO: verify this -->
- Notification and several script/test modules still contain Prompt 2 scaffolding TODOs. <!-- TODO: verify this -->
- Pulumi integration is incomplete, so infra deployment can drift from backend assumptions. <!-- TODO: verify this -->
