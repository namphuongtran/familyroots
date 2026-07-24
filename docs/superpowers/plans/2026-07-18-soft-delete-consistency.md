# Soft-Delete Consistency Sweep (A5) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A soft-deleted person is invisible on EVERY write path (marriages, parent-child, events, documents, branch founder) exactly as on read paths, and `/events/upcoming` matches the scheduler's deleted-person filter — closing review finding M3 + two sweep-found siblings. Spec: `docs/superpowers/specs/2026-07-18-soft-delete-consistency-design.md`.

**Architecture:** Pure predicate additions — each guard gains the persons-join `is_deleted = false` (the pattern `clan_repository.get_membership_with_person` set in A3); the two upcoming queries gain the scheduler's exact `(e.person_id IS NULL OR p.is_deleted = false)`. No error-code changes, no migration, no ADR (enforces the documented invisible-person rule).

**Tech Stack:** SQLAlchemy predicates; real-PG handler-level tests (pattern: `tests/integration/test_doi_authority.py` wiring; documents use the FakeStorage pattern from `tests/integration/test_clan_export_json.py`).

## Global Constraints

- **Error codes unchanged.** Each guard's caller keeps raising exactly what it raises today for a non-member person — verify per call site and pin it: relationship validator (`ensure_persons_in_clan` → its existing clan-invisible error), `event/handlers.py:69`, `document/handlers.py:80`, `branch/handlers.py:44,93` (all `person_not_found`-style — confirm codes from the handlers).
- Person-less events (`person_id IS NULL` — custom/clan ceremonies) MUST keep flowing through `/events/upcoming`; the new predicate must be the scheduler's exact form.
- Restore symmetry: every blocked operation succeeds again after `POST /persons/{id}/restore`-equivalent (handler-level restore is fine) with no other change.
- RED-first; full gate before done: `cd backend && uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports`.

---

### Task 1: RED — one test file covering all six holes + symmetry

**Files:**
- Create: `backend/tests/integration/test_soft_delete_consistency.py`

