# ADR-016: Real-Postgres, Migration-Based Integration Test Harness

## Status
Accepted (shipped — `backend/tests/integration/`)

## Context
The riskiest behavior in this system — clan isolation, recursive SQL tree functions,
RLS pilot, migration correctness — lives in Postgres features (partial unique
indexes, recursive CTEs, `SECURITY INVOKER` functions, GUC policies) that SQLite or
mocks cannot exercise. Mock-based tests were passing while real queries were wrong.

## Decision
Integration tests run against a **real Postgres**: a session-scoped fixture
(`migrated_db_url`) drops/creates a throwaway `family_roots_schema_test` database and
applies the **full Alembic chain** (the same migrations production runs), then tests
exercise real sessions. `TEST_PG_ADMIN_URL` overrides the admin DSN; local default is
the docker-compose `pgdb`. `TEST_PG_DB_NAME` overrides the database *name* (default
`family_roots_schema_test`) — required for concurrent suites, see Consequences.

Discipline that goes with it:
- **Two-sided isolation tests** — assert clan A sees its rows AND clan B does not.
- **Sabotage-verified negative controls** — prove a test would fail if the guard
  were removed, so green means something.
- Schema drift gate — autogenerate against the migrated DB must produce no diff.

## Consequences
Easier: migrations, SQL functions, indexes, and isolation are tested as deployed;
refactors of repository SQL are safe to verify.
Harder: tests need a running Postgres (`docker compose up -d pgdb`); the suite is
slower than pure-mock; CI must provision a database.

**One throwaway database per concurrent run.** Teardown is `DROP DATABASE … WITH
(FORCE)`, which terminates other backends' connections, so the name is effectively a
lock on the whole Postgres instance: two suites sharing it wipe each other's schema
mid-run. Measured on 2026-08-03 against `tests/integration` (465 tests): two
simultaneous runs on the same name produced 4 failed / 2 errors and 116 failed /
18 errors; the same two runs with distinct `TEST_PG_DB_NAME` values were 465 passed
each. Anything that may overlap another suite — a second agent in another worktree, a
developer alongside CI — must set `TEST_PG_DB_NAME`. It stays an env var rather than a
per-run random suffix so a crashed run leaves one predictable database to clean up
instead of an unbounded set of orphans.
