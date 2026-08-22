# ADR Index

| ADR | Title | Status |
|-----|-------|--------|
| [001](001-ddd-cqrs-hexagonal.md) | DDD + CQRS + Hexagonal Backend Architecture | Accepted, shipped |
| [002](002-clan-scoped-multitenancy.md) | Single Schema Clan-Scoped Multitenancy | Accepted, shipped (app-layer isolation) |
| [003](003-rest-first-client-contract.md) | REST-First Cross-Client Contract Strategy | Accepted, shipped |
| [004](004-redis-pubsub-events.md) | Redis for Distributed Domain Events | **Deferred — not built** (in-process dispatcher today, see ADR-014) |
| [005](005-dedicated-export-worker.md) | Dedicated Worker Service for Heavy Exports | **Deferred — not built** |
| [006](006-soft-vs-hard-delete.md) | Selective Soft-Delete by Aggregate | Accepted, shipped. The `documents` row is superseded by ADR-019; the 2026-07-02 edge-cascade update is amended by **ADR-051** — there is no cascade, an edge's visibility is derived on read |
| [007](007-identity-claims-workflow.md) | Identity Claims Workflow | Accepted, shipped |
| [008](008-rls-defense-in-depth.md) | Row-Level Security as Defense-in-Depth Layer-2 | Accepted, shipped. Phases 1-11, migrations 002 and 026-036. Clan-isolated: `documents`, `events`, `branches`, `parent_child`, `marriages`, `persons`, `change_requests`, `clan_memberships`, `clan_invitations`, `notification_log`, `clan_settings`. Not clan isolation: `identity_claims` (deny-all tripwire, ADR-042), `audit_logs` (clan-keyed reads only, ADR-043) and `user_clan_roles` (clan-keyed UPDATE and DELETE only, ADR-050). Amended by ADR-038 (Phase 4), ADR-047 (§ 2), and the dated Phase-10 amendment to its "Not yet" paragraph |
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
| [041](041-primary-green-heritage-family-single-background.md) | Leaf Green Is `primary`, Lacquer Red Becomes the `heritage` Family, One Warm Ground Is `background` | Accepted, shipped (2026-08-14, seed S-005) |
| [042](042-identity-claims-app-layer-isolation-system-session-lockout.md) | `identity_claims` Keeps Application-Layer Clan Isolation, and Its RLS Policy Denies the Request Role | Accepted (2026-08-22, seed S-011) — decision only; **implemented 2026-08-22 by seed S-012**, migration `033_rls_identity_claims`. The policy is a deny-all tripwire, not clan isolation |
| [043](043-audit-notification-rls-posture.md) | `audit_logs` Is Inside RLS Layer 2 with Per-Command Policies, `notification_log` Takes the Template Unchanged | Accepted, shipped (2026-08-22, seed S-013) — **implemented 2026-08-22 by seed S-014**, migration `034_rls_audit_notification` plus `AuditLog.__mapper_args__`. `notification_log` took the template; `audit_logs` took clan-keyed reads, a permissive INSERT, and no UPDATE/DELETE policy. Its Measurement 2 is stale on one row: `POST /invitations/{token}/accept` moved to the system session in ADR-048, so only two request routes write an audit row with no clan GUC |
| [044](044-privacy-toggles-dropped-from-v1.md) | `allow_public_tree` and `privacy_level` Are Dropped from v1, and the Concept Returns Only as One Column | Accepted (2026-08-22, seed S-016) — decision only; **S-017 and S-018 carry one column each**. Both drop by reversible migration, which loses nothing because the table is empty. The boolean does not come back (it is a projection of the level — ADR-027's single-authority rule); the level may, on four named terms. Nothing creates a `clan_settings` row and nothing should: measured 2026-08-22, an insert on the clan-less register session is rejected by migration `035`'s `WITH CHECK`. Corrects S-016's claim that the value domain is unstated — it was stated in `data-model.md` in **two** places, the column table and the ER diagram, and **both went with the column on 2026-08-22** (seeds S-017 and S-018, migrations `037_drop_allow_public_tree` and `038_drop_privacy_level`). Do not follow the line number this cell used to carry: nothing holds the domain now |
| [045](045-dark-mode-prefers-color-scheme-only.md) | Dark Mode Switches on `prefers-color-scheme` Alone, and the Dark Palette Is a Token Override | Accepted, shipped (2026-08-21, seed S-006) |
| [046](046-backoffice-aside-is-a-surface-step-not-an-inverted-region.md) | The Backoffice Aside Stops Being Inverted and Becomes a Surface Step | Accepted (2026-08-22, seed S-039) — decision only, no code; the edit is S-061. Rejects an `inverse-surface` role: M3 defines it as "the reverse of what is seen in the surrounding UI" and it flips (`color_scheme.dart:1313-1316`), a pair is six roles short, and `contrast.test.ts` structurally rejects a token that does not flip. The rail takes `muted`, so every pair it composes is already in `CASES` — zero new tokens. Withdraws the claim that S-006 made the boundary vanish: the rail's neighbour is `bg-gray-50`, so the step is 19.27:1 in both schemes and the 1.09:1 state arrives only with S-038. Found a live AA failure that had shipped since 2026-08-21: the brand mark measures **1.90:1** in dark, and the active pill 2.68:1 in light |
| [047](047-rls-seam-sets-clan-id-only.md) | The RLS Seam Sets `app.clan_id` Only, and ADR-008's `app.user_id` Clause Is Corrected by Dated Amendment | Accepted (2026-08-22, seed S-040) — decision only; amends ADR-008 § 2, no code change |
| [048](048-invitation-accept-runs-on-the-system-session.md) | Only `POST /invitations/{token}/accept` Moves to the System Session, and `clan_invitations` Takes the Clan-Isolation Policy | Accepted, shipped (2026-08-22, seed S-043) |
| [049](049-contact-pii-is-the-whole-field-visibility-rule.md) | Contact PII Is the Whole of Field-Level Visibility in v1, the Set Stays Fixed at `phone` and `email`, and the Contract Says So | Accepted (2026-08-22, seed S-053) — decision only, no code. The rule has shipped since 2026-07-05; this ADR keeps it fixed and writes it into `rest-persons-api.md`. Not per-clan: that lands on `clan_settings`, which ADR-044 measured dead, and "no row" is universal, so a configurable set must resolve missing to the maximal set or ship as total disclosure. Not extended: `_UPDATABLE_FIELDS` minus `SUBMITTABLE_PERSON_FIELDS` is exactly `_PII_FIELDS` is exactly `EXCLUDED_PERSON_FIELDS`, measured. Failure direction closed at two layers. Found that no test proves any route calls the redaction (S-058), and that `L11`, cited by six files, is defined nowhere |
| [050](050-user-clan-roles-clan-keyed-mutations.md) | `user_clan_roles` Takes Clan-Keyed UPDATE and DELETE Only, and Every Reader Stays on the Session It Is On | Accepted, shipped (2026-08-22, seed S-052) — migration `036_rls_user_clan_roles`. Half covered on purpose: `SELECT` and `INSERT` are permissive (the authorization gate and `POST /auth/onboard` both run with no clan selected), `UPDATE` and `DELETE` are clan-keyed. The mirror of ADR-043. No handler changed session |
| [051](051-edge-visibility-derived-not-cascaded.md) | Person Soft-Delete Does Not Cascade to Its Edges — an Edge's Visibility Is Derived, Not Stored | Accepted (2026-08-22, seed S-055) — decision only, no code. Amends ADR-006's update of 2026-07-02 by dated amendment: its cascade clause is superseded, its restore-symmetry clause stands and is satisfied exactly by the derived predicate. No marker column, no `PersonDeleted` consumer, no trigger. The cascade lost chiefly because a cascading **restore** runs migration 022's full `parent_child` guard and can be refused and left half-applied. S-056 gives the two by-id reads the same predicate the batch reads carry, and builds no cascade |
| [052](052-restore-bootstraps-the-request-role.md) | A Restore Bootstraps the `familyroots_app` Role and Its Grants, and the Drill Proves It Two-Sided | Accepted, shipped (2026-08-22, seed S-057, opened by S-050). **Indexed 2026-08-22, one batch late** — the ADR landed without a row here, which is the defect this index exists to prevent |
| [053](053-invitation-status-is-derived-not-stored.md) | An Invitation's Reported Status Is Derived From `expires_at`, Not Stored | Accepted, shipped (2026-08-22, seed S-019). **Supersedes an owner decision**, recorded at `specs/2026-07-25-invitation-expiry-reinvite-design.md:5` as "not a list-display change"; the maintainer was asked on 2026-08-22 and chose the reversal, and that spec carries a dated amendment. One predicate, `is_expired`, with two callers, so the read and the accept refusal cannot drift. No sweep: it would add a third out-of-band writer for a value no reader needs. Makes design-spec § J20's client-side rule redundant rather than contradicted, so no web or mobile work is owed. Nothing about the stored data changed |
| [054](054-clan-settings-table-is-dropped.md) | The `clan_settings` Table Is Dropped, and a Per-Clan Setting Must Be Designed Rather Than Re-Enabled | Accepted, shipped (2026-08-22, seed S-065) — migration `039_drop_clan_settings`. Closes ADR-044 § 5's hand-off. Zero rows, no endpoint, and a policy guarding a reader that could not arrive: ADR-044 Measurement 5 shows the obvious row creator is rejected by migration `035`'s own `WITH CHECK`. **Two features reached for this table and both declined on that same wall**, neither inheriting the reason from the other. Design spec § 7.10d refuses to draw its knobs — "No toggle for an unenforced setting ships" — and `data-model.md`'s "Roadmap item D3" resolved to nothing. "Keep it dormant with a note" lost on evidence: that had already been tried on this table and did not stop the cost. `rbac.md` loses its clan-settings rows and `rest-clans-api.md:168` stops meaning two things |
| [055](055-eight-tokenless-colour-families-decided-per-group.md) | The Eight Tokenless Colour Families Are Decided Per Group, Not Swept | Accepted, shipped (2026-08-22, seed S-068). **Gender coding loses its colour outright** — `MemberNode`, `MemberAvatar`, and `TreeCanvas`'s minimap were T-06's forbidden *only* channel, so this was never a token gap. Role, status, and stat-tile groups reuse existing tokens (`primary-container`, `accent`) or get **one** new one, `success`, quoted from spec § 2.1/2.2, and only where the state is real rather than decorative. Event kinds and the arbitrary six-colour stat rotation fold into existing neutral and accent treatments. **No `info` family, no `success-container`, and no second channel were added, because none was defended** |

**No number is allocated and unwritten.** Every ADR from 001 to 053 that a seed has claimed is
written and indexed above. **046 left this sentence on 2026-08-22**, written by seed S-039, as **049**
did the same day by seed S-053; the block quote below records why 049 was allocated twice and is
kept. **044, 050, 051, 052 and 053 were all written on 2026-08-22** by seeds S-016, S-052, S-055,
S-057 and S-019. **048 was taken by seed S-043 on 2026-08-22**, the same day 047 went to seed S-040.
Pre-allocating in the seed is deliberate, so that four agents picking work at once cannot pick the
same number. **054 was written on 2026-08-22 by seed S-065**, which dropped the table rather than
deciding what it was for. **055 was written on 2026-08-22 by seed S-068.** The next free number is **056**. This index is not the
authority: read [`../SEEDS.md`](../SEEDS.md), which wins when the two disagree.

> **ADR-052 landed on 2026-08-22 without a row here and was indexed one batch late**, on the same
> day, by the coordinator. Nothing caught it: an ADR file and this index are two places, and only
> this one is read when someone asks which numbers are taken. The check that found it compares the
> files on disk against the rows here in both directions, and it is worth re-running whenever an ADR
> lands:
>
> ```bash
> for f in docs/decisions/0*.md; do n=$(basename "$f" | cut -c1-3); \
>   grep -q "^| \[$n\]" docs/decisions/README.md || echo "ADR $n not indexed"; done
> ```

> **049 was allocated twice, and the second allocation is the live one.** Seed S-051 pre-allocated
> it on 2026-08-22 and then wrote no ADR, because what it had to say is about how this repository
> verifies rather than about the system it builds, and that belongs in `.claude/rules/seeds.md`
> (see its § "Why this is a rule here and not ADR-049"). This paragraph read "049 stays free by
> decision" for part of that day. Seed S-053 took it the same day for field-level visibility. **A
> released number is free, not reserved** — say which seed holds a number, not merely that it is
> taken. **S-053 closed on 2026-08-22 and ADR-049 is now written**, indexed in the table above.

> **This paragraph is a merge point, so re-read it rather than editing it from memory.** It was
> resolved by hand on 2026-08-22 after seeds S-011 and S-013 ran in parallel and each narrowed the
> sentence to exclude only its own number, which conflicted. It also carried a real defect until
> that day: it said the next free number was 046 while `SEEDS.md` had already allocated 046 to
> S-039 and said 047. **`SEEDS.md` is the authority on which numbers are taken**, because a seed
> allocates its number in its own text. When the two disagree, this file is the bug.

When adding ADRs, use sequential numbering and keep prior ADRs immutable except for
Status updates. **Any breaking API contract change or new load-bearing architectural
decision must land with an ADR in the same PR** (see `docs/contracts/README.md` rules).
