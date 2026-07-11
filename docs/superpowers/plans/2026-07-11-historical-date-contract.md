# HistoricalDate Contract Implementation Plan (contract-freeze 2/2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Freeze the fuzzy-date contract — every date in a response becomes a `HistoricalDate` object `{date, precision, display, lunar}`; storage gains `precision` + `display`; `approx` is migrated to `precision` and dropped.

**Architecture:** Additive migration (add precision/display, backfill from approx) → define `HistoricalDate` + serializer + write-DTO fields → reshape read responses (person/event/marriage, then tree) → finally switch the ~13 `approx` readers to `precision` and drop the `approx` columns. Each task leaves the full gate green.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic v2, Alembic, pytest-asyncio (real-DB).

## Global Constraints
- **Contract:** each date field → `{"date": "YYYY-MM-DD"|null, "precision": "exact|year|month|circa|unknown", "display": str|null, "lunar": str|null}`. `precision=="exact"` ⇒ clients render `date`; else render `display` (fallback `date`).
- **Precision enum:** exactly `exact|year|month|circa|unknown`. NO date ranges, NO structured lunar (owner-scoped v1). Lunar stays the existing display string.
- **Migration:** revision ids ≤32 chars, chain on `011_path_tiebreak`. Backfill: `approx=true`→`circa`; `date IS NOT NULL`→`exact`; `date IS NULL`→`unknown`. Drop `approx` only in the FINAL task (after no code reads it). Drift gate (`test_schema_baseline.py`) stays green.
- **`approx`→`precision` semantic:** anywhere code treated a date as "approximate," the test is now `precision != 'exact'`. Kinship `_age_rank` must refuse hard age-terms unless BOTH dates are `exact`.
- **Write DTOs** accept flat `<field>_precision` (default `'exact'`) + `<field>_display` (optional); responses NEST into `HistoricalDate`.
- No behavior change beyond the date shape; clan isolation untouched.
- **Quality gate (full, every task)** from `backend/`: `uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports` (use `uv run mypy`). Green before every commit. Run the WHOLE suite (many tests assert date fields — the gate is the safety net).

---

## Task 1: Migration 012 — add precision/display columns + backfill; models keep `approx`

**Files:** Create `migrations/versions/012_historical_date_precision.py`; modify `app/models/person.py`, `app/models/event.py`, `app/models/marriage.py`; test `tests/integration/test_historical_date_migration.py` (new).

- Columns (all `String(10)` precision default `'exact'`; `String(100)` display nullable):
  - persons: `birth_date_precision`, `birth_date_display`, `death_date_precision`, `death_date_display`.
  - events: `event_date_precision`, `event_date_display`.
  - marriages: `marriage_date_precision`, `marriage_date_display`, `divorce_date_precision`, `divorce_date_display`.
- Backfill per date (in `upgrade()`), e.g. persons birth:
  `UPDATE persons SET birth_date_precision = CASE WHEN birth_date_approx THEN 'circa' WHEN birth_date IS NOT NULL THEN 'exact' ELSE 'unknown' END`.
  Marriages/events have no `approx` today → default `'exact'` where date present else `'unknown'` (marriage/divorce dates are nullable → `unknown` when null).
- Keep `birth_date_approx`/`death_date_approx` columns (dropped in Task 5). Add the new columns to the ORM models (keep approx mapped for now).
- `downgrade()` drops the new columns.

- [ ] Step 1: real-DB test — apply head, insert a person with `birth_date_approx=true` + a birth_date, and one with null birth_date; assert `birth_date_precision` backfilled `circa` / `unknown` respectively; a person with an exact date → `exact`. (Use the `migrated_db_url` + sync engine fixtures like `test_schema_baseline.py`.)
- [ ] Step 2: run → FAIL (columns absent).
- [ ] Step 3: write migration 012 + add columns to the 3 models.
- [ ] Step 4: run green + drift gate (`test_schema_baseline.py`) green.
- [ ] Step 5: full gate.
- [ ] Step 6: commit — `git add migrations/versions/012_historical_date_precision.py app/models/person.py app/models/event.py app/models/marriage.py tests/integration/test_historical_date_migration.py` ; `"feat(backend): migration — date precision/display columns + backfill from approx (historical-date)"`.

