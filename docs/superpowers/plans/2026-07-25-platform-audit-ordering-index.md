# Platform audit log: newest-first + index (M14) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** The platform audit log returns **newest-first** (opt-in `descending` on the
shared pager; all other lists stay ASC) and is backed by a `(created_at DESC, id DESC)`
index. Audit/notification retention is unbounded by design (documented, no job). Spec:
`docs/superpowers/specs/2026-07-25-platform-audit-ordering-index-design.md`. One
migration (index only), ADR-030.

**Architecture:** `paginate_query(descending=False)` flips the keyset filter (`<` vs `>`)
and ordering (`desc` vs `asc`); `get_audit_log` passes `descending=True`.
`encode_cursor`/`build_page` unchanged (direction-agnostic). New migration adds the
index. No table change, no purge job.

**Tech Stack:** SQLAlchemy async, Alembic; real-PG integration tests
(`test_me_and_platform_admin.py`, `test_pagination.py`, `test_schema_baseline.py`).

## Global Constraints

- **`descending` defaults False** — every existing `paginate_query` caller stays ASC
  (frontend-bound "single ASC scheme"). Only `get_audit_log` passes `descending=True`.
- DESC keyset filter is `created_at < c OR (created_at == c AND id < last_id)`, order
  `desc(created_at), desc(id)`. Verify the tie-break on equal `created_at` is monotonic
  and non-duplicating.
- `build_page`/`encode_cursor`/`decode_cursor` unchanged — the cursor stays the opaque
  `(created_at, id)` of `data[-1]`.
- Index migration `025_audit_logs_created_at_index` (revision id ≤32 chars),
  `down_revision = 024_kinship_exclude_divorced`; reversible (drop on downgrade).
- No retention job. RED-first; full gate: `cd backend && uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports`.

---

### Task 1: RED — audit log newest-first + DESC cursor

**Files:**
- Create: `backend/tests/integration/test_platform_audit_ordering.py`

**Interfaces:**
- Consumes: `migrated_db_url`/real-PG; the `_clan`/`_profile`/`_audit` seeding + the
  `SqlAlchemyPlatformAdminQueryPort(session).get_audit_log(...)` call pattern from
  `test_me_and_platform_admin.py` (READ it). Seed rows with DISTINCT, explicit
  `created_at` (pass an explicit timestamp column in the INSERT so ordering is
  deterministic, not now()-collided).

- [ ] **Step 1: Write the tests** (spec Tests 1–3, scoped to a FRESH clan_id so the
  session-scoped shared DB doesn't contaminate):
  - `test_audit_log_newest_first` — seed 3 rows with created_at t1<t2<t3 → `get_audit_log`
    `data[0]` is the t3 row and order is [t3,t2,t1]. **RED today** (ASC → t1 first).
  - `test_audit_log_desc_cursor_no_overlap_monotonic` — 4 rows, `limit=2` → page1 = 2
    newest, page2 = next 2, no id on both pages, every page2.created_at ≤ every
    page1.created_at. **RED today**.
  - `test_audit_log_tiebreak_equal_created_at` — 2 rows with IDENTICAL created_at →
    ordered by id DESC, `limit=1` cursor advances without dup/skip.
- [ ] **Step 2: Run — record RED.** newest-first + desc-cursor tests FAIL today (ASC);
  tie-break may pass or fail depending on today's asc-id behavior — assert the DESIRED
  DESC behavior and note today-state. If a must-fail passes, STOP → BLOCKED.
- [ ] **Step 3: Commit** — `git commit -m "test: RED — platform audit log is oldest-first, should be newest-first (M14)"`.

---

### Task 2: The fix — descending pager + audit log opt-in

**Files:**
- Modify: `backend/app/core/pagination.py` (`paginate_query` gains `descending`)
- Modify: `backend/app/infrastructure/persistence/platform_admin_query_port.py` (`get_audit_log` passes `descending=True`)

- [ ] **Step 1: pagination.py** — add `descending: bool = False`; import `desc`; branch the
  keyset filter and the `order_by` per spec §1. Default path byte-identical to today.
- [ ] **Step 2: platform_admin_query_port.py** — `paginate_query(query, AuditLog, cursor, limit, descending=True)` in `get_audit_log`.
- [ ] **Step 3: Run** — Task-1 file green; then `test_me_and_platform_admin.py`,
  `test_pagination.py`, `test_cursor_validation.py`, `test_pagination_cursor_errors.py`,
  documents/claims/events list suites (ASC-unaffected controls); FULL suite (report
  count). mypy; lint-imports.
- [ ] **Step 4: Commit** — `git commit -m "fix(pagination): opt-in descending pager; platform audit log newest-first (M14)"`.

---

### Task 3: Index migration + ADR + docs

**Files:**
- Create: `backend/migrations/versions/025_audit_logs_created_at_index.py`
- Create: `docs/decisions/030-*.md` (+ register in `docs/decisions/README.md`)
- Modify: `docs/ops/migrations.md`, the platform-admin/audit contract or architecture doc

- [ ] **Step 1: Migration** — `revision = "025_audit_logs_created_at_index"`,
  `down_revision = "024_kinship_exclude_divorced"`. `upgrade`: `op.create_index("idx_audit_logs_created_at", "audit_logs", [sa.text("created_at DESC"), sa.text("id DESC")])`. `downgrade`: `op.drop_index("idx_audit_logs_created_at", "audit_logs")`. Apply + confirm head.
- [ ] **Step 2: Index-exists test** — add a schema pin (in the Task-1 file or
  `test_schema_baseline.py` style) asserting `idx_audit_logs_created_at` exists via
  `pg_indexes`.
- [ ] **Step 3: ADR-030** — the platform audit log is the single intentional DESC list
  (opt-in `descending`); all clan-facing lists stay ASC; audit/notification retention is
  unbounded by design (compliance/heritage), index keeps reads fast; a purge job on the
  `document_purge` template is a documented future option. Register in the ADR index.
- [ ] **Step 4: Grep + docs** — `grep -rn "paginate\|ASC\|descending\|audit_log\|recent\|retention" docs/contracts docs/architecture docs/decisions --include='*.md' | grep -v "review-2026-07-18\|superpowers"`. Note the DESC exception + no-retention in the platform-admin/audit doc; add migration 025 to migrations.md. Disposition each hit.
- [ ] **Step 5: Re-run grep; zero stale statements. Commit** — `git commit -m "docs: platform audit newest-first + index (ADR-030, migration 025, M14)"`.

---

### Task 4: Full gate (controller-run)

- [ ] `cd backend && uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports` — all five green.
