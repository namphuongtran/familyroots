# Contracts Index

This folder is the canonical home for public API and event contract documentation.

## Rules
- One file per public contract surface.
- Every contract file must state owner, consumers, schema, and versioning rules.
- Additive changes are preferred.
- Breaking changes must be paired with a migration strategy and an ADR.
- Keep these docs aligned with backend routes and client expectations.

## Current Contracts
- [rest-auth-api.md](rest-auth-api.md)
- [rest-me-api.md](rest-me-api.md)
- [rest-clans-api.md](rest-clans-api.md)
- [rest-persons-api.md](rest-persons-api.md)
- [rest-relationships-api.md](rest-relationships-api.md)
- [rest-tree-api.md](rest-tree-api.md)
- [rest-documents-api.md](rest-documents-api.md)
- [rest-events-api.md](rest-events-api.md)
- [rest-claims-api.md](rest-claims-api.md)
- [rest-platform-admin-api.md](rest-platform-admin-api.md)
- [rest-notifications-api.md](rest-notifications-api.md)
- [domain-events-audit.md](domain-events-audit.md)
- [domain-events-catalog.md](domain-events-catalog.md)
- [redis-domain-events.md](redis-domain-events.md)

## Maintenance Notes
- Keep route names consistent with backend router prefixes.
- Update consumers when a contract changes.
- Add versioned files if a breaking API branch is introduced.
