# ADR-030: Platform Audit Log Newest-First (Opt-In DESC) + Audit Retention by Design

## Status
Accepted, shipped (2026-07-25).

## Context

The 2026-07-18 backend review (`docs/architecture/backend-review-2026-07-18.md`,
finding **M14**) flagged the platform-admin audit log:

- `SqlAlchemyPlatformAdminQueryPort.get_audit_log` paginates through the shared
  `paginate_query`, which hardcoded `ORDER BY created_at ASC, id ASC`. But the port
  contract says *"Get **recent** audit logs across the platform"* and the table's
  indexes were built `created_at DESC` (`idx_audit_logs_clan`, `idx_audit_logs_actor`,
  migration 001). So a super-admin saw the **oldest** events first and had to page
  through the entire history to reach today.
- The **unfiltered** platform-wide query (no `clan_id` filter — it returns rows across
  all clans, not only `clan_id IS NULL` platform events) had **no bare `(created_at)`
  index**, so it fell back to a full scan + sort that worsened as `audit_logs` grew.
- `audit_logs` and `notification_log` grow **unbounded** (no retention).

The whole public API uses a **single ASC cursor-pagination scheme** (opaque
`(created_at, id)` cursors) that the frontend binds — so the pager could not simply be
flipped globally.

## Decision

1. **Opt-in descending pagination.** `paginate_query` gains `descending: bool = False`.
   The default is byte-for-byte the existing ASC behavior, so every clan-facing list is
   unchanged. `descending=True` flips both the keyset comparator
   (`created_at < cursor OR (== AND id < last_id)`) and the ordering
   (`created_at DESC, id DESC`). The opaque cursor and `build_page` are
   direction-agnostic. **`get_audit_log` is the only caller that passes
   `descending=True`** — it is a super-admin-only internal endpoint, not a
   frontend-bound public list, so this single deviation from the ASC scheme is
   deliberate and scoped.

2. **Supporting index.** Migration `025_audit_logs_created_at_index` adds
   `idx_audit_logs_created_at ON audit_logs (created_at DESC, id DESC)`, backing the
   platform-wide newest-first keyset scan. Per-clan / per-actor reads keep using the
   existing composites.

3. **Audit retention: unbounded by design.** `audit_logs` and `notification_log` are
   **retained indefinitely** — the audit trail is a compliance / heritage record that
   must not be silently deleted, and the new index keeps reads fast at any size. No
   purge job is added.

## Consequences

- The platform audit log now reads newest-first, matching its contract and its DESC
  indexes; admins see today's events immediately.
- The ASC contract for all clan-facing lists is untouched and untouchable-by-accident
  (the flag is opt-in, defaulted off).
- Audit/notification tables grow without bound. This is accepted; if volume ever
  demands it, a scheduled purge can be added on the `app/services/document_purge.py`
  template (advisory lock + a configurable `AUDIT_RETENTION_DAYS`, `0` = disabled) —
  a documented future option, intentionally not built now.

## Alternatives considered

- **Keep ASC, reword the "recent" contract to "oldest-first."** Rejected: an audit tool
  that shows the oldest event first is poor admin UX and contradicts the DESC indexes.
- **Flip `paginate_query` globally to DESC.** Rejected: breaks the frontend-bound ASC
  scheme for every clan-facing list.
- **Add a retention purge job now.** Rejected for this change: permanently deletes audit
  history for a compliance/heritage platform, and adds a background writer + config +
  scheduler surface not warranted at current volume.
