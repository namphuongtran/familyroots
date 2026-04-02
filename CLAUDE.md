# CLAUDE.md — FamilyRoots Development Context

## Project Overview

Vietnamese family genealogy platform. Monorepo: Python FastAPI backend + Flutter mobile + Next.js 16 web.

> **Note on Mobile UI Development:** See `mobile/CLAUDE.md` for specific rules regarding Flutter UI implementation, Design System ("Arbor Heritage") adherence, and Stitch integration workflow.

## Architecture

Backend uses **Domain-Driven Design** with CQRS, hexagonal ports/adapters, and Unit of Work.

### Layer Structure

```
app/
├── api/             # Thin controllers (FastAPI routers)
├── application/     # Command/Query handlers (CQRS)
├── domain/          # Entities, events, ports, value objects (NO FRAMEWORK IMPORTS)
├── infrastructure/  # Repository impls, UoW, event dispatcher
├── core/            # Config, security, permissions, database, exceptions
├── models/          # SQLAlchemy ORM models
├── schemas/         # Pydantic v2 DTOs
├── services/        # Legacy services (being migrated to domain layer)
└── middleware/       # HTTP middleware
```

### Critical Import Rules

- `domain/` → must NOT import FastAPI, SQLAlchemy, or Pydantic
- `application/` → may import `domain/` only, NOT `infrastructure/`
- `infrastructure/` → may import `domain/`, `models/`, `schemas/`
- `api/` → may import `application/`, `schemas/`, `core/`

### Adding a New Feature

1. Define the domain entity in `domain/{context}/entity.py`
2. Define domain events in `domain/{context}/events.py`
3. Define the repository protocol in `domain/{context}/repository.py`
4. Create command/query DTOs as `frozen=True` dataclasses in `application/{context}/commands.py`
5. Create handlers in `application/{context}/handlers.py`
6. Implement repository in `infrastructure/persistence/{context}_repository.py`
7. Wire dependency injection in `infrastructure/dependencies.py`
8. Create API routes in `api/v1/{context}.py`

### Patterns

- **Commands/Queries**: Use `@dataclass(frozen=True)` with an `ActorInfo` field
- **Domain Events**: Emit `AuditableEvent` subclasses for automatic audit logging
- **Unit of Work**: Always use `async with uow:` for write operations
- **Query Ports**: Use `Protocol` in domain, implement in `infrastructure/persistence/`
- **Error Handling**: Raise domain exceptions (`EntityNotFoundError`, `BusinessRuleViolation`) — they're mapped to HTTP by `core/exceptions.py`

### Data Isolation

All clan-scoped endpoints require `X-Current-Clan-Id` header. The `get_current_clan_id()` dependency validates membership and auto-selects for single-clan users.

### API Query Parameters

- `?profile=summary|detail|full` — sparse fieldset profiles
- `?fields=field1,field2` — explicit field selection
- `?include=marriages,documents,events,parent_child_links` — compound documents (eager load)
- `?include=stats` — include aggregate counts in list endpoints

## Commands

```bash
# Run backend
cd backend && .venv/bin/uvicorn app.main:app --reload

# Run tests
cd backend && .venv/bin/pytest

# Run web frontend
cd web && npm run dev
```

## Key Files

- `app/main.py` — App factory, middleware setup
- `app/core/security.py` — JWT validation, user profile, clan context
- `app/core/permissions.py` — RBAC: `RequireViewer`, `RequireEditor`, `RequireAdmin`, `RequireClanRole`
- `app/infrastructure/unit_of_work.py` — UoW with event dispatching
- `app/infrastructure/event_dispatcher.py` — `AuditLogHandler` for automatic audit logs
- `app/infrastructure/dependencies.py` — All DI wiring

## Style

- Python 3.14+ syntax (`X | None`, not `Optional[X]`)
- Pydantic v2 (`model_validate`, `model_dump`, `model_config`)
- SQLAlchemy 2.x (`Mapped[]`, `mapped_column()`, `select()`)
- All public functions need docstrings and type hints
