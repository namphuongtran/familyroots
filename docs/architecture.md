# Architecture Overview

## System Architecture

FamilyRoots is a multi-tenant Vietnamese family genealogy platform with a monorepo structure.

```
┌─────────────────┐     ┌─────────────────┐
│  Mobile App      │     │  Web App         │
│  (Flutter)       │     │  (Flutter Web)   │
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

## Multi-Tenant Design

Each family clan gets an isolated PostgreSQL schema (`clan_{slug}`). Tenant resolution happens via:

1. JWT token → `clan_id` claim
2. Middleware sets `search_path` to tenant schema
3. All queries are scoped to the active tenant

See [tenant-design.md](tenant-design.md) for details.

## Clean Architecture Layers

### Backend (Python / FastAPI)

| Layer           | Directory      | Responsibility                           |
|-----------------|----------------|------------------------------------------|
| API             | `app/api/`     | HTTP endpoints, request/response DTOs    |
| Services        | `app/services/`| Business logic, orchestration            |
| Models          | `app/models/`  | SQLAlchemy ORM models                    |
| Schemas         | `app/schemas/` | Pydantic validation schemas              |
| Middleware      | `app/middleware/` | Tenant resolution, Sentry integration |
| Core            | `app/core/`    | Config, security, database, logging      |

### Flutter (Dart / Mobile + Web)

| Layer           | Directory        | Responsibility                         |
|-----------------|------------------|----------------------------------------|
| Data            | `data/`          | Datasources, models, repository impl   |
| Domain          | `domain/`        | Entities, repo interfaces, use cases   |
| Presentation    | `presentation/`  | BLoC, pages, widgets                   |

## Technology Stack

| Component     | Technology                  |
|---------------|-----------------------------|
| Backend API   | FastAPI (Python 3.12+)      |
| Mobile        | Flutter (Dart)              |
| Web           | Flutter Web (Dart)          |
| Database      | PostgreSQL 16 (Supabase)    |
| Auth          | JWT (python-jose)           |
| Push Notifs   | Firebase Cloud Messaging    |
| Error Track   | Sentry                      |
| IaC           | Pulumi (Python)             |
| Hosting       | Render (API), Vercel (Web)  |
| CI/CD         | GitHub Actions              |

## Shared Code

The `packages/family_roots_core/` Dart package contains shared entities, API clients, and utilities used by both mobile and web apps. It is referenced as a path dependency in each `pubspec.yaml`.

## Deployment

- **Backend**: Docker → Render.com (via `render.yaml`)
- **Web**: Flutter Web → Vercel (via GitHub Actions)
- **Mobile**: Flutter → App Store / Google Play (via GitHub Actions APK build)
- **Database**: Supabase managed PostgreSQL

## Related Docs

- [Tenant Design](tenant-design.md)
- [API Design](api-design.md)
- [Database Schema](database-schema.md)
- [RBAC](rbac.md)
- [IaC Guide](iac-guide.md)
- [Onboarding](onboarding.md)
