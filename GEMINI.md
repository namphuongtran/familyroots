# FamilyRoots — Genealogy Platform for Vietnamese Clans

A comprehensive, cross-platform genealogy system designed specifically for Vietnamese family clans. It features multi-clan workspaces (Slack-style), interactive family trees, fuzzy name search, and strict data isolation via Row-Level Security.

## Project Architecture & Tech Stack

### Core Architecture
- **Monorepo:** Managed with `uv` (backend), `pnpm` (web), and `flutter/pub` (mobile).
- **Backend:** Python 3.14+ / FastAPI following **DDD + CQRS + Hexagonal** architecture.
- **Web:** Next.js 16 (React 19, TypeScript) with **Zustand** and **XYFlow** for tree visualization.
- **Mobile:** Flutter (Dart) using **BLoC** pattern, **Retrofit** for API, and **GetIt** for DI.
- **Infrastructure:** **Supabase** (PostgreSQL 18, Auth, Storage), **Firebase** (FCM), **Pulumi** (IaC), **Render/Vercel** (Hosting).

### Data Isolation & Multitenancy
- **Single Schema + RLS:** Data isolation is enforced at the database level using PostgreSQL Row-Level Security.
- **Clan Context:** Clients must provide the `X-Current-Clan-Id` header to scope requests.

## Development Workflow

### Key Commands (via Root Makefile)
| Category | Command | Description |
| :--- | :--- | :--- |
| **Infrastructure** | `make docker-up` | Start local Postgres + pgAdmin |
| **Backend** | `make backend-dev` | Run FastAPI with hot reload (:8000) |
| | `make backend-test` | Run pytest with coverage |
| | `make backend-lint` | Run Ruff (lint/format) and MyPy |
| | `make migrate` | Run Alembic migrations |
| **Web** | `make web-dev` | Run Next.js in dev mode (:3000) |
| | `make web-type-check` | Run TypeScript compiler check |
| **Mobile** | `make mobile-run` | Run Flutter app on default device |
| | `make mobile-test` | Run Flutter unit/widget tests |
| **General** | `make seed` | Seed development data |

### Backend Conventions
- **Domain Layer:** Must remain framework-agnostic (no FastAPI/SQLAlchemy/Pydantic imports).
- **Application Layer:** Orchestrates domain logic; may import Domain but not Infrastructure.
- **Infrastructure Layer:** Implements persistence (Repositories) and external integrations.
- **Write Operations:** Should flow through a **Unit of Work** and emit domain events.
- **Type Safety:** Strict MyPy checks are enforced. Use `uv run mypy app/` to verify.

### Web & Mobile Conventions
- **Contracts:** API interaction must align with definitions in `docs/contracts/`.
- **State:** Zustand for Web; BLoC for Mobile.
- **Localization:** Supports `vi`, `en`, `zh`, `fr`. Follow established i18n patterns in each service.

## Project Structure
```text
family-roots/
├── backend/          # FastAPI service (DDD/Hexagonal)
├── mobile/           # Flutter app (BLoC/Clean Architecture)
├── web/              # Next.js app (Dashboard/Admin)
├── packages/         # Shared Dart packages (family_roots_core)
├── infra/            # Pulumi IaC and database migrations
├── docs/             # Architecture, ADRs, and API contracts
└── scripts/          # Automation and seeding utilities
```

## Critical Rules & Constraints
- **Security:** Never bypass clan isolation checks. Always validate `clan_id` context.
- **Commits:** Follow [Conventional Commits](https://www.conventionalcommits.org/).
- **Validation:** Always run `make backend-lint`, `make web-type-check`, or `make mobile-analyze` before submitting changes.
- **Documentation:** Architecture decisions are recorded in `docs/decisions/`. Read them before proposing major structural changes.