---

## Task 2: `HistoricalDate` schema + serializer + write-DTO fields

**Files:** Create `app/schemas/historical_date.py`; modify `app/schemas/person.py`, `app/schemas/event.py`, `app/schemas/marriage.py` (write DTOs only in this task); test `tests/unit/test_historical_date.py` (new).

- `app/schemas/historical_date.py`:
```python
from datetime import date
from pydantic import BaseModel

class HistoricalDate(BaseModel):
    date: date | None = None
    precision: str = "exact"        # exact|year|month|circa|unknown
    display: str | None = None
    lunar: str | None = None

def to_historical_date(
    value: date | None, precision: str | None, display: str | None, lunar: str | None
) -> HistoricalDate:
    return HistoricalDate(
        date=value, precision=precision or "exact", display=display, lunar=lunar
    )
```
- Write DTOs — add (keep the existing `birth_date` etc. scalars; ADD, in this task, alongside the still-present `approx`):
  - `PersonCreateRequest`/`PersonUpdateRequest`: `birth_date_precision: str = "exact"` (Update: `str | None = None`), `birth_date_display: str | None`, and death equivalents.
  - `EventCreateRequest`/`EventUpdateRequest`: `event_date_precision`, `event_date_display`.
  - `MarriageCreateRequest`/`MarriageUpdateRequest`: `marriage_date_precision`/`_display`, `divorce_date_precision`/`_display`.
  - (Leave `birth_date_approx` on the write DTOs for now; removed in Task 5.)
- [ ] Step 1: unit test — `to_historical_date(date(1750,1,1),"circa","khoảng 1750","...")` → correct object; `to_historical_date(None,None,None,None)` → `{date:None, precision:"exact", display:None, lunar:None}`.
- [ ] Steps 2–5: RED → implement → GREEN → full gate.
- [ ] Step 6: commit — `"feat(backend): HistoricalDate schema + serializer + write-DTO precision/display fields (historical-date)"`.

---

## Task 3: reshape person + event + marriage RESPONSES to `HistoricalDate`

**Files:** `app/schemas/person.py`, `app/schemas/event.py`, `app/schemas/marriage.py` (response models); serialization sites (`app/api/v1/persons.py`, `events.py`, `relationships.py` and/or their handlers/mappers); tests.

- Response reshape (replace scalar date + its `_approx` with a `HistoricalDate`):
  - `PersonResponse`: `birth_date: HistoricalDate` + `death_date: HistoricalDate` (drop `birth_date_approx`/`death_date_approx`/`lunar_birth_date`/`lunar_death_date` as top-level — folded into the objects). `PersonMini`/`PersonSummary`/`PersonDetail`/`PersonDetailComposite`: `birth_date`/`death_date` → `HistoricalDate` (these currently expose scalar birth/death only).
  - `EventResponse` (+ the other two event read models with `event_date`): `event_date: HistoricalDate`.
  - `MarriageResponse`: `marriage_date`/`divorce_date` → `HistoricalDate`.
- Because these use `from_attributes=True` on ORM objects, add a field serializer or build the `HistoricalDate` in the response construction. Recommended: a `model_validator`/`field` computed from the ORM's `(date, precision, display, lunar)` — OR construct in the route/handler via `to_historical_date(...)` and drop `from_attributes` reliance for those fields. Pick the pattern that keeps the existing `.model_validate(orm)` call sites working (a `@computed_field` or a pre-validator assembling the nested object from the flat ORM attrs is cleanest). Marriages/events have no lunar → pass `lunar=None`.
- [ ] Step 1: update person/event/marriage response tests to the nested shape (`body["data"]["birth_date"]["date"]`, `["precision"]`); RED.
- [ ] Steps 2–5: implement → GREEN → full suite (fix every other test asserting a scalar person/event/marriage date) → full gate.
- [ ] Step 6: commit — `"feat(backend): person/event/marriage responses emit HistoricalDate (historical-date)"`.

