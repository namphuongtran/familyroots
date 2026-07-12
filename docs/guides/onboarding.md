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
docker compose up pgdb -d

# Run migrations
uv run alembic upgrade head

# Start the API server
uv run uvicorn app.main:app --reload --port 8000
```

Verify: Open http://localhost:8000/docs to see the Swagger UI.

### Running backend integration tests

Integration tests require a local Postgres (`docker compose up -d pgdb`).
`tests/integration/conftest.py` drops/creates a throwaway database
`family_roots_schema_test` and applies the full Alembic chain. Override the
admin DSN via `TEST_PG_ADMIN_URL` (default
`postgresql+psycopg://postgres:postgres@localhost:5432/postgres`).

```bash
cd backend
uv run pytest -m integration   # integration tests only
uv run pytest                  # full suite
```

## 3. Mobile App Setup

```bash
cd mobile

# Create .env from template
cp .env.example .env

# Generate Flutter platform directories (first time only)
flutter create --org com.familyroots --project-name familyroots .

# Get dependencies
flutter pub get

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

# Install dependencies
pnpm install

# Run the web app
pnpm dev
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
make web-dev           # Run web app
make docker-up         # Start Docker services
make docker-down       # Stop Docker services
```

## Project Structure

```
familyroots/
├── backend/           # FastAPI backend (Python)
├── mobile/            # Flutter mobile app (Dart)
├── web/               # Next.js web app (React, TypeScript)
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

## 8. SSO Configuration (Google + Apple)

### Google OAuth Setup

1. Go to **Supabase Dashboard → Authentication → Providers → Google**
2. Enable the Google provider
3. Create **OAuth 2.0 credentials** in [Google Cloud Console](https://console.cloud.google.com/)
   - Application type: Web application (for web) + iOS/Android (for mobile)
4. Set **Authorized redirect URI**: `https://<your-project>.supabase.co/auth/v1/callback`
5. Paste **Client ID** and **Client Secret** into Supabase
6. Add `GOOGLE_CLIENT_ID` and `GOOGLE_SERVER_CLIENT_ID` to `mobile/.env` and `web/.env`

### Apple Sign In Setup

> **Apple App Store Policy:** If an iOS/macOS app offers any third-party social login
> (including Google), it **must** also offer Apple Sign In.

1. Go to **Supabase Dashboard → Authentication → Providers → Apple**
2. Enable the Apple provider
3. In [Apple Developer Portal](https://developer.apple.com/):
   - Create an **App ID** with "Sign In with Apple" capability
   - Create a **Service ID** (for web OAuth redirect)
   - Generate a **private key** (`.p8` file)
4. Paste **Team ID**, **Key ID**, **Service ID**, and **private key content** into Supabase
5. For iOS: Add "Sign In with Apple" capability in Xcode project settings
6. For web: Configure the return URL in Apple Developer Portal

### Platform Super Admin Bootstrap

The super admin account is created **once** via CLI script (never via API):

```bash
cd backend
export SUPABASE_URL=https://xxxx.supabase.co
export SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
uv run python ../scripts/bootstrap_super_admin.py
```

> ⚠️ This script can only be run once. Store the credentials securely.

## Getting Help

- Check the [Architecture docs](../architecture/overview.md) for system overview
- Review [API Design](../architecture/api-design.md) for endpoint specs
- See [Data Isolation Design](../architecture/multi-tenancy.md) for clan_id + RLS approach
- Read [RBAC](../architecture/rbac.md) for permissions model
