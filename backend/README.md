# Backend — FamilyRoots API

FastAPI-based REST API service for the FamilyRoots genealogy platform.

## Tech Stack

- **Framework**: FastAPI (Python 3.12+)
- **Database**: PostgreSQL via Supabase (async SQLAlchemy + asyncpg)
- **Auth**: Supabase Auth (JWT validation)
- **Storage**: Supabase Storage
- **Notifications**: Firebase Cloud Messaging
- **Package Manager**: uv

## Project Structure

```
backend/
├── app/
│   ├── api/v1/          # API route handlers (versioned)
│   ├── core/            # Config, database, security
│   ├── models/          # SQLAlchemy ORM models
│   ├── schemas/         # Pydantic v2 request/response schemas
│   ├── services/        # Business logic layer
│   ├── middleware/       # Custom middleware (language, sentry)
│   └── main.py          # App factory, lifespan, middleware setup
├── migrations/          # Alembic migrations (single schema)
├── tests/               # pytest test suite
├── pyproject.toml       # Dependencies (uv-managed)
├── Dockerfile           # Production container (uses uv)
└── alembic.ini          # Alembic configuration
```

## Setup

```bash
# Install dependencies
uv sync

# Copy env file and fill in values
cp .env.example .env

# Run migrations
uvx alembic upgrade head

# Start dev server
uv run uvicorn app.main:app --reload
```

## Commands

```bash
uv sync                     # Install/sync dependencies
uv add <package>            # Add a dependency
uv add --dev <package>      # Add a dev dependency
uv run pytest               # Run tests
uvx ruff check .            # Lint
uvx ruff format .           # Format
uvx mypy app/               # Type check
uvx alembic revision --autogenerate -m "description"  # Create migration
uvx alembic upgrade head    # Apply migrations
```