---

## Task 4: reshape TREE responses to `HistoricalDate`

**Files:** `app/services/tree_builder.py` (node dicts), `app/schemas/tree.py` (`SpouseNode`, `TreeNode`, `TreeNodeSummary`, `TreeNodeDetail`, `FocusAncestor`, `FocusTreeNode`), `app/infrastructure/persistence/tree_repository.py` (ancestors list + spouses), and the `get_family_tree_flat`/spouse SQL that must now also select `*_precision`/`*_display`; tests.

- The tree SQL functions (`get_family_tree_flat`, the spouse query, `get_ancestors_flat`) currently select `birth_date`/`death_date` (+ `birth_date_approx`). They must also return `*_precision` + `*_display` so the builder can assemble `HistoricalDate`. **This needs a migration to `CREATE OR REPLACE` those functions** (revision 012b/013 — chain appropriately) OR select the extra columns via the person JOIN in the Python query where the builder already joins persons. Prefer adding the columns to the SQL functions' `RETURNS TABLE` (a `CREATE OR REPLACE` migration) since the builder consumes their output.
- `tree_builder` node dicts: `birth_date`/`death_date` → nested `HistoricalDate` dicts (drop `birth_date_approx`/`death_date_approx` top-level). Spouse nodes + ancestors likewise.
- tree schemas: the six models' `birth_date`/`death_date` → `HistoricalDate`; drop the `_approx` fields.
- [ ] Step 1: update tree tests to nested date shape; RED.
- [ ] Steps 2–5: implement (incl. the SQL-function column additions) → GREEN → full gate.
- [ ] Step 6: commit — `"feat(backend): tree responses emit HistoricalDate (historical-date)"`.

---

## Task 5: switch `approx` readers → `precision`; drop `approx` (migration 013)

**Files:** `app/services/relationship_descriptor.py` (`_age_rank`), `app/infrastructure/persistence/tree_repository.py` + the `find_relationship_path` SQL (selects `birth_date_approx`), `app/domain/person/entity.py`, `app/infrastructure/persistence/person_mapper.py`, `app/application/person/{commands,handlers}.py`, `app/infrastructure/persistence/person_query_port.py`, write DTOs (drop `*_approx`); create `migrations/versions/013_drop_date_approx.py`; models drop `approx`; tests.

- Replace every remaining `birth_date_approx`/`death_date_approx` read with `precision != 'exact'` semantics. Kinship `_age_rank`: return `None` unless BOTH persons' relevant dates are `precision == 'exact'` (the `find_relationship_path` SQL must select `birth_date_precision` instead of `birth_date_approx`; the descriptor threads precision).
- Remove `*_approx` from write DTOs (fully replaced by `*_precision`).
- Migration 013: `DROP COLUMN` the `*_approx` columns on persons; remove from ORM models. Drift gate green.
- [ ] Step 1: tests — kinship refuses age-terms when a date is non-`exact` (precision-driven); a person round-trips precision; drift gate after drop. RED where behavior/columns change.
- [ ] Steps 2–5: implement → GREEN → full suite (no remaining `_approx` references: `grep -r _approx app/` returns nothing) → full gate.
- [ ] Step 6: commit — `"refactor(backend): precision replaces approx everywhere; drop date_approx columns (historical-date)"`.

---

## Self-Review
- Migration adds precision/display + backfills; approx dropped only after readers switch (Task 5) — each task green. ✅
- HistoricalDate object on ALL response date fields (person/event/marriage + tree); write DTOs take flat precision/display. ✅
- Precision enum fixed (exact|year|month|circa|unknown); no range/structured-lunar; lunar stays string. ✅
- `approx`→`precision` semantic (`_age_rank` exact-only; find_path SQL selects precision). ✅
- Type consistency: `HistoricalDate`/`to_historical_date` signature stable across schema + serialization; precision `str` default `'exact'` across models/DTOs/migration. ✅
- Risk noted: Task 4 touches the tree SQL functions' RETURNS TABLE (a CREATE OR REPLACE migration + both scoped/unscoped defs like migration 005) — the fiddliest step.
