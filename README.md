# FamilyRoots 🌳

A cross-platform genealogy app for Vietnamese family clans. Members can view/edit their family tree, manage member profiles, upload photos/documents, and receive notifications for death anniversaries and birthdays. Users can belong to multiple clans and switch between them (like Slack workspaces).

## Tech Stack

| Layer              | Technology                        |
|--------------------|-----------------------------------|
| Mobile Frontend    | Flutter (Dart) — Android + iOS    |
| Web Frontend       | Flutter Web (Dart) + Admin Panel  |
| Backend API        | FastAPI (Python 3.12+)            |
| Database           | PostgreSQL via Supabase           |
| Auth               | Supabase Auth (JWT + Google OAuth)|
| File Storage       | Supabase Storage                  |
| Push Notifications | Firebase Cloud Messaging (FCM)    |
| Backend Deploy     | Render.com                        |
| Web Deploy         | Vercel                            |
| CI/CD              | GitHub Actions                    |
| IaC                | Pulumi (Python)                   |
| Monitoring         | Sentry                            |

## Monorepo Structure

```
family-roots/
├── .github/          # CI/CD workflows, PR templates
├── backend/          # FastAPI Python service (pure REST API)
├── mobile/           # Flutter app — Android + iOS + Tablet
├── web/              # Flutter Web app — Browser + Admin Panel
├── packages/         # Shared Dart packages (used by mobile + web)
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

# 3. Start local infrastructure
docker compose up -d db pgadmin

# 4. Setup backend
cd backend
uv sync
cp .env.example .env   # Fill in local values
uvx alembic upgrade head
uv run uvicorn app.main:app --reload

# 5. Setup mobile
cd ../mobile
flutter pub get
flutter run

# 6. Setup web
cd ../web
flutter pub get
flutter run -d chrome
```

Or use the Makefile:

```bash
make docker-up       # Start local infra
make backend-dev     # Run backend with hot reload
make mobile-run      # Run mobile app
make web-run         # Run web app in Chrome
```

See [docs/onboarding.md](docs/onboarding.md) for the full developer setup guide.

## Documentation

- [Architecture Overview](docs/architecture.md)
- [Data Isolation Design](docs/tenant-design.md)
- [Infrastructure as Code Guide](docs/iac-guide.md)
- [Developer Onboarding](docs/onboarding.md)
- [API Design](docs/api-design.md) *(Prompt 2)*
- [Database Schema](docs/database-schema.md) *(Prompt 2)*
- [RBAC Design](docs/rbac.md) *(Prompt 2)*

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
