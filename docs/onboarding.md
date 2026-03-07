# Developer Onboarding Guide

Welcome to **FamilyRoots**! This guide will help you set up your local development environment.

## Prerequisites

| Tool      | Version  | Install                                       |
|-----------|----------|-----------------------------------------------|
| Python    | ≥ 3.12   | [python.org](https://python.org)              |
| uv        | latest   | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Flutter   | ≥ 3.x    | [flutter.dev](https://flutter.dev/docs/get-started/install) |
| Docker    | latest   | [docker.com](https://docker.com)              |
| Git       | latest   | [git-scm.com](https://git-scm.com)           |

## 1. Clone the Repository

```bash
git clone https://github.com/your-org/familyroots.git
cd familyroots
```

## 2. Backend Setup

```bash
cd backend

# Create .env from template
cp .env.example .env
# Edit .env with your local settings

# Install Python dependencies
uv sync

# Start database
docker compose up db -d

# Run migrations
uv run alembic upgrade head

# Start the API server
uv run uvicorn app.main:app --reload --port 8000
```

Verify: Open http://localhost:8000/docs to see the Swagger UI.

## 3. Mobile App Setup

```bash
cd mobile

# Create .env from template
cp .env.example .env

# Generate Flutter platform directories (first time only)
flutter create --org com.familyroots --project-name familyroots .

# Get dependencies (shared package + mobile)
cd ../packages/family_roots_core && flutter pub get
cd ../../mobile && flutter pub get

# Run code generation
flutter pub run build_runner build --delete-conflicting-outputs

# Run the app
flutter run
```

## 4. Web App Setup

```bash
cd web

# Create .env from template
cp .env.example .env

# Generate Flutter web project (first time only)
flutter create --org com.familyroots --project-name familyroots_web --platforms web .

# Get dependencies
cd ../packages/family_roots_core && flutter pub get
cd ../../web && flutter pub get

# Run code generation
flutter pub run build_runner build --delete-conflicting-outputs

# Run the web app
flutter run -d chrome
```

## 5. Docker Compose (Full Stack)

```bash
# Start everything
docker compose up -d

# Services:
#   - Backend API: http://localhost:8000
#   - pgAdmin:     http://localhost:5050
#   - PostgreSQL:   localhost:5432
```

## 6. Pre-commit Hooks

```bash
# Install pre-commit hooks
pip install pre-commit
pre-commit install

# Or use the Makefile
make pre-commit-install
```

## 7. Useful Makefile Commands

```bash
make backend-dev       # Start backend dev server
make backend-test      # Run backend tests
make backend-lint      # Lint backend code
make mobile-run        # Run mobile app
make web-run           # Run web app
make docker-up         # Start Docker services
make docker-down       # Stop Docker services
```

## Project Structure

```
familyroots/
├── backend/           # FastAPI backend (Python)
├── mobile/            # Flutter mobile app (Dart)
├── web/               # Flutter web app (Dart)
├── packages/          # Shared Dart packages
├── infra/             # Infrastructure as Code
├── docs/              # Documentation
├── scripts/           # Utility scripts
└── docker-compose.yml # Local orchestration
```

## Code Style

- **Python**: ruff (linter + formatter), mypy (type checker)
- **Dart**: flutter analyze, dart format
- **Commits**: Conventional Commits (`feat:`, `fix:`, `docs:`, etc.)
- **Branches**: `main` (production), `develop` (integration), `feat/*`, `fix/*`

## Getting Help

- Check the [Architecture docs](architecture.md) for system overview
- Review [API Design](api-design.md) for endpoint specs
- See [Tenant Design](tenant-design.md) for multi-tenancy details
- Read [RBAC](rbac.md) for permissions model
