# Platform audit log: newest-first + supporting index (M14) — Design

**Date:** 2026-07-25
**Source finding:** M14 in `docs/architecture/backend-review-2026-07-18.md`.
**Owner decisions:** (a) DESC newest-first for the platform audit log via an opt-in
`descending` flag (all other lists stay ASC); (b) NO retention purge — audit /
notification history is retained by design; the new index keeps queries fast.

## Problem

`SqlAlchemyPlatformAdminQueryPort.get_audit_log` paginates via the shared
`paginate_query`, which hardcodes `order_by(asc(created_at), asc(id))`
(`core/pagination.py:59`). But the port contract says *"Get **recent** audit logs
across the platform"* (`domain/platform_admin/query_port.py:117`) and the table's
indexes were built `created_at DESC` (`idx_audit_logs_clan`, `idx_audit_logs_actor`,
migration 001:853-854). So a super-admin opening the audit log sees the **oldest**
events first and must page through the entire history to reach today. Two further gaps:
- **No bare `(created_at)` index** — the platform-wide query (`clan_id IS NULL`) orders
  by `created_at, id` with nothing to support it → a full scan + sort that worsens as
  `audit_logs` grows.
- **Unbounded growth** — no retention on `audit_logs`/`notification_log`.

## Design

### 1. Opt-in DESC pagination (`core/pagination.py`)

`paginate_query` gains `descending: bool = False`. Default (False) is byte-for-byte
today's behavior — every existing caller (documents, claims, events, clans, and the
clan-scoped audit reads) stays ASC, preserving the frontend-bound
"single ASC cursor scheme" contract. When `descending=True`:

```python
if cursor:
    created_at, last_id = decode_cursor(cursor)
    if descending:
        query = query.where(
            or_(model.created_at < created_at,
                and_(model.created_at == created_at, model.id < last_id))
        )
    else:
        query = query.where(
            or_(model.created_at > created_at,
                and_(model.created_at == created_at, model.id > last_id))
        )
order = (desc(model.created_at), desc(model.id)) if descending else (asc(...), asc(...))
return query.order_by(*order).limit(limit + 1)
```

`encode_cursor`/`decode_cursor`/`build_page` are unchanged — the cursor is still the
opaque `(created_at, id)` of the last row on the page, and `build_page` is
direction-agnostic (it encodes `data[-1]`; the DESC filter continues correctly with
`<`). `get_audit_log` passes `descending=True`; nothing else does.

### 2. Supporting index (new migration `025_audit_logs_created_at_index`)

`CREATE INDEX idx_audit_logs_created_at ON audit_logs (created_at DESC, id DESC)` —
supports the platform-wide `clan_id IS NULL` "recent" keyset scan (ORDER BY + the
`(created_at, id)` cursor filter) without a full scan/sort. The existing
`idx_audit_logs_clan (clan_id, created_at DESC)` already covers the clan-filtered
variant. Reversible (drop on downgrade). No table change.

### 3. Retention: none, by design (documented)

Per the owner decision, `audit_logs` and `notification_log` are **retained
indefinitely** — the audit trail is a compliance/heritage record, and the new index
keeps reads fast at any size. No purge job is added. Documented so the "unbounded"
observation is a recorded, intentional choice (a retention job can be added later, on
the `document_purge` template, if volume ever demands — noted as a future option).

### ADR

Add **ADR-030** — the platform-admin audit log is the single intentional DESC
(newest-first) list; all clan-facing lists remain ASC. Records the opt-in
`descending` mechanism and the no-retention-by-design decision, and that this deviation
is scoped to a super-admin-only internal endpoint (not the frontend-bound public lists).

## What does NOT change

- Every other cursor-paginated endpoint (ASC, unchanged).
- The audit `Page`/`PageMeta` envelope, cursor opacity, `AuditLogEntryView` shape.
- `notification_log` (no new index, no query change — only the retention note).
- Audit write paths.

## Tests (real-DB; RED-first)

1. **Newest-first ordering** (the bug): seed ≥3 `audit_logs` rows for a fresh clan with
   DISTINCT, increasing `created_at` (t1<t2<t3) → `get_audit_log` returns them
   **newest-first** (t3, t2, t1); `data[0]` is the most recent. **RED today** (returns
   t1 first).
2. **DESC cursor paginates without overlap/gap**: page through a fresh clan's rows with
   `limit=2`, DESC → page1 = the 2 newest, page2 = the next, no row on both pages, and
   every row on page2 is older than every row on page1 (the keyset is monotonic
   descending). RED today (ASC order).
3. **Tie-break on equal `created_at`**: two rows with identical `created_at` order by
   `id DESC` deterministically and don't duplicate/skip across the cursor.
4. **ASC callers unaffected** (control): a `paginate_query`-based list that does NOT pass
   `descending` (e.g. a documents/claims/events list, or a direct unit test of
   `paginate_query`) still orders ASC. Pin so the opt-in didn't leak.
5. **Index exists** (schema pin): `idx_audit_logs_created_at` is present after migration
   (query `pg_indexes`), mirroring the schema-baseline test style.
6. Existing platform-admin + pagination suites stay green (the advancement/no-overlap
   test is order-agnostic; the newest-first change doesn't break it).

## Docs

- `docs/architecture/rbac.md` or the platform-admin doc / `docs/contracts/` audit
  section: the platform audit log is newest-first (DESC), the one intentional exception
  to the ASC list scheme; retained indefinitely (no retention purge by design).
- `docs/ops/migrations.md`: migration 025 (index; reversible).
- `docs/decisions/README.md`: register ADR-030.
- Grep sweep: `paginate_query|ASC|descending|audit_log|created_at|retention|recent`
  across docs/contracts + docs/architecture + docs/decisions; per-hit dispositions.
