# Architecture Overview

## System Architecture

FamilyRoots is a Vietnamese family genealogy platform with a monorepo structure.

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

## Data Isolation

FamilyRoots uses a single PostgreSQL schema with `clan_id`-based isolation, enforced by Supabase Row Level Security (RLS). Users can belong to multiple clans and switch between them via the `X-Current-Clan-Id` header (similar to Slack's workspace switcher).

See [Data Isolation Design](tenant-design.md) for details.

## Clean Architecture Layers

### Backend (Python / FastAPI)

| Layer           | Directory      | Responsibility                           |
|-----------------|----------------|------------------------------------------|
| API             | `app/api/`     | HTTP endpoints, request/response DTOs    |
| Services        | `app/services/`| Business logic, orchestration            |
| Models          | `app/models/`  | SQLAlchemy ORM models                    |
| Schemas         | `app/schemas/` | Pydantic validation schemas              |
| Middleware      | `app/middleware/` | Language detection, Sentry integration |
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

- [Data Isolation Design](tenant-design.md)
- [API Design](api-design.md)
- [Database Schema](database-schema.md)
- [RBAC](rbac.md)
- [IaC Guide](iac-guide.md)
- [Onboarding](onboarding.md)
