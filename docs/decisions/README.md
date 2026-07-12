# ADR Index

| ADR | Title | Status |
|-----|-------|--------|
| [001](001-ddd-cqrs-hexagonal.md) | DDD + CQRS + Hexagonal Backend Architecture | Accepted, shipped |
| [002](002-clan-scoped-multitenancy.md) | Single Schema Clan-Scoped Multitenancy | Accepted, shipped (app-layer isolation) |
| [003](003-rest-first-client-contract.md) | REST-First Cross-Client Contract Strategy | Accepted, shipped |
| [004](004-redis-pubsub-events.md) | Redis for Distributed Domain Events | **Deferred — not built** (in-process dispatcher today, see ADR-014) |
| [005](005-dedicated-export-worker.md) | Dedicated Worker Service for Heavy Exports | **Deferred — not built** |
| [006](006-soft-vs-hard-delete.md) | Selective Soft-Delete by Aggregate | Accepted, shipped (edge-cascade on roadmap) |
| [007](007-identity-claims-workflow.md) | Identity Claims Workflow | Accepted, shipped |
| [008](008-rls-defense-in-depth.md) | Row-Level Security as Defense-in-Depth Layer-2 | Accepted, **pilot only — inert at runtime** |
| [009](009-clan-deletion-restrict.md) | Clan Deletion Is RESTRICT-Guarded | Accepted, shipped |
| [010](010-response-envelope-cursor-pagination.md) | Canonical Success Envelope + Cursor-Only Pagination | Accepted, shipped |
| [011](011-historical-date-precision.md) | HistoricalDate — Precision Model Replaces `*_approx` | Accepted, shipped |
| [012](012-computed-generation-mother-attribution.md) | Graph-Computed đời + Derived Mother Attribution | Accepted, shipped |
| [013](013-import-linter-boundary-ratchet.md) | Machine-Enforced Boundaries (import-linter + Ratchet) | Accepted, shipped |
| [014](014-uow-in-transaction-domain-events.md) | UoW In-Transaction Domain-Event Dispatch (Audit) | Accepted, shipped |
| [015](015-email-verification-flow.md) | Email Verification Flow | Accepted, shipped |
| [016](016-real-postgres-test-harness.md) | Real-Postgres Integration Test Harness | Accepted, shipped |
| [017](017-optimistic-concurrency.md) | Required Optimistic Concurrency Control on Genealogy Writes | Accepted, shipped |

When adding ADRs, use sequential numbering and keep prior ADRs immutable except for
Status updates. **Any breaking API contract change or new load-bearing architectural
decision must land with an ADR in the same PR** (see `docs/contracts/README.md` rules).
