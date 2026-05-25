# FamilyRoots 🌳

A cross-platform genealogy app for Vietnamese family clans. Members can view and edit their family tree, manage member profiles, upload photos and documents, and receive push notifications for death anniversaries and birthdays. The project ships a **Flutter mobile app** (Android + iOS) and a **Next.js web dashboard** (admin panel + backoffice). Users can belong to multiple clans and switch between them (like Slack workspaces).

## Key Features

- **Multi-clan workspaces** — join several family clans, switch context instantly
- **Interactive family tree** — visualize lineage with XYFlow (React Flow)
- **Fuzzy Vietnamese name search** — PostgreSQL trigram + unaccent
- **Role-based access control** — viewer / editor / admin per clan
- **Audit logging** — every mutation tracked (actor, action, old/new values)
- **Push notifications** — Firebase FCM with cron-based anniversary & birthday reminders
- **Multilingual** — Vietnamese, English, Chinese, French (vi / en / zh / fr)
- **Relationship validation** — business rules for marriages, parent-child links
- **Soft deletes** — data preserved with `is_deleted` flag
- **Row-Level Security** — clan data isolation enforced at the database engine level

## Tech Stack

| Layer              | Technology                                       |
|--------------------|--------------------------------------------------|
| Mobile Frontend    | Flutter (Dart) — Android + iOS                   |
| Web Frontend       | Next.js 16 (React 19, TypeScript)                |
| Backend API        | FastAPI (Python 3.14+)                           |
| Database           | PostgreSQL 18 via Supabase                       |
| Auth               | Supabase Auth (JWT + Google / Apple SSO)         |
| File Storage       | Supabase Storage                                 |
| State Management   | Zustand (web) · Flutter BLoC (mobile)            |
| Tree Visualization | XYFlow / React Flow (web)                        |
| Push Notifications | Firebase Cloud Messaging (FCM)                   |
| Scheduling         | APScheduler (cron-based reminder jobs)           |
| Backend Deploy     | Render.com (Docker)                              |
| Web Deploy         | Vercel                                           |
| CI/CD              | GitHub Actions (5 workflows)                     |
| IaC                | Pulumi (Python)                                  |
| Monitoring         | Sentry                                           |
| Package Managers   | uv (backend) · pnpm (web) · pub (mobile)         |

## Monorepo Structure

```
family-roots/
├── .github/          # CI/CD workflows (backend-ci, mobile-ci, web-ci, pr-checks, infra-ci)
├── backend/          # FastAPI Python service (pure REST API)
├── mobile/           # Flutter app — Android + iOS + Tablet
├── web/              # Next.js web app — Dashboard + Admin Panel + Backoffice
├── infra/            # Infrastructure as Code (Pulumi, Render, Supabase, Firebase)
├── docs/             # Architecture docs, guides, ADRs
├── scripts/          # Utility scripts (seeding, export, super admin bootstrap)
├── docker-compose.yml
├── Makefile          # Common dev commands
└── .pre-commit-config.yaml
```

## Data Isolation Model

**Single Schema + clan_id + Row Level Security** — one PostgreSQL instance (Supabase), all tables in a single `public` schema. Every clan-scoped table has a `clan_id UUID NOT NULL` column. Supabase RLS policies enforce data isolation at the database engine level. Users who belong to multiple clans switch context via the `X-Current-Clan-Id` header.

## Quick Start

```bash
# 1. Clone and enter repo
git clone https://github.com/your-org/family-roots.git && cd family-roots

# 2. Install pre-commit hooks
pre-commit install

# 3. Start local infrastructure (PostgreSQL + pgAdmin)
docker compose up -d pgdb pgadmin

# 4. Setup backend (http://localhost:8000)
cd backend
uv sync
cp .env.example .env   # Fill in local values
uvx alembic upgrade head
uv run uvicorn app.main:app --reload

# 5. Setup mobile
cd ../mobile
flutter pub get
flutter run

# 6. Setup web (http://localhost:3000)
cd ../web
pnpm install
pnpm dev
```

Or use the Makefile:

```bash
make docker-up       # Start pgdb + pgadmin
make docker-all      # Start all services (pgdb, api, pgadmin, web)
make backend-dev     # Run backend with hot reload (:8000)
make mobile-run      # Run mobile app
make web-dev         # Run Next.js web app (:3000)
```

See [docs/guides/onboarding.md](docs/guides/onboarding.md) for the full developer setup guide.

## Documentation

Start at [docs/README.md](docs/README.md) for the full index. Quick links:

- [Architecture Overview](docs/architecture/overview.md)
- [API Design](docs/architecture/api-design.md)
- [Data Model](docs/architecture/data-model.md)
- [RBAC Design](docs/architecture/rbac.md)
- [Multi-Tenancy Design](docs/architecture/multi-tenancy.md)
- [Developer Onboarding](docs/guides/onboarding.md)
- [Infrastructure as Code Guide](docs/guides/iac-guide.md)
- [Flutter Build & Publish](docs/guides/flutter-build-publish.md)

## Branch Strategy

| Branch | Purpose |
|--------|---------|
| `main` | Production-ready, protected |
| `develop` | Integration branch |
| `feature/{ticket}-desc` | Feature work |
| `fix/{ticket}-desc` | Bug fixes |
| `chore/desc` | Maintenance |
| `infra/desc` | Infrastructure changes |

## Commit Convention

[Conventional Commits](https://www.conventionalcommits.org/) — enforced in CI.

```
feat(members): add profile photo upload endpoint
fix(tree): resolve infinite loop in recursive query
chore(ci): update Flutter to 3.24 stable
infra(pulumi): add Vercel domain binding for production
```

## License

Apache License 2.0 — see [LICENSE](LICENSE).
