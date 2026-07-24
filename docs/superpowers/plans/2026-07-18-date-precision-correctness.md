# Date-Precision Correctness (M4 + M5) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recurring giỗ/birthday notifications fire only on exact dates (M4 — no fabricated-anniversary FCM), and the biological parent-age floor is a hard error only when both birth dates are exact, else advisory (M5). Enforces ADR-011 (HistoricalDate: estimates are display-only). Spec: `docs/superpowers/specs/2026-07-18-date-precision-correctness-design.md`. No migration, no new ADR.

**Architecture:** M4 — add an `event_date_precision`-exact predicate to both scheduler recurring queries and both `/events/upcoming` queries (scoped to recurring in the mixed solar CTE). M5 — `get_birth_dates` returns date+precision; `validate_parent_child` downgrades the <12 floor to a warning when either date is non-exact, and (side-fix) the warning paths now continue to cycle detection instead of early-returning.

**Tech Stack:** SQLAlchemy async raw SQL, real-PG integration tests (patterns: `test_upcoming_lunar.py`, `test_scheduler_robustness.py`, existing relationship-validator suites).

## Global Constraints

- **M4 precision gate is RECURRING-scoped.** Scheduler: both queries are already `is_recurring = true` → add `AND e.event_date_precision = 'exact'` to each. `/events/upcoming`: the solar CTE ALSO carries one-off future events (`is_recurring OR event_date >= today`) — a one-off event with a non-exact date is a real upcoming date and must STILL appear; so gate recurring only: `AND NOT (e.is_recurring = true AND e.event_date_precision <> 'exact')`. The upcoming lunar query is all-recurring → plain `AND e.event_date_precision = 'exact'`.
- Non-exact recurring events remain stored + shown on timelines/lists (only the reminder + the upcoming-recurring listing are suppressed). One-off events (any precision) and person-less exact events unaffected.
- **M5 warnings use the EXISTING `{"warning": <plain str>}` channel** `validate_parent_child` already returns (warnings are not i18n-keyed today — match the existing `>80` string style; do not add i18n). `<12`-exact stays hard `BusinessRuleViolation("relationship.parent_too_young")` (422). `<12`-non-exact and `>80` are warnings.
- **Cycle detection must run on the warning path** (fixes the pre-existing `>80` early-return-skips-cycle bug): accumulate the warning in a local, run the cycle check, return `{"warning": w}` at the end. `<12` and `>80` are mutually exclusive (no clobber).
- RED-first; full gate before done: `cd backend && uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports`.

---

### Task 1: RED — M4 (scheduler + upcoming) and M5 (parent-age precision)

**Files:**
- Create: `backend/tests/integration/test_date_precision.py`

**Interfaces:**
- Consumes: `migrated_db_url`; scheduler invocation pattern from `test_scheduler_robustness.py` (`send_anniversary_notifications` + FCM monkeypatch); upcoming pattern from `test_upcoming_lunar.py`; relationship-validator wiring from the existing relationship suites.

- [ ] **Step 1: Write the tests.**

M4:
```python
async def test_recurring_circa_event_is_not_notified_and_not_in_upcoming(...):
    # seed a recurring event (solar) with event_date_precision='circa' positioned at
    # the notify boundary + a live person. Run the scheduler → NO send for it
    # (monkeypatched send_to_clan / send_each records zero calls for this event).
    # GET /events/upcoming → the circa recurring event is ABSENT.
    # RED today: it notifies / appears.
async def test_recurring_exact_event_notifies_and_appears(...):
    # identical but precision='exact' → notified + present (positive control, GREEN today).
async def test_recurring_lunar_circa_excluded(...):
    # is_lunar_calendar=true + precision='circa' recurring → not notified, not in upcoming.
async def test_oneoff_circa_future_event_still_in_upcoming(...):
    # is_recurring=false, precision='circa', event_date in the future → STILL appears in
    # /upcoming (one-offs are unaffected by the recurring precision gate). GREEN today;
    # this pins that M4 does NOT over-filter one-offs.
```

M5 (drive `validate_parent_child` via the relationship create path or the validator directly, mirroring the existing validator tests):
```python
async def test_parent_too_young_hard_when_both_birth_dates_exact(...):
    # bio parent 5 yr older, both birth_date_precision='exact' → 422
    # relationship.parent_too_young (regression pin, GREEN today).
async def test_parent_too_young_downgraded_to_warning_when_nonexact(...):
    # bio parent 5 yr older, parent birth_date_precision='circa' → edge CREATED (no 422),
    # response/meta carries a warning. RED today (hard-blocked).
async def test_cycle_still_detected_when_age_downgraded_to_warning(...):
    # A parent-of B (ok); attempt B parent-of A (would cycle) with a <12 gap and a
    # non-exact date → still 409 relationship.creates_cycle (proves the warning path
    # does NOT early-return before cycle detection). RED today IF the impl early-returns;
    # today the hard-422 fires first so it's a different failure — assert the FINAL
    # desired behavior (409 cycle) and note the today-state in the docstring.
async def test_adoptive_under_12_still_allowed(...):
    # adopted parent 5 yr older → no age floor (existing behavior; control).
```

Discover how the suite surfaces `validate_parent_child`'s warning (meta.warning on the create response, or the returned dict) and assert accordingly.

