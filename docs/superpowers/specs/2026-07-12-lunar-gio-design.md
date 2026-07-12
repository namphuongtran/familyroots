# Lunar giỗ Design Spec

**Date:** 2026-07-12
**Branch:** `feat/lunar-gio` (off `main` @ eed74f7)
**Purpose:** Make lunar-calendar anniversary reminders (ngày giỗ âm lịch) actually work.
Today the scheduler **skips** every `is_lunar_calendar = true` event
(`app/services/scheduler.py` filters `is_lunar_calendar = false` and only logs a
"deferred" count), and `/events/upcoming` computes a **wrong** `next_occurrence` for
lunar events (it applies the solar month/day anniversary formula). Giỗ in Vietnam is
overwhelmingly lunar — the flagship reminder feature is inert for its main use case.

**Owner decisions (2026-07-12):**
- Conversion engine: **implement the Vietnamese algorithm in-house** (Hồ Ngọc Đức's
  astronomical method, UTC+7). NO `lunardate`-style dependency — Chinese-calendar
  libraries (UTC+8) diverge from the Vietnamese calendar on boundary days and even
  leap months (e.g. Tết 1985, 2007); a wrong giỗ date is a serious cultural error.
- Giỗ conventions: **traditional standard** — (1) death in a leap month (tháng
  nhuận) → annual giỗ in the REGULAR month of the same number, every year, even in
  years that have that leap month again; (2) death on lunar day 30 → in years where
  that month has only 29 days, observe on day 29 (the month's last day).

---

## Item 1 — Lunar calendar engine (`app/services/lunar_calendar.py`)

Pure Python, zero dependencies, no framework imports. Hồ Ngọc Đức's astronomical
algorithm (Julian day number, new-moon calculation, sun longitude, month numbering
from the winter-solstice month), parameterized by timezone offset with default
`7.0` (Vietnam). Valid range at least 1900–2199 (covers genealogy + all recurrence).

### Public API
```python
@dataclass(frozen=True)
class LunarDate:
    year: int      # lunar year
    month: int     # 1..12
    day: int       # 1..30
    leap: bool     # this month is the leap month (tháng nhuận)

def solar_to_lunar(d: date, tz: float = 7.0) -> LunarDate
def lunar_to_solar(year: int, month: int, day: int, leap: bool = False, tz: float = 7.0) -> date
    # If (year, month, leap) does not exist (no such leap month) → falls back to the
    # regular month. If day exceeds the month's length (30 vs 29) → ValueError
    # (callers that need clamping use next_lunar_anniversary).
def next_lunar_anniversary(event_date: date, today: date, tz: float = 7.0) -> date
```

### `next_lunar_anniversary` semantics (mirrors the solar `next_anniversary_sql`)
1. `lunar = solar_to_lunar(event_date)` — the original death date in lunar terms.
2. Giỗ target each lunar year = `(lunar.month, lunar.day)` with the conventions:
   - **month**: always the REGULAR month (leap flag discarded — owner convention 1);
   - **day**: `min(lunar.day, days_in(lunar_year, month))` — clamps 30 → 29 in short
     months (owner convention 2).
3. Compute the solar date of that giỗ in the lunar year containing `today`; if the
   result is `< today`, compute it in the next lunar year. Return the first solar
   date `>= today`.
4. Deterministic pure function — no clock access; callers pass `today`.

### Placement & boundaries
`app/services/` (cross-cutting calendar math, same layer as `relationship_descriptor`).
Infrastructure (`event_repository`) and services (`scheduler`) may import it; no
import-linter contract forbids infra/services → services. It must NOT import
SQLAlchemy/FastAPI/Pydantic (pure stdlib: `math`, `datetime`, `dataclasses`).

### Testing (the core of this PR)
- **Table-driven known dates** (all publicly verifiable against Hồ Ngọc Đức's amlich
  / vietnamese calendar tables):
  - Tết (1/1 âm): 2023-01-22, 2024-02-10, 2025-01-29, 2026-02-17.
  - **VN/CN divergence years**: Tết 1985 = 1985-01-21 (VN, UTC+7; Chinese calendar
    gives 1985-02-20 — off by a month due to leap-month placement); 2007 boundary
    checks. These tests pin the UTC+7 correctness that rules out Chinese-calendar libs.
  - Giỗ tổ Hùng Vương (10/3 âm): 2024-04-18, 2025-04-07, 2026-04-26.
  - Leap-month round-trips: a date inside tháng 2 nhuận 2023 (lunar 2023 has leap
    month 2) converts to `leap=True` and back.
- **Round-trip property**: for every day in 1950–2050, `lunar_to_solar(solar_to_lunar(d)) == d`.
- **Convention tests**: death on (leap month 2, day 15) 2023 → giỗ in regular month 2
  of following years; death on lunar day 30 of a 30-day month → next year where that
  month has 29 days yields day 29.
- **Anniversary window tests**: `next_lunar_anniversary` returns today when today IS
  the giỗ; returns next lunar year's date when this year's has passed.

---

## Item 2 — Scheduler fires lunar giỗ

`app/services/scheduler.py`:
- Keep the existing solar SQL query unchanged (`is_lunar_calendar = false`).
- Replace the "count + skip" block with a second query selecting the same columns
  for `is_recurring = true AND is_lunar_calendar = true` (joined to persons the same
  way, no `next_occurrence` in SQL), then compute
  `next_occurrence = next_lunar_anniversary(event_date, today)` in Python.
- Feed solar + lunar rows through the SAME per-event loop (notify when
  `days_until == notify_days_before`, dedup on notification_log per day, per-event
  commit, per-event error isolation). Refactor the loop body only as far as needed
  to accept an iterable of `(event fields, next_occurrence)` from both sources.
- Remove the "lunar support deferred" log line.
- `today` remains the SCHEDULER_TIMEZONE-local date (Asia/Ho_Chi_Minh) — consistent
  with the UTC+7 lunar math.

## Item 3 — `/events/upcoming` computes lunar correctly

`app/infrastructure/persistence/event_repository.py::get_upcoming`:
- SQL: exclude lunar RECURRING events from the CTE's anniversary CASE (add
  `AND NOT (e.is_recurring AND e.is_lunar_calendar)` to the recurrence branch /
  WHERE as appropriate). Non-recurring events (lunar or not) keep
  `next_occurrence = event_date` — unchanged.
