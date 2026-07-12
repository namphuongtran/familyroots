# ADR-013: Machine-Enforced Hexagonal Boundaries (import-linter + Ratchet)

## Status
Accepted (2026-07 — shipped; application→ORM ratchet fully burned down 2026-07-05)

## Context
ADR-001's layer rules lived only in CLAUDE.md and review comments — violations were
a review catch, not a CI failure, and known debt was invisible.

## Decision
Encode the boundaries as import-linter contracts in `backend/pyproject.toml`
(`uv run lint-imports`, part of the standard quality gate):
- domain imports no outer layers and no frameworks (FastAPI/SQLAlchemy/Pydantic/…);
- application never imports api/infrastructure/ORM models;
- api never imports SQLAlchemy/ORM directly.

Known debt is pinned as **ratchet** contracts via `ignore_imports` lists with one
rule: **the lists may shrink, never grow**. Removing an entry is a cleanup win;
adding one is a CI failure by construction.

## Consequences
Easier: boundary violations fail CI instead of relying on reviewer memory; debt is
explicit, enumerated, and monotonically decreasing.
Harder: new legitimate cross-layer needs must be designed through ports instead of
whitelisted; occasional contract maintenance when modules move.
