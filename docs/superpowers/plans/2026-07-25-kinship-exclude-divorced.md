# Kinship excludes divorced marriages (M8) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** The kinship path (`find_relationship_path`) stops traversing `status='divorced'`
marriages as `spouse` edges, so the descriptor no longer emits present-tense
"Vợ/Chồng", "Mẹ kế/Bố dượng", con dâu/rể, or in-law terms for dissolved marriages.
Widowed/separated/married still count. Spec: `docs/superpowers/specs/2026-07-25-kinship-exclude-divorced-design.md`. One new migration (function replacement), no schema change, no new ADR, no i18n, no descriptor change.

**Architecture:** New migration `024_kinship_exclude_divorced` `CREATE OR REPLACE`s
`find_relationship_path` with migration 019's exact frontier-BFS body plus
`AND m.status <> 'divorced'` on the spouse-edge subquery; `downgrade` re-installs 019's
unfiltered body. Column `marriages.status` is `Mapped[str]` (NOT NULL) so `<> 'divorced'`
needs no NULL guard — same predicate as migration 022 / 015 / relationship_repository.

**Tech Stack:** plpgsql function via Alembic; real-PG integration tests (patterns:
`test_phase0_blockers.py` for `find_relationship_path` seeding, existing kinship /
relationship-descriptor suites).

## Global Constraints

- The filter is `status <> 'divorced'` **only** — widowed/separated/married keep the
  spouse edge (owner decision; matches `has_active_marriage`). Do NOT filter on
  `status = 'married'`.
- Reproduce migration 019's `_UPGRADE` body EXACTLY (frontier BFS, plpgsql, temp-table
  scratch, tie-break `DISTINCT ON ... ORDER BY neighbor_id, path_ids, path_edges`),
  changing ONLY the spouse-edge subquery. Do not "improve" anything else.
- `downgrade()` must restore 019's body verbatim (copy 019's `_UPGRADE` string) so the
  migration is cleanly reversible to the exact prior function.
- RED-first; full gate before done: `cd backend && uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports`.

---

### Task 1: RED — divorced marriages must not be kinship spouse edges

**Files:**
- Create: `backend/tests/integration/test_kinship_divorced.py`

**Interfaces:**
- Consumes: `migrated_db_url` / real-PG conftest; `find_relationship_path` seeding
  pattern from `test_phase0_blockers.py` (raw clan/person/marriage/parent_child
  inserts + `SELECT ... FROM public.find_relationship_path(:from,:to,:clan)`); the
  `describe_relationship` entry from `app/services/relationship_descriptor.py`
  (import + call on the path rows) OR drive the tree/handlers relationship endpoint —
  discover which the existing kinship tests use and mirror it.

- [ ] **Step 1: Write the tests** (per spec Tests 1–5):
  - `test_divorced_spouse_has_no_kinship_path` — A,B married then `status='divorced'`,
    no other link → `find_relationship_path(A,B)` returns zero rows (and, if driving the
    descriptor/endpoint, no "Vợ/Chồng" term). RED today.
  - `test_divorced_stepparent_not_described` — C child of P; P married X then divorced →
    C→X path is not `("parent","spouse")` / not step-parent term. RED today.
  - `test_widowed_spouse_still_kinship` — A,B `status='widowed'` → spouse path present,
    "Vợ/Chồng" still emitted (control, GREEN today; pins divorced-only).
  - `test_separated_spouse_still_kinship` — `status='separated'` → spouse path present
    (control, GREEN today).
  - `test_divorced_coparents_still_linked_via_child` — A,B divorced but share child C →
    A↔B connected via child/parent edges (path exists, edges are child/parent not
    spouse). GREEN today via the blood path; pins that people aren't removed, only the
    spouse edge.
- [ ] **Step 2: Run — record RED.** Expected fails: the two divorced tests (spouse,
  step-parent). Controls (widowed, separated, co-parent-via-child) pass. If a must-fail
  passes, STOP → BLOCKED (means status filtering already exists somewhere unexpected).
- [ ] **Step 3: Commit** — `git commit -m "test: RED — divorced marriages traversed as live kinship spouse edges (M8)"`.

---

### Task 2: The fix — migration 024 (function replacement)

**Files:**
- Create: `backend/migrations/versions/024_kinship_exclude_divorced.py`

- [ ] **Step 1: Author the migration.** `down_revision = "023_one_founder_per_clan"`,
  revision id `024_kinship_exclude_divorced` (≤32 chars — OK). Embed two SQL strings:
  - `_UPGRADE` = migration 019's `_UPGRADE` body copied EXACTLY, with the single spouse
    subquery changed to add `AND m.status <> 'divorced'` (place it right after the
    existing `AND m.is_deleted = false` / `AND m.created_by_clan_id = p_clan_id` line, so
    it reads consistently with migration 022's `status <> 'divorced' AND is_deleted = false`).
  - `_DOWNGRADE` = migration 019's `_UPGRADE` body copied EXACTLY (no filter).
  - `upgrade()`: `DROP FUNCTION IF EXISTS public.find_relationship_path(UUID, UUID, UUID, INT)` then `op.execute(_UPGRADE)` (mirror 019's upgrade).
  - `downgrade()`: same DROP then `op.execute(_DOWNGRADE)`.
- [ ] **Step 2: Apply + verify** — `uv run alembic upgrade head`; confirm head is now
  `024_kinship_exclude_divorced`. Sanity-check the function exists and the 3-arg call
  still works.
- [ ] **Step 3: Run** — Task-1 file now fully green (divorced tests flip; controls stay
  green); then `test_phase0_blockers.py` (uses `find_relationship_path`), the existing
  kinship / relationship-descriptor / tree suites; FULL suite (report count). Note the
  session-scoped test DB re-applies the whole chain incl. 024, so no manual DB step is
  needed for the suite.
- [ ] **Step 4: Commit** — `git commit -m "fix(kinship): exclude divorced marriages from relationship-path spouse edges (024, M8)"`.

---

### Task 3: Docs (grep-verified)

**Files:**
- Modify: `docs/architecture/domain-rules.md`
- Modify: `docs/ops/migrations.md`

- [ ] **Step 1: Grep** — `grep -rn "find_relationship_path\|kinship\|divorced\|spouse\|descriptor" docs/contracts docs/architecture docs/ops --include='*.md' | grep -v "review-2026-07-18\|superpowers"`. Disposition each hit.
- [ ] **Step 2: Edits** — domain-rules.md: kinship descriptor traverses only
  `status <> 'divorced'` marriages (divorced excluded from kinship paths; widowed/
  separated persist), matching `has_active_marriage`; reference the M8 finding + ADR-025's
  active-marriage semantics. migrations.md: add 024 (reversible function replacement, no
  schema change).
- [ ] **Step 3: Re-run grep; zero stale statements. Commit** — `git commit -m "docs: kinship excludes divorced marriages (M8, migration 024)"`.

---

### Task 4: Full gate (controller-run)

- [ ] `cd backend && uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports` — all five green.
