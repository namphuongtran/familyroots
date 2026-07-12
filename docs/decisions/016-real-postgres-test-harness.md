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
the docker-compose `pgdb`.

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
