# FamilyRoots

## What This System Does
FamilyRoots is a Vietnamese genealogy platform that allows clans to maintain accurate family trees, member profiles, and life events across web and mobile clients. The platform caters to two primary personas: "Clan Elders" who manage and curate the historical records, and "Younger Generations" who consume notifications (e.g., death anniversaries) and explore their heritage. It features multi-clan workspaces, role-based access, and clan-scoped data isolation, monetized potentially through premium features or subscriptions for larger clans.

## System Stage
Growing — Transitioning from in-process events to a distributed architecture (adding Redis Pub/Sub and a dedicated async worker for heavy exports) to support scaling. The team consists of one human engineer and an Agentic AI acting as a Solo-Dev team.

## How to Use This Second Brain
- Before planning:       paste `docs/prompts/before-plan.md`
- Brainstorming:         paste `docs/prompts/brainstorm.md`
- Cross-service change:  paste `docs/prompts/check-contracts.md`
- End of session:        paste `docs/prompts/update-knowledge.md`
- New service:           paste `docs/prompts/new-service.md`

## Global Rules
- Backend follows DDD + CQRS + hexagonal boundaries.
- Domain layer must remain framework-agnostic.
- Application layer may import domain only, not infrastructure.
- All write operations should flow through Unit of Work and publish events to Redis.
- Clan-scoped APIs must enforce X-Current-Clan-Id context and role checks.
- Public API errors should keep stable structured envelope semantics.
- Mobile UI must follow Arbor Heritage design mandates and localization rules.
- Mobile UI testing, dependency injection, and layout fixes must follow lessons in `docs/flutter-lessons.md`.
- **ALWAYS check docker-compose to ensure backend and frontend are working as expected.**
- **Be exceptionally careful with `user` and `person` data in the clan, as these are critical landmines.**

## Never Do
- Never bypass clan isolation checks for convenience.
- Never import FastAPI/SQLAlchemy/Pydantic directly into backend domain layer.
- Never bypass repository/application boundaries from frontend presentation code.
- Never commit secrets or plain .env files.
- Never treat in-process events as durable integration events (migrating to Redis).

## Services Map
| Service | Responsibility | Tech | Port |
|---------|---------------|------|------|
| backend | Canonical business logic, persistence, auth validation, contracts | FastAPI, SQLAlchemy async, PostgreSQL | 8000 |
| web | Browser UX and admin workflows over backend contracts | Next.js 16, React 19, TypeScript | 3000 |
| mobile | Native UX and app interactions over backend contracts | Flutter, Dart, BLoC, Dio/Retrofit | N/A |
| worker | Heavy async processing (e.g., PDF/Tree exports) | Python, Redis | N/A |

## Shared Infrastructure
- PostgreSQL (Supabase managed and local Docker)
- Supabase Auth and Storage
- Firebase Cloud Messaging
- Redis (Pub/Sub message broker for events)
- Sentry monitoring
- Render backend hosting blueprint
- Vercel web deployment pipeline
- GitHub Actions CI/CD workflows (Mobile deployed automatically to App/Play Store via CI)

## Key Global Commands
- Local infra: `make docker-up` or `docker compose up -d`
- Check all infra: `make docker-all` (Crucial to verify backend & frontend stability)
- Backend dev: `make backend-dev`
- Backend test: `make backend-test`
- Backend migrate: `make migrate`
- Web dev: `make web-dev`
- Web quality: `make web-type-check` and `make web-lint`
- Mobile dev: `make mobile-run`
- Mobile quality: `make mobile-test` and `make mobile-analyze`

## Known Pain Points
- Migrating in-process events to Redis Pub/Sub requires refactoring the Unit of Work (ADR-004).
- Pulumi resources are currently stubs and create deployment drift.