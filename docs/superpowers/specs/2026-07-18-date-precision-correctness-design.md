# Date-Precision Correctness (M4 + M5) — Design

**Date:** 2026-07-18
**Source findings:** M4 + M5 in `docs/architecture/backend-review-2026-07-18.md`.
**Principle enforced:** the HistoricalDate contract (ADR-011, CLAUDE.md) — an
estimated date (`precision != exact`) is display-only and must NOT drive a
computed/compared decision as if it were an exact point. This already governs
kinship age terms ("only when both birth dates are exact"); M4/M5 extend the same
rule to giỗ scheduling and the parent-age floor. No new ADR (enforcement of an
existing principle); no migration.
**Owner decision (M4):** record-but-don't-notify.

## The two holes

- **M4 — Giỗ computed from placeholder dates.** The scheduler's recurring-event
  queries (`scheduler.py:104-148`, solar + lunar) and `/events/upcoming`
  (`event_repository.get_upcoming`, solar CTE + lunar) select recurring events
  with NO `event_date_precision` filter, then compute a next anniversary from the
  raw `event_date`. A "khoảng 1950" (circa) death → a clan-wide FCM giỗ reminder
  on the fabricated Jan-1 lunar anniversary, every year.
- **M5 — `parent_too_young` treats circa as exact.** `get_birth_dates` returns
  only `date` (no precision); `validator.validate_parent_child` computes the
  gap and hard-blocks (`422 relationship.parent_too_young`) when a biological
  parent is < 12 years older — even when one/both birth dates are estimates, so a
  legitimate historical lineage with placeholder dates is rejected with no
  override.

## Design

### M4 — recurring notifications require an exact date

A recurring event generates notifications ONLY when `event_date_precision =
'exact'`. Add `AND e.event_date_precision = 'exact'` to:
- both scheduler recurring queries (solar `scheduler.py:~122`, lunar `~148`);
- both `/events/upcoming` queries (`event_repository.get_upcoming` solar CTE +
  lunar) — keeping the A5 invariant "`/upcoming` = exactly what will be
  notified" true (a non-exact recurring event fires no reminder, so it must not
  appear in upcoming either).

Consequences (documented, intentional):
- The event is still **stored** and shown on the person's timeline / event list
  with its `display` string ("khoảng 1950") — only the *reminder* is suppressed.
  Non-destructive.
- One-off (non-recurring) events are unaffected (they were never anniversary-
  computed). Person-less events with an exact date still notify.
- **`death_anniversary` for a person with no `death_date`:** OUT of scope as a
  hard rule — the giỗ's date lives on the EVENT (`event_date`), not derived from
  `person.death_date`, and many real ancestors have an unknown death date yet a
  known giỗ. Documented as a non-issue; the precision gate already prevents the
  fabricated-date reminder, which was the real defect.

### M5 — precision-aware parent-age floor

- `get_birth_dates` widens its return to carry precision: `dict[uuid, BirthDate]`
  where `BirthDate` is a small frozen dataclass `(value: date | None, precision:
  str)` (or a `(date|None, str)` tuple — implementation choice; the port Protocol
  updates to match). SQL selects `birth_date, birth_date_precision` (still
  filtering `is_deleted = false` per M3).
- `validate_parent_child`: compute `age_gap` as today. The biological < 12-year
  floor stays a **hard 422 `relationship.parent_too_young`** ONLY when BOTH
  birth dates have `precision == 'exact'`. If the gap is < 12 but either date is
  non-exact, downgrade to a non-blocking **warning** (the same
  `{"warning": ...}` channel `validate_parent_child` already returns for the
  > 80-year advisory) — the estimate can't justify a hard claim.
- **Ordering care (load-bearing):** the function still runs cycle detection AFTER
  the age checks. The < 12-non-exact warning must NOT early-return (that would
  skip cycle detection) — accumulate it in a local and return it at the end,
  after the cycle check, exactly as the > 80 advisory path must also continue to
  the cycle check. (Verify the current > 80 path doesn't skip the cycle check;
  if it does, that's a pre-existing bug to note, not silently inherit.)
- The > 80-year advisory is unchanged (already a warning). Warnings stay plain
  strings (matching the existing `relationship.unusual_age_gap` pattern —
  warnings are not i18n-keyed today; out of scope to change).

## Tests (real-DB; RED-first)

**M4** (scheduler + upcoming):
1. A recurring event with `event_date_precision = 'circa'` at the notify
   boundary → the scheduler sends NO notification and `/events/upcoming` does
   NOT list it. RED today (it notifies / appears). An otherwise-identical
   `precision = 'exact'` event → notifies + appears (positive control). Cover
   BOTH solar and lunar (`is_lunar_calendar` true/false).
2. Non-recurring + person-less-exact events unaffected (controls).
3. Scheduler parity: the precision-excluded event is absent from BOTH the
   scheduler's set and `/upcoming` (the A5 invariant holds).

**M5** (parent-age precision):
4. Biological parent < 12 yr older, BOTH birth dates exact → hard 422
   `relationship.parent_too_young` (regression pin, GREEN today).
5. Biological parent < 12 yr older, parent OR child birth date non-exact →
   NO 422; the edge is created with a `meta.warning`. RED today (hard-blocked).
6. Cycle detection still fires when the age check downgrades to a warning
   (seed a would-be cycle with a non-exact under-12 gap → still 409
   `relationship.creates_cycle`, proving the warning path didn't early-return).
7. Adoptive/step/foster under-12 unaffected (no age floor — existing behavior).

Existing event, scheduler, relationship, tree suites stay green.

## Docs

- `docs/architecture/domain-rules.md`: the precision rule now covers giỗ
  scheduling (recurring reminders need an exact date) and the parent-age floor
  (hard only when both exact, else advisory) — alongside the existing kinship
  clause.
- `docs/contracts/rest-events-api.md`: recurring notifications / `/upcoming`
  require `event_date_precision = 'exact'`; non-exact recurring events are
  recorded but never notified.
- `docs/contracts/rest-relationships-api.md`: `parent_too_young` is a hard 422
  only when both birth dates are exact, else a `meta.warning`.
- Grep sweep: `precision|circa|parent_too_young|upcoming|giỗ|anniversary` across
  docs/contracts + docs/architecture; per-hit dispositions.
