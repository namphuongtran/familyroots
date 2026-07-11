# Contract-Freeze Design Spec (pre-frontend gate)

**Date:** 2026-07-11
**Branch:** `feat/contract-freeze` (off `main` @ a70cee0)
**Purpose:** Freeze the 4 load-bearing API contracts the 2026-07-11 scorecard flagged as
"decide-before-frontend" (`docs/architecture/backend-scorecard-review-2026-07-11.md`), so the
(deferred) frontend binds each shape ONCE and the remaining grade-A backend work can land additively.

**Owner decisions (2026-07-11):**
- **Dates**: precision + display text; lunar stays a display string (NO range, NO structured lunar in v1). Add `precision` + `display` columns; migrate `approx` → `precision`.
- **đa thê attribution**: derive `mother_id` in the read-model (NO schema change).
- **đời** authority: graph-computed everywhere (recommended, accepted).
- **Typed envelope**: `Envelope[T]`/`Page[T]` `response_model` (recommended, accepted).

These are contracts to make REAL (implemented + emitted), not just documented — the frontend binds live shapes.

---

## Item 1 — Historical (fuzzy) date  — LARGEST (cross-cutting)

### Frozen contract (the object the frontend binds, everywhere a date appears)
```jsonc
"birth_date": {
  "date": "1750-01-01" | null,             // best-known point — sorting, giỗ anniversary
  "precision": "exact" | "year" | "month" | "circa" | "unknown",
  "display": "khoảng 1750" | null,          // human text; frontend shows this when precision != "exact"
  "lunar": "15/08 Nhâm Tý" | null           // display-only (structured lunar deferred)
}
```
Applies to every current date: `persons` birth/death, `events` event_date, `marriages` marriage/divorce.
When `precision == "exact"`, clients render `date`; otherwise render `display` (falling back to `date`).

### Storage (migration)
- `persons`: add `birth_date_precision` (String(10), default `'exact'`), `birth_date_display` (String(100), null); same for death. Migrate `birth_date_approx` → precision (`approx=true` ⇒ `'circa'`; else `date IS NOT NULL` ⇒ `'exact'`; `date IS NULL` ⇒ `'unknown'`). **DROP `birth_date_approx`/`death_date_approx`** (precision supersedes).
- `events`: add `event_date_precision` + `event_date_display`.
- `marriages`: add `marriage_date_precision`/`_display` + `divorce_date_precision`/`_display`.
- Keep existing `lunar_birth_date`/`lunar_death_date` strings (feed the `lunar` field). Events' `is_lunar_calendar` bool stays (drives the scheduler); add nothing lunar-structured.

### Blast radius (single-source: `precision` replaces `approx`) — ~13 files
Mostly mechanical plumbing (rename/remap the field): `schemas/{person,event,tree}.py` (+ `marriage.py`), `person_mapper.py`, `application/person/{commands,handlers}.py`, `person_query_port.py`, `tree_repository.py`, `tree_builder.py`, `domain/person/entity.py`, `models/person.py`. **One real logic site:** `services/relationship_descriptor.py::_age_rank` — currently returns `None` when either date is `approx`; change to "return `None` unless `precision == 'exact'`" (so kinship age-terms still refuse hard claims on any non-exact date). The `find_path` SQL / repo that threads `birth_date_approx` for the kinship path must select `birth_date_precision` instead.

### Approach
Add a `HistoricalDate` Pydantic model in `schemas/`; a small serializer builds it from `(date, precision, display, lunar)`. Response schemas (person/event/marriage + tree `TreeNode`/`SpouseNode`/`FocusAncestor`/`FocusTreeNode`) emit `HistoricalDate` for each date field. Write DTOs accept `precision`/`display` (optional; default `exact`/null). Reshapes the date fields of those responses (breaking — acceptable, frontend deferred).

### Out of scope (v1)
Date ranges (earliest/latest), structured lunar (can-chi year + lunar m/d + leap), reign-era precision.

---

## Item 2 — đa thê child→mother attribution (derive; no schema change)

### Frozen contract (on each child node in the tree/focus payload)
```jsonc
"mother_id": "uuid" | null,          // the child's female parent (which wife)
"mother_spouse_order": 1 | null      // that mother's spouse_order in her marriage to the father (vợ cả/hai/ba)
```
Frontend groups a father's `children` under each wife via `mother_id`; `mother_spouse_order` labels the group.

