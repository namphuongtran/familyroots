.PHONY: help docker-up docker-down backend-dev backend-test backend-lint \
       supabase-up supabase-down supabase-env \
       mobile-run mobile-test web-dev web-build web-lint web-type-check \
       infra-preview infra-up migrate seed

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
migrate: ## Run Alembic migrations
	cd backend && uvx alembic upgrade head

seed: ## Seed development data
	cd backend && uv run python ../scripts/seed_dev_data.py

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
