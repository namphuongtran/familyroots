# ADR-032: Transient DB Operational Failures Surface as 503, Not 500

## Status
Accepted (2026-08-01).

## Context

A mid-request database failure that is **not under the application's control** — a
dropped/severed connection, connection-pool exhaustion, a Postgres restart or admin
shutdown, or resource exhaustion (too many connections, out of memory, disk full) —
raises a SQLAlchemy `OperationalError` (the DBAPI class defined for exactly these
"operational, not the programmer's fault" errors). The first chokepoint is
`get_current_user`'s `db.scalar` (`app/core/security.py`), then every repository query.

Before this ADR, nothing mapped `OperationalError`, so it fell to the catch-all
`unhandled_exception_handler` → an opaque **`500 internal_error`**. That is wrong on two
counts:

- **It misleads clients.** A `500` reads as "server bug, don't bother retrying / file a
  report"; the truth is "the datastore is briefly unavailable, retry with backoff." The
  native mobile client and any SDK treat 500 and 503 very differently.
- **It is inconsistent with our own readiness signal.** `/health` already reports
  `degraded` on a DB failure (`app/main.py`), and the storage- and identity-provider
  outage paths already return a truthful `503` (`storage_unavailable`,
  `auth_provider_unavailable`). A DB outage being a 500 was the odd one out.

## Decision

**Register a handler mapping SQLAlchemy `OperationalError` → `503 database_unavailable`.**

- Only `OperationalError` routes to 503 — it is the DBAPI class for
  infrastructural/transient failures. `ProgrammingError`, `DataError`, and other
  `DatabaseError` subclasses indicate an application bug (malformed SQL, type mismatch)
  and deliberately **stay `500 internal_error`** via the catch-all, so a real defect is
  still loud.
- `OperationalError` is a **sibling** of `IntegrityError` under `DBAPIError` (neither is
  an ancestor of the other), so this registration never shadows the existing
  `IntegrityError → 409/500` mapping. Starlette resolves handlers by the exception's MRO,
  so an `OperationalError` instance matches this handler over the catch-all `Exception`.
- The raw DBAPI message (which can contain host/DSN fragments) is **logged**, never
  returned; the client gets the stable `{"error": {"code": "database_unavailable", ...}}`
  envelope with a localized message (en/vi/zh/fr).
- New public error code `database_unavailable` (503), documented in
  `docs/contracts/error-codes.md`.

## Consequences

- Clients get a retry-able, truthful status for a brief datastore blip instead of a
  misleading bug signal; per-request behavior now matches `/health`'s `degraded`.
- A pathological-but-our-fault slow query cancelled by `statement_timeout` surfaces as
  `OperationalError` (SQLSTATE 57014) and will read as 503 rather than 500. Accepted:
  the DB protecting itself is a "try again / shed load" condition, and repeated 503s
  remain visible in monitoring — it does not hide the perf problem, it just labels it
  honestly.
- No schema change, no migration. One handler + one error code + i18n; pinned by
  `tests/unit/test_database_unavailable_handler.py` (direct-envelope, registration, and
  an end-to-end route-injection test proving MRO routing over the catch-all).

## Alternatives considered

- **Keep 500.** Rejected: misleading to retryable clients and inconsistent with
  `/health` and the storage/identity 503s.
- **Map all `DBAPIError`/`DatabaseError` → 503.** Rejected: that would sweep
  `ProgrammingError`/`DataError` (genuine application bugs) into a soft "try again",
  hiding defects. The mapping is deliberately narrowed to the operational class.
- **Per-SQLSTATE allow-list** (class 08 connection, 57P0x shutdown, 53xxx resources).
  Rejected as unnecessary precision: `OperationalError` already *is* the DBAPI-level
  partition of "operational vs programmer error," so keying on the exception class is
  simpler and equivalent in practice.