### Approach (read-model only)
In the tree descendant builder, for each child, find its **female parent** among that child's `parent_child` edges (clan-scoped) → `mother_id`. Then look up the marriage between the father (the node the child hangs under) and that mother → `mother_spouse_order = marriage.spouse_order`. Both via the batched queries already in `tree_builder` (extend the existing spouse/edge lookups; no N+1). `mother_id = null` when no mother edge is recorded (honest — child renders ungrouped). No migration, no write-path change.

### Out of scope
Storing `parent_role`/`via_spouse_id` on `parent_child` (revisit only if derivation proves too lossy in real data).

---

## Item 3 — đời (generation) authority: graph-computed everywhere

### Frozen contract
`generation` (and `generation_of_focus`) is ALWAYS the graph-derived đời (thủy tổ = 1; `distance-from-founder + 1`; `null` when not descended from a founder) on **every** tree endpoint — not the hand-entered `clan_memberships.generation`.

### Approach
`GET /tree` (full tree) + `/tree/subtree` currently surface `cm.generation` (via `get_family_tree_flat`). Make them compute đời the way `/tree/focus` already does (anchor = founder distance, then `base + local depth`) — extract the đời-stamping the focus handler uses into a shared helper and apply it in the full-tree/subtree handlers. `clan_memberships.generation` is **deprecated as a display source** (kept as a column; not dropped). One authority for "Đời N".

### Out of scope
Dropping/backfilling the `clan_memberships.generation` column; materializing đời.

---

## Item 4 — Typed response envelope (`Envelope[T]` / `Page[T]`)

### Frozen contract
OpenAPI documents real response schemas again (F-1 dropped `response_model` → opaque `object`). Generic:
```python
class Envelope[T](BaseModel):   data: T
class PageMeta(BaseModel):       cursor: str | None; has_more: bool; limit: int
class Page[T](BaseModel):        data: list[T]; meta: PageMeta
```

### Approach
Apply `response_model=Envelope[PersonResponse]` / `Page[PersonSummary]` etc. on the **fixed-shape** routes (all writes, action results, `/marriages`, `/parent-child`, single-resource GETs, the list endpoints with a stable item type). For the **dynamically-shaped person reads** (`profile=summary|detail|full` + `?fields=` + `?include=`), keep `dict[str, Any]` but document via `responses={200: {...}}` with a representative schema + a note — a single static `response_model` can't express the per-request shape. Runtime bodies are unchanged (still `{data}`/`{data,meta}`); only the OpenAPI annotation is restored, so it's non-breaking to clients and enables OpenAPI→TypeScript codegen.

### Out of scope
Reshaping the dynamic person reads to fit a static model; changing any runtime body.

---

## Testing

- **Dates**: migration up/down + drift gate; `approx→precision` data migration correctness (approx→circa, date→exact, null→unknown); responses emit `HistoricalDate` for person/event/marriage + tree nodes; kinship `_age_rank` refuses age-terms on non-`exact` dates (regression: an old test relying on `approx` still holds under precision).
- **Attribution**: real-DB tree with đa thê (father + 2 wives, children under each) → each child node's `mother_id` = correct wife, `mother_spouse_order` matches; child with no mother edge → `mother_id = null`.
- **đời**: `GET /tree` + `/tree/subtree` now return graph-computed đời (thủy tổ = 1) equal to `/tree/focus` for the same nodes; a clan with wrong hand-entered `cm.generation` still reports correct computed đời.
- **Envelope**: OpenAPI schema (`/openapi.json` in debug) shows typed `data`/`meta` for the annotated routes; runtime bodies byte-unchanged (existing envelope tests stay green).

Full gate: `uv run pytest`, `uvx ruff check .`, `uvx ruff format --check .`, `uv run mypy app/ tests/`, `uv run lint-imports`.

## Build decomposition (suggested — each its own PR)

The date item is by far the largest (migration + ~13 files + response reshaping); the others are smaller. Suggest sequencing as separate PRs so each is reviewable and the frontend can start against whichever contracts land first:
1. **Envelope[T]/Page[T]** (mechanical, unblocks TS codegen) — smallest, do first.
2. **đời-everywhere** (extract + apply the focus đời helper) — small.
3. **mother_id attribution** (read-model derive) — small.
4. **Historical date** (migration + precision-replaces-approx + HistoricalDate everywhere) — largest, its own PR.

## Explicitly NOT in this pass
Date ranges / structured lunar; `parent_role`/`via_spouse_id` storage; dropping `cm.generation`; sources/citations, person-merge, and the other grade-A/roadmap items (they land additively after, alongside frontend); RLS layer-2.