- [ ] **Step 2: Run — record RED.** Expected fails: the two M4 circa tests (solar+lunar), the M5 non-exact-warning test; possibly the cycle test (document its today-state). Controls (exact-notifies, one-off-circa-in-upcoming, both-exact-hard, adoptive) pass. If a must-fail passes, STOP → BLOCKED.
- [ ] **Step 3: Commit** — `git commit -m "test: RED — recurring giỗ on non-exact dates (M4); parent_too_young precision (M5)"`.

---

### Task 2: The fixes

**Files:**
- Modify: `backend/app/services/scheduler.py` (both recurring queries)
- Modify: `backend/app/infrastructure/persistence/event_repository.py` (`get_upcoming` solar CTE + lunar query)
- Modify: `backend/app/infrastructure/persistence/relationship_repository.py` (`get_birth_dates` → date+precision)
- Modify: `backend/app/domain/relationship/validator.py` (the `get_birth_dates` port Protocol signature + `validate_parent_child` precision logic + cycle-ordering fix) + a `BirthDate` type
- Possibly: wherever the `BirthDate` dataclass best lives (domain/relationship)

- [ ] **Step 1: M4 scheduler** — add `AND e.event_date_precision = 'exact'` to both the solar recurring query (`scheduler.py:~122`) and the lunar recurring query (`~148`).
- [ ] **Step 2: M4 upcoming** — in `event_repository.get_upcoming`: solar CTE (`~120`) add `AND NOT (e.is_recurring = true AND e.event_date_precision <> 'exact')`; lunar query (`~148-151`) add `AND e.event_date_precision = 'exact'`.
- [ ] **Step 3: M5 birth-date+precision** — define `@dataclass(frozen=True) class BirthDate: value: date | None; precision: str` (domain/relationship, near the port). `get_birth_dates` (repository) selects `birth_date, birth_date_precision` (keep the `is_deleted = false` filter) and returns `dict[uuid, BirthDate]`. Update the port Protocol return type in `validator.py`.
- [ ] **Step 4: M5 validator** — rewrite the age block in `validate_parent_child`:

```python
        parent = dates.get(parent_id)
        child = dates.get(child_id)
        parent_bd = parent.value if parent else None
        child_bd = child.value if child else None
        both_exact = bool(parent and child and parent.precision == "exact" and child.precision == "exact")
        age_gap = (child_bd - parent_bd).days / 365.25 if parent_bd and child_bd else None

        warning: str | None = None
        if relationship_type == "biological":
            bio_count = await self._q.count_bio_parents(child_id, clan_id, exclude_link_id)
            if bio_count >= 2:
                raise ConflictError("relationship.too_many_biological_parents")
            if age_gap is not None and age_gap < 12:
                if both_exact:
                    raise BusinessRuleViolation(
                        "relationship.parent_too_young",
                        detail={"min_age_gap": 12, "actual": round(age_gap, 1)},
                    )
                # non-exact: an estimate can't justify a hard block (ADR-011) — advise only
                warning = f"Parent only {round(age_gap, 1)} years older than child (dates approximate)"
        if age_gap is not None and age_gap > 80:
            warning = f"Unusual age gap: {round(age_gap, 1)} years"
        if check_cycle and await self._q.is_ancestor(parent_id, child_id, clan_id):
            raise BusinessRuleViolation("relationship.creates_cycle")
        return {"warning": warning} if warning else None
```

This ALSO fixes the pre-existing bug where the `>80` path returned early and skipped cycle detection (note it in the report).

- [ ] **Step 5: Run** — Task-1 file green; then `test_scheduler_robustness.py`, `test_upcoming_lunar.py`, `test_anniversary_dates.py`, the relationship-validator suites, tree; FULL suite (report count). mypy: check per-module overrides. If an existing scheduler/upcoming test seeded a recurring event without setting precision, it defaults to 'exact' (migration 012 default) so it stays notified — verify no existing test relied on a non-exact recurring event notifying.
- [ ] **Step 6: Commit** — `git commit -m "fix: recurring notifications require exact dates (M4); precision-aware parent_too_young + cycle-order fix (M5)"`.

---

### Task 3: Docs (grep-verified)

**Files:**
- Modify: `docs/architecture/domain-rules.md`
- Modify: `docs/contracts/rest-events-api.md`
- Modify: `docs/contracts/rest-relationships-api.md`

- [ ] **Step 1: Grep** — `grep -rn "precision\|circa\|parent_too_young\|upcoming\|anniversary\|giỗ\|recurring" docs/contracts docs/architecture --include='*.md' | grep -v "review-2026-07-18\|superpowers"`. Disposition each.
- [ ] **Step 2: Edits** — domain-rules.md: the precision rule now also governs giỗ scheduling (recurring reminders require an exact date; non-exact recurring events are recorded but not notified) and the parent-age floor (hard 422 only when both birth dates exact, else advisory). rest-events-api.md: `/events/upcoming` + notifications exclude non-exact RECURRING events (one-off events unaffected). rest-relationships-api.md: `parent_too_young` hard only when both exact, else `meta.warning`. Reference ADR-011 + the M4/M5 review findings.
- [ ] **Step 3: Re-run grep; zero stale statements. Commit** — `git commit -m "docs: precision governs giỗ notifications (M4) + parent-age floor (M5)"`.

---

### Task 4: Full gate (controller-run)

- [ ] `cd backend && uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports` — all five green.