**Interfaces:**
- Consumes: `migrated_db_url`; handler wiring per aggregate (build each command handler over a real session the way its existing integration tests do — grep each aggregate's test file for the construction); FakeStorage for documents.

- [ ] **Step 1: Write the tests** (seed helpers mirroring `test_doi_authority.py`: clan, persons w/ memberships, `is_deleted` toggled by raw UPDATE):

```python
# Parametrized-by-surface core scenario, one test per surface for clear failure names:

async def test_marriage_creation_blocked_for_soft_deleted_person(...):
    # live H + deleted W → MarriageCommandHandler.create → the validator's existing
    # invisible-person error (pytest.raises, match the ACTUAL code — record it);
    # restore W (raw UPDATE is_deleted=false) → same create succeeds (201-equivalent).

async def test_parent_child_creation_blocked_for_soft_deleted_person(...):
    # deleted parent → blocked; restore → succeeds.

async def test_event_creation_blocked_for_soft_deleted_person(...):
    # EventCommandHandler.create with person_id = deleted person → blocked; restore → ok.

async def test_document_upload_blocked_for_soft_deleted_person(...):
    # DocumentCommandHandler.upload (FakeStorage) person_id = deleted → blocked;
    # restore → ok; assert NO blob was uploaded on the blocked path (FakeStorage.uploaded empty).

async def test_branch_founder_blocked_for_soft_deleted_person(...):
    # Branch create (and update — handlers.py:44 AND :93) with founder_person_id
    # = deleted person → blocked; restore → ok.

async def test_upcoming_hides_deleted_persons_gio_and_matches_scheduler(...):
    # Seed: recurring giỗ for X (will be deleted), recurring giỗ for live Y,
    # person-less clan ceremony. Soft-delete X.
    # /upcoming (EventQueryHandler.get_upcoming or the repo call — mirror
    # tests/integration/test_upcoming_lunar.py's invocation): X's event ABSENT,
    # X's name nowhere in the serialized payload (str-scan the response), Y's
    # present, person-less present. Scheduler parity: run the scheduler's query
    # path (or its repo equivalent — mirror test_scheduler_robustness.py's
    # approach) and assert the SAME event id set. Restore X → giỗ reappears.

async def test_get_birth_dates_excludes_deleted(...):
    # repo-level: deleted person id absent from the returned map.
```

- [ ] **Step 2: Run — record RED.** All blocked-path asserts FAIL today (creates succeed against deleted persons; upcoming shows X). Restore-symmetry positive controls pass. If any blocked-path test PASSES today, STOP: report BLOCKED (premise wrong for that surface).
- [ ] **Step 3: Commit** — `git commit -m "test: RED — writes target soft-deleted persons; /upcoming leaks their giỗ (M3)"`.

---

### Task 2: The fixes

**Files:**
- Modify: `backend/app/infrastructure/persistence/relationship_repository.py` (`persons_in_clan` +join persons is_deleted; `get_birth_dates` +filter)
- Modify: `backend/app/infrastructure/persistence/event_repository.py` (`person_in_clan` +join; both upcoming queries + the scheduler predicate)
- Modify: `backend/app/infrastructure/persistence/document_repository.py` (`person_in_clan` +join)
- Modify: `backend/app/infrastructure/persistence/branch_repository.py` (`person_in_clan` +join)

- [ ] **Step 1: Guards** — each becomes (adjust imports; relationship's is the list form):

```python
        stmt = (
            select(ClanMembership.person_id)
            .join(Person, Person.id == ClanMembership.person_id)
            .where(
                ClanMembership.person_id.in_(person_ids),   # or == person_id
                ClanMembership.clan_id == clan_id,
                Person.is_deleted.is_(False),
            )
        )
```

Update each guard's docstring: "a soft-deleted person is invisible here, matching the read-path definition (M3, review 2026-07-18)". `get_birth_dates` adds `PersonModel.is_deleted.is_(False)` + docstring line.

- [ ] **Step 2: Upcoming queries** — locate the persons join in BOTH the solar CTE and the lunar query inside `get_upcoming` (~:90-146) and add the scheduler's exact predicate `AND (e.person_id IS NULL OR p.is_deleted = false)` (match the query's actual aliases). Docstring: "mirrors scheduler.py's filter — /upcoming shows exactly what will be notified".
- [ ] **Step 3: Run** — Task-1 file all green ×3; then the neighbor suites (`test_upcoming_lunar.py`, `test_scheduler_robustness.py`, `test_anniversary_dates.py`, relationship/event/document/branch suites) and the FULL suite (report count; if an existing test seeded creates against deleted persons deliberately, update ONLY with justification).
- [ ] **Step 4: Commit** — `git commit -m "fix: soft-deleted persons are invisible to every write guard; /upcoming matches the scheduler (M3)"`.

---

### Task 3: The class gate + docs sync + full gate

**Files:**
- Modify: `backend/tests/integration/test_soft_delete_consistency.py` (append the gate test)
- Possibly: docs/contracts behavior notes (grep decides)

- [ ] **Step 1: Source-scan gate** (future-proofing — a NEW aggregate's guard can't silently omit the filter):

```python
def test_every_person_guard_filters_soft_deleted() -> None:
    """Source-scan gate: every person(s)_in_clan guard in the persistence layer
    must reference is_deleted. Catches the M3 class in FUTURE aggregates —
    runtime tests above prove today's five; this catches the sixth."""
    import inspect, re
    import app.infrastructure.persistence as persistence_pkg
    # iterate the package's modules; for each function named person_in_clan /
    # persons_in_clan, inspect.getsource and assert "is_deleted" in it, with a
    # failure message naming the module+function. (pkgutil.iter_modules +
    # importlib; skip private modules.)
```

Flesh it out; sabotage-verify once by mentally (or actually) removing one filter — the message must name the offender.
- [ ] **Step 2: Docs grep** — `grep -rn "soft-delete\|soft delete\|is_deleted\|upcoming" docs/contracts docs/architecture --include='*.md' | grep -v "review-2026-07-18\|superpowers"`: update any doc that says writes against deleted persons are possible or that /upcoming may show them (likely: rest-events-api.md upcoming notes, rest-relationships-api.md guard notes, domain-rules.md invisible-person rule gains "including all write guards — M3 closed"). Disposition every hit in the report.
- [ ] **Step 3: Full gate + commit** — `git commit -m "test: source-scan gate for person-guard soft-delete filters; docs sync"`.