- Python: fetch the clan's lunar recurring events in a second small query, compute
  `next_occurrence` via `next_lunar_anniversary(event_date, today)`, keep only
  those with `today <= next_occurrence <= end_date`, merge with the SQL rows,
  sort by `next_occurrence`, apply `limit`.
- Response shape unchanged: `next_occurrence` stays a scalar ISO date (derived),
  `event_date` stays HistoricalDate, `is_lunar_calendar` already exposed.

## Item 4 — Docs in the same PR

- `docs/decisions/018-vietnamese-lunar-calendar.md` — ADR: in-house VN algorithm
  (UTC+7 rationale, rejected Chinese-calendar libs), giỗ conventions (leap month →
  regular month; day-30 clamp), scope (recurrence math only; display strings remain
  user-entered).
- `docs/decisions/README.md` — add row 018.
- `docs/architecture/notifications-scheduler.md` — remove the ⚠️ lunar-skipped
  banner; document the two-source (SQL solar + Python lunar) flow.
- `docs/contracts/push-notifications.md` — lunar giỗ reminders now fire; remove the
  ⚠️ note.
- `docs/contracts/rest-events-api.md` — note: for `is_lunar_calendar = true`
  recurring events, `next_occurrence` is the converted solar date of the next lunar
  anniversary (traditional conventions), computed with the Vietnamese calendar.

## Testing (integration, real Postgres)

- Scheduler: seed a lunar recurring giỗ whose next lunar anniversary is exactly
  `notify_days_before` days from an injected `today` → job run inserts a
  notification_log row; second run same day → deduped (no second row). A solar
  event in the same run still fires (regression). Mirror the fixture/injection
  style of the existing `tests/integration/test_anniversary_dates.py`.
- `/events/upcoming`: clan with one lunar recurring event → response's
  `next_occurrence` equals the engine-computed conversion (assert against a
  hard-coded known date, not by re-calling the engine); a lunar event outside the
  window is excluded; solar events unchanged; merged ordering correct.
- Full gate: `uv run pytest -q && uvx ruff check . && uvx ruff format --check . &&
  uv run mypy app/ tests/ && uv run lint-imports`.

## Explicitly NOT in this pass

Auto-generating `HistoricalDate.lunar` display strings from dates; per-clan
configurable giỗ conventions (clan_settings — revisit only on real demand); a full
lunar-calendar UI; backfilling reminders missed while lunar was skipped; changing
`is_lunar_calendar` write-path semantics (`event_date` remains the recorded solar
date of the original event).
