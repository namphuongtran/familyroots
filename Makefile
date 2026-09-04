.PHONY: help docker-up docker-down backend-dev backend-test backend-lint \
       supabase-up supabase-down supabase-env \
       mobile-run mobile-test web-dev web-build web-lint web-type-check \
       infra-preview infra-up migrate seed seed-verify

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ─── Docker ────────────────────────────────────────────────────────────
docker-up: ## Start local infrastructure (pgdb + pgadmin)
	docker compose up -d pgdb pgadmin

docker-down: ## Stop all containers
	docker compose down

docker-all: ## Start all services including backend
	docker compose up -d

# ─── Supabase (auth + Storage), a SEPARATE stack from docker-compose ──
# Two databases on purpose: pgdb is the application database Alembic migrates, the
# Supabase stack owns auth.* and Storage. See docs/ops/local-supabase.md.
supabase-up: ## Start the local Supabase stack (auth + Storage) and wait for health
	scripts/supabase_local.sh up

supabase-down: ## Stop the local Supabase stack, keeping its database
	scripts/supabase_local.sh down

supabase-env: ## Print SUPABASE_URL / ANON / SERVICE_ROLE for the local stack
	scripts/supabase_local.sh env

# ─── Backend ───────────────────────────────────────────────────────────
backend-dev: ## Run backend with hot reload
	cd backend && uv run uvicorn app.main:app --reload --port 8000

backend-test: ## Run backend tests with coverage
	cd backend && uv run pytest tests/ --cov=app --cov-report=term-missing

backend-lint: ## Lint and type-check backend
	cd backend && uvx ruff check . && uvx ruff format --check . && uvx mypy app/

backend-format: ## Auto-format backend code
	cd backend && uvx ruff format . && uvx ruff check --fix .

# ─── Mobile ────────────────────────────────────────────────────────────
mobile-run: ## Run mobile app (default device)
	cd mobile && flutter run

mobile-test: ## Run mobile tests
	cd mobile && flutter test

mobile-analyze: ## Analyze mobile code
	cd mobile && flutter analyze

# ─── Web (Next.js) ─────────────────────────────────────────────────────────
web-dev: ## Run Next.js web app in dev mode
	cd web && pnpm dev

web-build: ## Build web for production
	cd web && pnpm build

web-lint: ## Lint web code
	cd web && pnpm lint

web-type-check: ## Type-check web code
	cd web && pnpm type-check

# ─── Infrastructure ───────────────────────────────────────────────────
infra-preview: ## Preview infrastructure changes
	cd infra/pulumi && pulumi preview

infra-up: ## Apply infrastructure changes
	cd infra/pulumi && pulumi up

# ─── Database ─────────────────────────────────────────────────────────
migrate: ## Run Alembic migrations against the application database
# `uv run`, not `uvx`: alembic needs the project virtualenv to import app.core.config
# and the models package (backend/CLAUDE.md). A bare `uvx alembic` fails to import them.
	cd backend && uv run alembic upgrade head

# The environment both seed targets need, resolved once. Two rules, and both matter.
# What the caller exported WINS: `SUPABASE_SERVICE_ROLE_KEY=... make seed` never shells
# out. And scripts/supabase_local.sh is asked only for what is missing, because
# `supabase status` refuses to print anything while any container reports unhealthy --
# including a container that is transiently unhealthy and answering queries normally
# (measured 2026-08-22 on supabase_db_familyroots, "Health check exceeded timeout (2s)").
SEED_ENV = set -e; \
	  export DATABASE_URL="$${DATABASE_URL:-postgresql+psycopg://postgres:postgres@localhost:5432/family_roots}"; \
	  if [ -z "$${SUPABASE_URL:-}" ] || [ -z "$${SUPABASE_SERVICE_ROLE_KEY:-}" ]; then \
	    eval "$$(scripts/supabase_local.sh env | sed 's/^/export /')"; \
	  fi; \
	  [ -n "$${SUPABASE_SERVICE_ROLE_KEY:-}" ] || { echo "make: no SUPABASE_SERVICE_ROLE_KEY. Start the stack with 'make supabase-up', or export the key yourself." >&2; exit 2; }

seed: ## Seed BOTH databases from empty: a test clan, four users, their roles
# One command, and it covers both halves of a test user. Needs `make docker-up` and
# `make supabase-up` first. A user's identity lives in the Supabase stack's auth.users and
# the membership lives in the application database, so seeding one without the other
# leaves a user who logs in and can reach nothing. See docs/ops/seed-test-users.md.
#
# DATABASE_URL is taken from the environment when set, and otherwise defaults to
# docker-compose.yml's pgdb credentials. backend/.env is NOT read here: the seeder takes
# plain environment variables only, so that what it targets is visible in the command.
	@$(SEED_ENV); \
	  cd backend && uv run alembic upgrade head && uv run python ../scripts/seed_dev_data.py apply

seed-verify: ## Check that the two halves of every seeded test user agree
	@$(SEED_ENV); \
	  cd backend && uv run python ../scripts/seed_dev_data.py verify

# ─── Packages ─────────────────────────────────────────────────────────
packages-get: ## Get dependencies for all projects
	cd mobile && flutter pub get
	cd web && pnpm install

# ─── Pre-commit ───────────────────────────────────────────────────────
pre-commit-install: ## Install pre-commit hooks
	pre-commit install

pre-commit-run: ## Run pre-commit on all files
	pre-commit run --all-files

# ─── Git ──────────────────────────────────────────────────────────────
sync: ## Commit and push all changes to the current branch. Usage: make sync m="type(scope): message"
	@if [ -z "$(m)" ]; then \
		echo "Error: Commit message is required. Usage: make sync m=\"type(scope): message\""; \
		exit 1; \
	fi
	./scripts/git_sync.sh "$(m)"
