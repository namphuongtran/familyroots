# Repository Guidelines

## Project Structure & Module Organization
`familyroots` is a monorepo with product apps and infrastructure side by side. Use `backend/` for the FastAPI API (`app/`, `migrations/`, `tests/`), `web/` for the Next.js App Router frontend (`src/app`, `src/application`, `src/domain`, `src/infrastructure`), and `mobile/` for the Flutter app (`lib/features`, `lib/core`, `test/`, `assets/`). Shared docs live in `docs/`, automation scripts in `scripts/`, and deployment code in `infra/pulumi/`.

## Build, Test, and Development Commands
Prefer the top-level `Makefile` for common tasks:

- `make docker-up`: start local PostgreSQL and pgAdmin.
- `make backend-dev`: run FastAPI with reload on `:8000`.
- `make web-dev`: run Next.js locally on `:3000`.
- `make mobile-run`: launch the Flutter app on a connected device/emulator.
- `make backend-test`: run `pytest` with coverage for `backend/tests/`.
- `make web-lint` and `make web-type-check`: validate the web app.
- `make mobile-test` and `make mobile-analyze`: verify Flutter code.
- `make pre-commit-run`: run repo hooks before pushing.

## Coding Style & Naming Conventions
Python uses Ruff, MyPy, and a 100-character line length; keep imports sorted and type hints strict. TypeScript uses ESLint + Prettier; place route code under `web/src/app` and keep domain/application/infrastructure layers separated. Dart follows `flutter_lints` with `prefer_single_quotes`, `avoid_print`, and `prefer_final_locals`. Match existing naming: `snake_case` for Python modules, `kebab-case` for branch names, and descriptive feature folders such as `mobile/lib/features/members/`.

## Testing Guidelines
Backend tests use `pytest` with markers like `unit`, `integration`, and `slow`; name files `test_*.py`. Flutter tests live under `mobile/test` and run with `flutter test`. The web app currently emphasizes lint and type-check gates; add targeted tests when introducing non-trivial behavior. For backend changes, keep coverage intact by running `make backend-test`.

## Commit & Pull Request Guidelines
Commits follow Conventional Commits with optional scopes, as seen in history: `feat(workflow): ...`, `refactor(mobile): ...`, `chore(ci): ...`. Keep messages imperative and scoped to one change. PRs should include a short summary, linked issue or task, affected areas (`backend`, `web`, `mobile`, `infra`), and screenshots for UI changes. Call out schema, env, or migration impacts explicitly.

## Security & Configuration Tips
Do not commit secrets; copy from `.env.example` files and rely on `gitleaks` plus pre-commit hooks. If you change infra or auth-related settings, update the relevant docs in `docs/ops/` or service README files in the same change.
