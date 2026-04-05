# ADR-001: DDD + CQRS + Hexagonal Backend Architecture

## Status
Accepted

## Context
The backend needs to evolve quickly while preserving domain correctness for genealogy rules, RBAC, and clan isolation.
Directly coupling API handlers, persistence logic, and business rules increases regression risk.

## Decision
Adopt a layered architecture with:
- Domain layer for pure business concepts and invariants
- Application layer for command/query orchestration
- Infrastructure adapters for persistence and external services
- Thin API controllers for transport concerns
- Unit of Work + domain events for transactional consistency and audit integration

## Consequences
Easier:
- reasoning about domain rules
- testing core logic independently
- replacing infrastructure adapters over time

Harder:
- more files and boilerplate per feature
- stricter import boundaries require discipline and tooling
