# GEDCOM parent grouping by relationship type (M6) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** GEDCOM export stops inventing couples: a child's parents are grouped by
`relationship_type`, and within a type paired only via a real marriage or as an
exactly-two couple, else single-parent FAMs — never across types. Spec:
`docs/superpowers/specs/2026-07-25-gedcom-parent-families-design.md`. No migration, no
new ADR (refines ADR-020).

**Architecture:** Rewrite the pairing loop in `gedcom_export._link_children`
(`app/services/gedcom_export.py:172-220`) to partition by relationship type and pair
within a type (real-marriage-first → exactly-two-couple → single). Everything else
(marriage FAMs, PEDI mapping, HUSB/WIFE, sort keys, `family_by_pair` dedup) is preserved.

**Tech Stack:** pure-Python service (`app.services` — fenced by import-linter; no
api/application/domain/models imports). Unit tests (`test_gedcom_export.py`) + real-DB
export tests (`test_clan_export_gedcom.py`).

## Global Constraints

- **Never pair two parents of different `relationship_type` into one FAM.**
- Deterministic: children sorted by `str(id)`; within a child, types processed in
  sorted name order and parents in `str(id)` order; greedy real-marriage pairing in
  sorted order. Same input → byte-identical output regardless of edge input order.
- Preserve `family_by_pair` dedup (synthetic couple keyed `frozenset({a,b})`,
  single-parent keyed `frozenset({parent})`) so co-children share a FAM; PEDI stays
  per-`child_famc` entry (a shared FAM can carry different PEDI per child).
- `pedi = None if relationship_type == "biological" else relationship_type` (unchanged
  mapping). Do NOT change the `2 PEDI <rel>` value emission (step-PEDI is a separate
  tracked concern).
- `app.services` import boundary must stay clean (no new imports outside stdlib +
  existing). RED-first; full gate before done: `cd backend && uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports`.

---

### Task 1: RED — parents grouped by type, no invented cross-type couples

**Files:**
- Create: `backend/tests/unit/test_gedcom_parent_families.py`

**Interfaces:**
- Consumes: the GEDCOM export entry point + in-memory fixture shape used by
  `tests/unit/test_gedcom_export.py` (discover how it builds persons/edges/marriages
  and calls the exporter; mirror it). Assertions parse the emitted GEDCOM text
  (FAM records, `1 HUSB`/`1 WIFE`/`1 CHIL`, child `1 FAMC` + `2 PEDI`).

- [ ] **Step 1: Write the tests** (spec Tests 1–6). Key RED test: a child with
  biological mother (F) + biological father (M) + adoptive father (M), no marriages →
  assert (a) exactly one FAM contains BOTH biological parents as HUSB/WIFE and the child;
  (b) NO FAM lists a biological parent together with the adoptive father as HUSB/WIFE;
  (c) the adoptive father appears in a single-parent FAM with the child's FAMC carrying
  `2 PEDI adopted`; (d) the child has exactly two `1 FAMC` links. **RED today** (UUID
  pairing can put the adoptive father in a couple with a biological parent). Add the
  bio-couple regression, real-marriage-within-type, adoptive-couple, single-adoptive-
  alongside-bio-couple, and determinism (export twice / shuffled edge order → identical)
  tests.
- [ ] **Step 2: Run — record RED.** The 3-parent invention test must FAIL today (assert
  the DESIRED post-fix structure). If it PASSES for a given UUID ordering, force the RED
  by choosing parent UUIDs whose sort order interleaves types (e.g. adoptive father's id
  sorts between the two biological parents') — document the construction. Controls
  (bio-couple, determinism) may pass today. If the must-fail passes for ALL orderings,
  STOP → BLOCKED.
- [ ] **Step 3: Commit** — `git commit -m "test: RED — GEDCOM invents cross-type parent couples (M6)"`.

---

### Task 2: The fix — group parents by relationship type

**Files:**
- Modify: `backend/app/services/gedcom_export.py` (`_link_children`)

- [ ] **Step 1: Rewrite `_link_children`'s per-child pairing** per spec §Design:
  partition the child's unique parents by `relationship_type`; for each type (sorted),
  (a) greedily attach the child to any real marriage FAM among the type's parents
  (consume both), (b) of the remaining unconsumed: exactly-two → one synthetic couple
  FAM, else → single-parent FAM(s); `pedi = None if type == 'biological' else type`.
  Reuse `family_by_pair` for dedup; keep `_husb_wife` for HUSB/WIFE; keep the sort keys.
  Never pair across types.
- [ ] **Step 2: Run** — Task-1 file green; then `test_gedcom_export.py`,
  `test_clan_export_gedcom.py`, `test_clan_export_json.py`, `test_txn_pool_hygiene.py`;
  FULL suite (report count). mypy (note `app.services.*` per-module override — keep it
  clean); lint-imports (services boundary).
- [ ] **Step 3: Commit** — `git commit -m "fix(gedcom): group child parents by relationship type; never invent cross-type couples (M6)"`.

---

### Task 3: Real-DB end-to-end + docs

**Files:**
- Create/extend: `backend/tests/integration/test_clan_export_gedcom.py` (a mixed-type-parents case)
- Modify: `docs/contracts/rest-exports-api.md`
- Possibly: `docs/decisions/020-clan-export-formats.md`

- [ ] **Step 1: Real-DB test** — seed a clan + a child with a biological mother+father
  and an adoptive father (real `persons` / `parent_child` rows), hit the export endpoint,
  parse the GEDCOM, assert no invented couple + the expected multi-FAMC/PEDI. Follow the
  existing `test_clan_export_gedcom.py` seeding + parse helpers.
- [ ] **Step 2: Grep + docs** — `grep -rn "FAMC\|PEDI\|couple\|paired\|parent\|relationship_type" docs/contracts docs/decisions --include='*.md' | grep -v "review-2026-07-18\|superpowers"`. Rewrite `rest-exports-api.md:170` (parents grouped by type; within-type real-marriage/couple/single; never cross-type; one FAMC per family unit with its PEDI). Update ADR-020 if it details FAM construction. Disposition each hit.
- [ ] **Step 3: Re-run grep; zero stale statements. Commit** — `git commit -m "test+docs: GEDCOM groups parents by type; no invented couples (M6)"`.

---

### Task 4: Full gate (controller-run)

- [ ] `cd backend && uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports` — all five green.
