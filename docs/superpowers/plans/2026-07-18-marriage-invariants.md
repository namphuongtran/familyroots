# Marriage-Record Invariants (A7 — M1 + M7) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `divorce_date ≥ marriage_date` is enforced on marriage PATCH (M1), and `spouse_order` uniqueness is orientation-independent (M7, two-sided per-person) so a flipped `(W2, H)` can't create a second "vợ cả". Spec: `docs/superpowers/specs/2026-07-18-marriage-invariants-design.md`. No migration.

**Architecture:** M1 — the update handler re-validates effective (merged) dates, raising domain `ValidationError` (422, structured envelope — the app's convention for handler/domain validations). M7 — `has_spouse_order_conflict` widens to check both `person1_id`/`person2_id` for either endpoint; validator + handlers pass both ids; existing person1-keyed partial unique index stays. ADR-029.

**Tech Stack:** SQLAlchemy async raw SQL, pydantic v2, real-PG integration tests (pattern: existing relationship suites).

## Global Constraints

- **Error codes (verified against code, correcting the spec's guesses):** M7 reuses the EXISTING `relationship.duplicate_spouse_order` (ConflictError → 409; `app/i18n/*.json:173`, raised at `validator.py:170`). M1 raises domain `ValidationError` (`app/domain/shared/exceptions.py:61` → 422 per `core/exceptions.py:106`) with a NEW code `relationship.divorce_before_marriage` (add to ALL FOUR locales; i18n coverage test enforces it).
- M1 create path is UNCHANGED (its pydantic `@model_validator` 422 stays). The update path yields the structured 422 — both are 422; the differing envelope is the app's established schema-validation-vs-domain-validation split, not an inconsistency.
- M7: `person1`/`person2` symmetry preserved — NO canonicalization, NO migration. The check only fires when `spouse_order is not None` and `status <> 'divorced'`.
- Accepted residuals (ADR-029, intentional): (a) a person can't be same-rank spouse in two simultaneous live marriages (polyandry over-reject — fine under polygyny); (b) concurrent-flip-race not DB-backstopped (rare; non-concurrent flip IS fixed).
- RED-first; full gate before done: `cd backend && uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports`.

---

### Task 1: RED — M1 update-block + M7 flip + controls

**Files:**
- Create: `backend/tests/integration/test_marriage_invariants.py`

**Interfaces:**
- Consumes: `migrated_db_url`; `MarriageCommandHandler` wiring (mirror the relationship suites — grep `tests/integration` for how they build `MarriageCommandHandler`/`RelationshipDomainValidator` over a real session).

- [ ] **Step 1: Write the tests.** Seed clan + persons (+ memberships). Helpers to create a marriage via the handler and PATCH via the update handler.

```python
# M1
async def test_marriage_create_still_blocks_divorce_before_marriage(...):
    # create with divorce_date < marriage_date → 422 (pydantic; regression pin, GREEN today)
async def test_marriage_update_blocks_divorce_before_marriage(...):
    # create married (marriage_date=1950); PATCH divorce_date=1940, status=divorced,
    # expected_version=1 → domain ValidationError relationship.divorce_before_marriage
    # (422). RED today: 200.
async def test_marriage_update_blocks_marriage_after_divorce(...):
    # create divorced (marriage 1950, divorce 1960); PATCH marriage_date=1970 → 422. RED today.
async def test_marriage_update_allows_valid_dates(...):
    # PATCH divorce_date after marriage_date → 200 (control).

# M7
async def test_spouse_order_flip_orientation_is_caught(...):
    # create (H, W1, order=1) → 201; create (W2, H, order=1) → relationship.duplicate_spouse_order
    # (409). RED today: 201 (person1-only check misses it).
async def test_da_the_distinct_orders_allowed(...):
    # (H, W1, 1) + (H, W2, 2) both 201 (control — legit đa thê).
async def test_spouse_order_update_flip_caught(...):
    # create (H,W1,1) + (W2,H,2); PATCH the second's spouse_order→1 → conflict (H would
    # have two order-1 across orientations); exclude-self: PATCH (H,W1,1) to order 1 → ok.
async def test_polyandry_same_rank_rejected_ADR029(...):
    # (H1, W1, 1) + (H2, W1, 1) → conflict. Docstring: intentional per ADR-029 (two-sided
    # invariant; acceptable under the polygyny model). Pins the accepted consequence.
async def test_divorced_marriage_excluded_from_spouse_order(...):
    # (H,W1,1 married) + (H,W2,1 status=divorced) → allowed (divorced leaves live set).
```

Discover the ACTUAL create-time 422 shape for the M1 create pin (pydantic `RequestValidationError` if created via HTTP, or the `ValueError` from `MarriageCreateRequest.validate_marriage` if constructing the schema) — mirror however the suite drives creates. Assert M7 conflicts by the `relationship.duplicate_spouse_order` code.

- [ ] **Step 2: Run — record RED.** Expected: `..._update_blocks_divorce_before_marriage`, `..._update_blocks_marriage_after_divorce`, `..._flip_orientation_is_caught`, `..._update_flip_caught`, `..._polyandry_same_rank_rejected` FAIL today; the create-pin + distinct-orders + divorced-excluded + valid-dates controls PASS. If a must-fail test passes, STOP → report BLOCKED.
- [ ] **Step 3: Commit** — `git commit -m "test: RED — marriage PATCH date order (M1) + two-sided spouse_order (M7)"`.

---

### Task 2: The fixes

**Files:**
- Modify: `backend/app/application/relationship/handlers.py` (`MarriageCommandHandler.update` — M1 date check; both create+update pass both ids to the spouse_order check)
- Modify: `backend/app/domain/relationship/validator.py` (`check_spouse_order` → two ids; the query-port protocol method it calls)
- Modify: `backend/app/infrastructure/persistence/relationship_repository.py` (`has_spouse_order_conflict` → two-sided SQL)
- Modify: `backend/app/domain/relationship/repository.py` (or wherever the query-port Protocol for `has_spouse_order_conflict` lives — grep it)
- Modify: `backend/app/i18n/{vi,en,zh,fr}.json` (`relationship.divorce_before_marriage`)

- [ ] **Step 1: M7 two-sided query** — `has_spouse_order_conflict` signature `(person_a, person_b, spouse_order, clan_id, exclude_marriage_id=None)`; SQL:

```sql
SELECT 1 FROM public.marriages
WHERE spouse_order = :so
  AND created_by_clan_id = :clan_id
  AND status <> 'divorced' AND is_deleted = false
  AND (person1_id IN (:a, :b) OR person2_id IN (:a, :b))
  AND (CAST(:exclude_id AS uuid) IS NULL OR id != :exclude_id)
LIMIT 1
```

(An existing live non-divorced marriage carrying `spouse_order = N` that touches either endpoint means adding this one would give that endpoint two order-N marriages → conflict.)

- [ ] **Step 2: Validator** — `check_spouse_order(person_a, person_b, spouse_order, clan_id, *, exclude_marriage_id=None)`: `if spouse_order is None: return`; else if `await self._q.has_spouse_order_conflict(person_a, person_b, spouse_order, clan_id, exclude_marriage_id)` raise `ConflictError("relationship.duplicate_spouse_order")`. Update the query-port Protocol signature to match.
- [ ] **Step 3: Handlers** — create (`MarriageCommandHandler.create`): `check_spouse_order(cmd.person1_id, cmd.person2_id, cmd.spouse_order, cmd.clan_id)`. update: `check_spouse_order(marriage.person1_id, marriage.person2_id, new_order, cmd.clan_id, exclude_marriage_id=marriage.id)`.
- [ ] **Step 4: M1** — in `MarriageCommandHandler.update`, before `marriage.update(...)`:

```python
        eff_marriage = cast("date | None", cmd.changes.get("marriage_date", marriage.marriage_date))
        eff_divorce = cast("date | None", cmd.changes.get("divorce_date", marriage.divorce_date))
        if eff_marriage and eff_divorce and eff_divorce < eff_marriage:
            raise ValidationError("relationship.divorce_before_marriage")
```

Import the domain `ValidationError` from `app.domain.shared.exceptions` (match the module's existing exception imports). Add `date` import if needed.

- [ ] **Step 5: i18n** — `"relationship.divorce_before_marriage"` in all four catalogs (vi: "Ngày ly hôn không được trước ngày kết hôn.", en: "Divorce date must not be earlier than the marriage date.", zh/fr faithful).
- [ ] **Step 6: Run** — Task-1 file all green; then relationship + tree + marriage suites; FULL suite (report count). mypy: check per-module overrides for the touched handler/repo modules.
- [ ] **Step 7: Commit** — `git commit -m "fix(relationships): enforce divorce>=marriage on PATCH (M1); two-sided spouse_order uniqueness (M7)"`.

---

### Task 3: ADR-029 + docs (grep-verified)

**Files:**
- Create: `docs/decisions/029-two-sided-spouse-order.md`
- Modify: `docs/decisions/README.md` (029 row)
- Modify: `docs/contracts/rest-relationships-api.md`

- [ ] **Step 1: ADR-029** (format of ADR-027): Context = M7 (person1-oriented check + symmetric model → flip creates two vợ cả) + M1 (PATCH date bypass). Decision = two-sided per-person spouse_order invariant (app-layer, both columns); divorce≥marriage on create AND update. Consequences = the flip is caught; the two accepted residuals (polyandry over-reject under the polygyny model; concurrent-flip-race not DB-backstopped, non-concurrent flip fixed, per-clan-advisory-lock trigger is the future option); no migration. Alternatives rejected = canonicalize orientation (needs gender + backfill migration).
- [ ] **Step 2: rest-relationships-api.md** — spouse_order uniqueness is per-person / orientation-independent (vợ cả/hai/ba can't be duplicated for a husband regardless of which side is person1); divorce_date ≥ marriage_date enforced on create AND update.
- [ ] **Step 3: Grep sweep** — `grep -rn "spouse_order\|divorce_date\|vợ cả\|person1" docs/contracts docs/architecture --include='*.md' | grep -v "review-2026-07-18\|superpowers"`; disposition each; commit — `git commit -m "docs: ADR-029 two-sided spouse_order + marriage date-order on update"`.

---

### Task 4: Full gate (controller-run)

- [ ] `cd backend && uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports` — all five green.
