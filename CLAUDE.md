# FamilyRoots

## What This System Does
FamilyRoots is a Vietnamese genealogy platform that lets clans maintain accurate family trees across web and mobile clients. It provides role-based collaboration, auditability, multilingual UX, and clan-scoped data isolation so multiple family communities can coexist safely in one platform.

## Current Stage
Growing, with strong architectural foundations and active scaffold-to-build work in selected areas (mobile modules, infra automation, and auxiliary scripts).

## How Work Is Planned Here
Work is tracked as **GitHub issues** on `namphuongtran/familyroots`, through the `gh` CLI.

- **Picking up work:** take an open issue labelled `ready-for-agent`.
- **Milestone order and the reason for each boundary:** docs/roadmap.md. It holds no work.
- **One pull request per issue.** Do not close two issues in one PR unless they are the same change.

## Agent skills

### Issue tracker

Issues live in GitHub Issues on `namphuongtran/familyroots`, via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The five default triage roles, each label string equal to its name. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context. ADRs live in `docs/decisions/`. See `docs/agents/domain.md`.

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
- Public API successes use the canonical envelope: every 2xx body is {"data": ...}; lists add "meta": {cursor, has_more, limit}. Date fields are HistoricalDate objects {date, precision, display, lunar}. docs/contracts/ is the spec.
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
| mobile | Native UX and app interactions over backend contracts | Flutter, Dart, Riverpod 3, Dio | N/A |

## Shared Infrastructure
- PostgreSQL (Supabase managed and local Docker)
- Supabase Auth and Storage
- Firebase Cloud Messaging
- Sentry monitoring
- Render backend hosting blueprint
- Vercel web deployment pipeline
- GitHub Actions CI/CD workflows
- Pulumi IaC skeleton (partially implemented)

## Required Reading Before Each Task
Start every task by reading the docs that own the surface being touched (full map in docs/README.md):
- Any API request/response change → docs/contracts/README.md (envelope + HistoricalDate rules) + the matching docs/contracts/rest-*.md. Update the contract file in the same PR.
- DB schema or migration → docs/architecture/data-model.md + docs/ops/migrations.md.
- Tree / đời / kinship / đa thê → docs/architecture/tree-read-model.md + docs/architecture/domain-rules.md.
- Auth / login / roles / clan context → docs/architecture/auth-flow.md + docs/architecture/rbac.md + docs/architecture/multi-tenancy.md.
- Any architectural choice or breaking change → docs/decisions/README.md (ADR index); add a new ADR in the same PR.
- Deploy / infra / incident → docs/ops/README.md.
When code and docs disagree, the code is the truth — fix the doc in the same PR.

## Knowledge Indexes
- Documentation Index (start here): docs/README.md
- Contracts: docs/contracts/README.md
- Decisions (ADRs): docs/decisions/README.md
- Operations: docs/ops/README.md
- Architecture Overview: docs/architecture/overview.md
- Flutter Lessons: docs/guides/flutter-lessons.md

## Key Global Commands
- Local infra: docker compose up -d pgdb pgadmin
- Backend dev: cd backend && uv run uvicorn app.main:app --reload
- Backend test: cd backend && uv run pytest
- Backend migrate: cd backend && uv run alembic upgrade head
- Backend full quality gate (run before claiming done): cd backend && uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports
- Web dev: cd web && pnpm dev
- Web quality: cd web && pnpm type-check && pnpm lint
- Mobile dev: cd mobile && flutter run (secrets via --dart-define; see mobile/CLAUDE.md)
- Mobile full quality gate (run before claiming done): cd mobile && dart format --set-exit-if-changed lib test && dart run build_runner build && git diff --exit-code && flutter analyze && flutter test

## Known Pain Points
- Prompt 2 TODO scaffolds remain in infra and helper scripts (mobile's were deleted by the ADR-034 rebuild).
- Mobile M0 has never run on a device: it compiles and CI builds an APK, but Supabase/Sentry init needs platform channels, so login against real Supabase is unverified.
- Pulumi resources are currently stubs, which can create deployment drift.
- In-process event dispatcher lacks durable delivery guarantees.
- Web testing harness appears less complete than backend/mobile test posture.
- Some contract assumptions changed over time and require regular docs/contracts sync checks.
