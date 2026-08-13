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
| [008](008-rls-defense-in-depth.md) | Row-Level Security as Defense-in-Depth Layer-2 | Accepted, shipped (active for `documents`, `events`, `branches`, `parent_child`, `marriages`, `persons`; amended by ADR-038) |
| [009](009-clan-deletion-restrict.md) | Clan Deletion Is RESTRICT-Guarded | Accepted, shipped |
| [010](010-response-envelope-cursor-pagination.md) | Canonical Success Envelope + Cursor-Only Pagination | Accepted, shipped |
| [011](011-historical-date-precision.md) | HistoricalDate — Precision Model Replaces `*_approx` | Accepted, shipped |
| [012](012-computed-generation-mother-attribution.md) | Graph-Computed đời + Derived Mother Attribution | Accepted, shipped |
| [013](013-import-linter-boundary-ratchet.md) | Machine-Enforced Boundaries (import-linter + Ratchet) | Accepted, shipped |
| [014](014-uow-in-transaction-domain-events.md) | UoW In-Transaction Domain-Event Dispatch (Audit) | Accepted, shipped |
| [015](015-email-verification-flow.md) | Email Verification Flow | Accepted, shipped |
| [016](016-real-postgres-test-harness.md) | Real-Postgres Integration Test Harness | Accepted, shipped |
| [017](017-optimistic-concurrency.md) | Required Optimistic Concurrency Control on Genealogy Writes | Accepted, shipped |
| [018](018-vietnamese-lunar-calendar.md) | In-House Vietnamese Lunar Calendar Engine for Giỗ Recurrence | Accepted, shipped |
| [019](019-document-soft-delete-purge.md) | Document Soft-Delete + Retention Purge | Accepted, shipped (supersedes ADR-006's documents row) |
| [020](020-clan-export-formats.md) | Clan Export Formats — Lossless JSON Archive + GEDCOM Interop | Accepted, shipped |
| [021](021-non-enumerating-auth-surfaces.md) | Non-Enumerating Auth Surfaces + Request-Meta Audit Enrichment + Invitation-Accept Rate Limit | Accepted, shipped |
| [022](022-event-soft-delete-occ.md) | Events: Soft Delete + OCC + person FK SET NULL | Accepted, shipped |
| [023](023-parent-child-db-backstop.md) | DB Backstop for Genealogy Graph Invariants (parent_child trigger) | Accepted, shipped |
| [024](024-non-canonical-envelope-exceptions.md) | Non-Canonical Envelope Exceptions Typed As-Is (Normalize Pre-Frontend) | Normalized |
| [025](025-per-clan-edge-write-serialization.md) | Per-Clan Edge-Write Serialization + Invariant-Matching Unique Backstops | Accepted, shipped (2026-07-18, amends ADR-023) |
| [026](026-single-founder-designation.md) | Admin-Designated Single Founder (Thủy Tổ) + Deterministic Read | Accepted, shipped (2026-07-18) |
| [027](027-doi-single-authority.md) | Con Theo Đời Cha — đời Single Authority + Pedigree-Collapse Rendering | Accepted, shipped (2026-07-18) |
| [028](028-no-external-io-holding-db-connection.md) | No External I/O While Holding a Pooled DB Connection | Accepted, shipped (2026-07-18) |
| [029](029-two-sided-spouse-order.md) | Two-Sided Per-Person `spouse_order` + Marriage Date-Order on Update | Accepted, shipped (2026-07-18) |
| [030](030-platform-audit-newest-first-retention.md) | Platform Audit Log Newest-First (Opt-In DESC) + Audit Retention by Design | Accepted, shipped (2026-07-25) |
| [031](031-cross-clan-edges-app-layer.md) | Cross-Clan Edge Prevention Is an Application-Layer Guarantee (No DB Trigger) | Accepted (2026-07-25) |
| [032](032-db-outage-503.md) | Transient DB Operational Failures Surface as 503, Not 500 | Accepted (2026-08-01) |
| [033](033-w3c-trace-context-sentry.md) | W3C Trace Context for Correlation, Exported Through Sentry | Accepted (2026-08-02) |
| [034](034-mobile-riverpod-rebuild.md) | Rebuild the Flutter App on Riverpod, Deleting the Mock Scaffold | Accepted (2026-08-02) |
| [035](035-deterministic-login-membership-selection.md) | Deterministic Membership Selection in the Login/Profile Response | Accepted (2026-08-02) |
| [036](036-public-avatar-urls.md) | `persons.avatar_url` Is a Permanent Public URL, Written Only by set-avatar | Accepted (2026-08-02) |
| [037](037-change-requests-workflow.md) | Change Requests — Adopt the Dormant Table, Editor-or-Admin Review, Three-Way Merge on Approval | Accepted, shipped (2026-08-02) |
| [038](038-persons-returning-vs-membership-rls.md) | `persons` RLS — Fix the RETURNING/`persons_sel` Collision in the ORM, Not in the Policy | Accepted, shipped (2026-08-02, amends ADR-008 Phase 4) |
| [039](039-clan-user-list-identity-asymmetry.md) | Clan User Lists — `display_name` on Both, `email` Only on the Admin Pending Queue | Accepted, shipped (2026-08-02) |
| [040](040-metrics-token-floor-and-throttle.md) | `METRICS_TOKEN` Length Floor at Boot + 404-Preserving Failure Throttle | Accepted, shipped (2026-08-03) |
| [041](041-primary-green-heritage-family-single-background.md) | Leaf Green Is `primary`, Lacquer Red Becomes the `heritage` Family, One Warm Ground Is `background` | Accepted (2026-08-14), not shipped — seed S-005 renames |

When adding ADRs, use sequential numbering and keep prior ADRs immutable except for
Status updates. **Any breaking API contract change or new load-bearing architectural
decision must land with an ADR in the same PR** (see `docs/contracts/README.md` rules).
