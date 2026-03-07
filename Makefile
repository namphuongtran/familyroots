.PHONY: help docker-up docker-down backend-dev backend-test backend-lint \
       mobile-run mobile-test web-run web-test web-build \
       infra-preview infra-up migrate seed

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ─── Docker ────────────────────────────────────────────────────────────
docker-up: ## Start local infrastructure (db + pgadmin)
	docker compose up -d db pgadmin

docker-down: ## Stop all containers
	docker compose down

docker-all: ## Start all services including backend
	docker compose up -d

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

# ─── Web ───────────────────────────────────────────────────────────────
web-run: ## Run web app in Chrome
	cd web && flutter run -d chrome

web-test: ## Run web tests
	cd web && flutter test

web-build: ## Build web for production
	cd web && flutter build web --release

web-analyze: ## Analyze web code
	cd web && flutter analyze

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
packages-get: ## Get dependencies for all Flutter projects
	cd packages/family_roots_core && dart pub get
	cd mobile && flutter pub get
	cd web && flutter pub get

# ─── Pre-commit ───────────────────────────────────────────────────────
pre-commit-install: ## Install pre-commit hooks
	pre-commit install

pre-commit-run: ## Run pre-commit on all files
	pre-commit run --all-files
