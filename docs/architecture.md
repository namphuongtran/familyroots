# Architecture Overview

## System Architecture

FamilyRoots is a Vietnamese family genealogy platform with a monorepo structure.

```
┌─────────────────┐     ┌─────────────────┐
│  Mobile App      │     │  Web App         │
│  (Flutter)       │     │  (Next.js 16)    │
│  iOS / Android   │     │  Browser + Admin │
└────────┬────────┘     └────────┬────────┘
         │                       │
         └───────────┬───────────┘
                     │
              ┌──────▼──────┐
              │  Backend API │
              │  (FastAPI)   │
              │  Port: 8000  │
              └──────┬──────┘
                     │
         ┌───────────┼───────────┐
         │           │           │
   ┌─────▼─────┐ ┌──▼───┐ ┌────▼────┐
   │ PostgreSQL │ │ FCM  │ │ Sentry  │
   │ (Supabase) │ │      │ │         │
   └───────────┘ └──────┘ └─────────┘
```

## Data Isolation

FamilyRoots uses a single PostgreSQL schema with `clan_id`-based isolation, enforced by Supabase Row Level Security (RLS). Users can belong to multiple clans and switch between them via the `X-Current-Clan-Id` header (similar to Slack's workspace switcher).

See [Data Isolation Design](tenant-design.md) for details.

## Backend Architecture (DDD)

The backend follows **Domain-Driven Design** with **CQRS** (Command/Query Responsibility Segregation) and the **hexagonal architecture** pattern (ports and adapters).

### Layer Structure

```
app/
├── api/             # Controllers — thin HTTP layer, request/response mapping
├── application/     # Use cases — command/query handlers (CQRS)
├── domain/          # Core business logic — entities, events, value objects, ports
├── infrastructure/  # Adapters — repositories, UoW, event dispatcher, external services
├── core/            # Cross-cutting — config, security, database, permissions, exceptions
├── middleware/       # HTTP middleware — language detection, rate limiting
├── models/          # SQLAlchemy ORM models (shared infrastructure)
└── schemas/         # Pydantic v2 request/response DTOs
```

### Layer Rules

| Layer            | Can Depend On                              | Must NOT Import            |
|------------------|--------------------------------------------|----------------------------|
| `domain/`        | Nothing (pure Python, framework-agnostic)  | FastAPI, SQLAlchemy, Pydantic |
| `application/`   | `domain/`                                  | `infrastructure/`, `api/`  |
| `infrastructure/`| `domain/`, `models/`, `schemas/`           | `api/`, `application/`     |
| `api/`           | `application/`, `schemas/`, `core/`        | `domain/` (indirect via handlers) |

### Bounded Contexts

Each bounded context follows a consistent structure:

```
domain/{context}/
├── entity.py        # Aggregate root
├── events.py        # Domain events
├── repository.py    # Repository protocol (port)
├── query_port.py    # Read-side query protocol (port)
└── value_objects.py # Value objects (if any)

application/{context}/
├── commands.py      # Frozen dataclass command/query DTOs
└── handlers.py      # CommandHandler / QueryHandler
```

Active contexts: `person`, `relationship`, `auth`, `clan`, `document`, `event`, `tree`, `branch`, `me`, `platform_admin`.

### Key Patterns

| Pattern             | Implementation                                                     |
|---------------------|--------------------------------------------------------------------|
| **Unit of Work**    | `SqlAlchemyUnitOfWork` — flush → collect events → dispatch → commit |
| **Domain Events**   | `InMemoryEventDispatcher` — automatic `AuditLog` for `AuditableEvent`s |
| **CQRS**            | Separate `CommandHandler` (writes) and `QueryHandler` (reads)      |
| **Hexagonal Ports** | `Protocol`-based ports in `domain/`, adapters in `infrastructure/` |
| **Sparse Fieldsets**| `?fields=`, `?profile=summary|detail|full`, `?include=` query params |

### Flutter (Dart / Mobile)

| Layer           | Directory        | Responsibility                         |
|-----------------|------------------|----------------------------------------|
| Data            | `data/`          | Datasources, models, repository impl   |
| Domain          | `domain/`        | Entities, repo interfaces, use cases   |
| Presentation    | `presentation/`  | BLoC, pages, widgets                   |

## Technology Stack

| Component     | Technology                  |
|---------------|------------------------------|
| Backend API   | FastAPI (Python 3.14+)       |
| Mobile        | Flutter (Dart)               |
| Web           | Next.js 16 (App Router)      |
| Database      | PostgreSQL 18 (Docker/Render) / PostgreSQL 17 (Supabase) |
| Auth          | JWT via Supabase JWKS (RS256)|
| Push Notifs   | Firebase Cloud Messaging     |
| Error Track   | Sentry                       |
| IaC           | Pulumi (Python)              |
| Hosting       | Render (API), Vercel (Web)   |
| CI/CD         | GitHub Actions               |

## Shared Code

The `packages/family_roots_core/` Dart package contains shared entities, API clients, and utilities used by the mobile app. It is referenced as a path dependency in each `pubspec.yaml`.

## Deployment

- **Backend**: Docker → Render.com (via `render.yaml`)
- **Web**: Next.js → Vercel (via GitHub Actions)
- **Mobile**: Flutter → App Store / Google Play (via GitHub Actions APK build)
- **Database**: Supabase managed PostgreSQL

## Related Docs

- [Data Isolation Design](tenant-design.md)
- [API Design](api-design.md)
- [Database Schema](database-schema.md)
- [RBAC](rbac.md)
- [IaC Guide](iac-guide.md)
- [Onboarding](onboarding.md)
