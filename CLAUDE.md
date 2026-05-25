# FamilyRoots

## What This System Does
FamilyRoots is a Vietnamese genealogy platform that lets clans maintain accurate family trees across web and mobile clients. It provides role-based collaboration, auditability, multilingual UX, and clan-scoped data isolation so multiple family communities can coexist safely in one platform.

## Current Stage
Growing, with strong architectural foundations and active scaffold-to-build work in selected areas (mobile modules, infra automation, and auxiliary scripts).

## How to Use This Second Brain
- Before planning any feature: run /project:before-plan
- After finishing any session: run /project:update-knowledge
- Adding a new service: run /project:new-service
- Brainstorming: run /project:brainstorm
- Cross-service change: run /project:check-contracts first
- First-time refresh/bootstrap: run /project:setup-knowledge
- Sync CLAUDE.md with repo changes: run /project:sync-claude-md

## Global Rules
- Backend follows DDD + CQRS + hexagonal boundaries.
- Domain layer must remain framework-agnostic.
- Application layer may import domain only, not infrastructure.
- All write operations should flow through Unit of Work and domain events.
- Clan-scoped APIs must enforce X-Current-Clan-Id context and role checks.
- Public API errors should keep stable structured envelope semantics.
- Mobile UI must follow Arbor Heritage design mandates and localization rules.
- Dart business entities live in mobile/lib/domain.

## Never Do
- Never bypass clan isolation checks for convenience.
- Never import FastAPI/SQLAlchemy/Pydantic directly into backend domain layer.
- Never bypass repository/application boundaries from frontend presentation code.
- Never commit secrets or plain .env files.
- Never treat in-process events as durable integration events without explicit mitigation.

## Services Map
| Service | Responsibility | Tech | Port |
|---------|---------------|------|------|
| backend | Canonical business logic, persistence, auth context validation, contracts | FastAPI, SQLAlchemy async, PostgreSQL | 8000 |
| web | Browser UX and admin workflows over backend contracts | Next.js 16, React 19, TypeScript | 3000 |
| mobile | Native UX and app interactions over backend contracts | Flutter, Dart, BLoC, Dio/Retrofit | N/A |

## Shared Infrastructure
- PostgreSQL (Supabase managed and local Docker)
- Supabase Auth and Storage
- Firebase Cloud Messaging
- Sentry monitoring
- Render backend hosting blueprint
- Vercel web deployment pipeline
- GitHub Actions CI/CD workflows
- Pulumi IaC skeleton (partially implemented)

## Knowledge Indexes
- Contracts: docs/contracts/README.md
- Operations: docs/ops/README.md
- Decisions: docs/decisions/README.md
- Flutter Lessons: docs/guides/flutter-lessons.md
- Architecture Overview: docs/architecture/overview.md
- Documentation Index: docs/README.md

## Key Global Commands
- Local infra: docker compose up -d pgdb pgadmin
- Backend dev: cd backend && .venv/bin/uvicorn app.main:app --reload
- Backend test: cd backend && .venv/bin/pytest
- Backend migrate: cd backend && .venv/bin/alembic upgrade head
- Web dev: cd web && pnpm dev
- Web quality: cd web && pnpm type-check && pnpm lint
- Mobile dev: cd mobile && flutter run
- Mobile quality: cd mobile && flutter test && dart analyze .

## Known Pain Points
- Multiple Prompt 2 TODO scaffolds still exist across mobile, infra, and helper scripts.
- Pulumi resources are currently stubs, which can create deployment drift.
- In-process event dispatcher lacks durable delivery guarantees.
- Web testing harness appears less complete than backend/mobile test posture.
- Some contract assumptions changed over time and require regular docs/contracts sync checks.
