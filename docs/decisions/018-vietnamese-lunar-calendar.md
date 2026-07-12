# ADR-018: In-House Vietnamese Lunar Calendar Engine for Giỗ Recurrence

## Status
Accepted (2026-07-12 — shipped)

## Context
Giỗ (ngày giỗ âm lịch — the annual lunar-calendar death anniversary) is the
platform's flagship reminder feature, and giỗ in Vietnam is overwhelmingly tracked
by the lunar calendar, not the solar one. Before this change the scheduler
hard-filtered `is_lunar_calendar = false` and only logged a count of skipped lunar
events ("lunar support deferred"), and `/events/upcoming` applied the solar
month/day anniversary formula to lunar-flagged events, producing a wrong
`next_occurrence`. The flagship notification was inert for its main use case, and
the read model actively lied about when a lunar giỗ would next fall.

Two engine choices were considered:
- **A Chinese-calendar library** (e.g. a `lunardate`-style package). These compute
  the lunar calendar at the Chinese meridian (UTC+8). The Vietnamese calendar
  (UTC+7) diverges from the Chinese calendar on boundary days and — more
  seriously — occasionally places its leap month in a different lunar month
  entirely. The canonical example is Tết (lunar new year) 1985: the Vietnamese
  calendar puts Tết on 1985-01-21, while the Chinese calendar's leap-month
  placement shifts its new year to 1985-02-20 — a full month off. For a
  cultural/religious date like giỗ, a wrong month is not a rounding error, it's a
  serious correctness failure that would misinform a family about when to hold
  the ceremony.
- **An in-house implementation of Hồ Ngọc Đức's astronomical algorithm**,
  parameterized by timezone offset with `tz=7.0` (Vietnam) as the default. This is
  the same method used by Vietnam's canonical amlich/lunar calendar references and
  is verifiable against publicly published Vietnamese calendar tables.

## Decision
- Implement the conversion engine in-house at `backend/app/services/lunar_calendar.py`:
  pure stdlib (`math`, `datetime`, `dataclasses`), zero third-party dependencies, no
  framework imports (no SQLAlchemy/FastAPI/Pydantic) — placed in `app/services/` as
  cross-cutting calendar math, the same layer as `relationship_descriptor`.
  Rejected Chinese-calendar libraries for the UTC+7 vs UTC+8 boundary-day and
  leap-month divergence above (Tết 1985 pins the correctness case in tests).
  All computations use `tz=7.0` by default.
- Public API: `LunarDate(year, month, day, leap)`, `solar_to_lunar(d, tz=7.0)`,
  `lunar_to_solar(year, month, day, leap=False, tz=7.0)` (a leap flag for a month
  with no leap counterpart falls back to the regular month; a day beyond the
  month's length raises `ValueError`), and `next_lunar_anniversary(event_date,
  today, tz=7.0)` — a deterministic pure function (no clock access; callers pass
  `today`) mirroring the semantics of the existing solar `next_anniversary_sql`.
- **Supported range is `SUPPORTED_MIN_YEAR = 1910` .. `SUPPORTED_MAX_YEAR = 2199`
  (fail-loud, pre-merge review)**. The algorithm's round-trip identity
  (`lunar_to_solar(solar_to_lunar(d)) == d`) is only reliable in this window —
  1900-1909 has ~350 round-trip mismatches concentrated in 1900 itself (the
  Meeus new-moon approximation is anchored at the 1900-01-01 epoch and degrades
  near/before it). Outside the window the arithmetic used to silently return an
  implausible result instead of raising — e.g. `solar_to_lunar(date(1890, 1,
  21))` returned `LunarDate(1890, 1, -28)` (a negative day), and that negative day
  bypassed `lunar_to_solar`'s month-length guard, so
  `next_lunar_anniversary(date(1890, 3, 15), date(2025, 1, 1))` returned a
  plausible-but-WRONG `2025-02-22` with no exception. Every public entry point
  now validates its year (`solar_to_lunar` on `d.year`; `lunar_to_solar` on the
  `year` param, tolerating `SUPPORTED_MIN_YEAR - 1` because Tết falls in Jan/Feb
  so early-January solar dates in `SUPPORTED_MIN_YEAR` convert to that trailing
  lunar year — verified round-trip clean) and raises `ValueError` outside
  1910-2199; `lunar_to_solar` additionally rejects `month` outside `1..12` and
  `day < 1` (closing off the negative-day bypass at its source, not just at the
  month-length check). Pre-1910 ancestor giỗ support is a follow-up (would need
  an epoch-extended algorithm), not covered here.
- **Giỗ conventions** (owner decision, traditional Vietnamese practice), applied
  inside `next_lunar_anniversary`:
  1. **Leap month → regular month.** If the original death fell in a leap month
     (tháng nhuận), the annual giỗ is observed every year in the REGULAR month of
     the same number — never re-observed specially in a later year that happens
     to have that leap month again. The leap flag is discarded when computing the
     recurring target.
  2. **Day-30 clamp.** If the death fell on lunar day 30, then in a lunar year
     where that month has only 29 days, the giỗ is observed on day 29 (the
     month's last day) instead of failing or rolling to the next month.
- **Computation is in Python, not SQL, and lazy per-event.** Solar anniversaries
  stay a SQL date-arithmetic CASE (`next_anniversary_sql`) because that math is
  cheap and cannot raise. Lunar anniversaries run the astronomical algorithm,
  which is expensive and CAN raise on a pathological date, so it is computed
  lazily, per event, inside the per-event try/except in both call sites:
  - `app/services/scheduler.py::send_anniversary_notifications` — the solar SQL
    query is unchanged; a second query fetches `is_lunar_calendar = true`
    recurring rows with only `event_date` (no `next_occurrence` from SQL). Solar
    and lunar rows are merged into one iterable and fed through the same
    per-event loop (notify-gate, dedup, per-event commit, per-event error
    isolation). `next_lunar_anniversary` is called *inside* that per-event try,
    so one bad lunar row rolls back and continues instead of aborting the run
    before any event — solar or lunar — is processed.
  - `app/infrastructure/persistence/event_repository.py::get_upcoming` — the CTE
    excludes lunar recurring events (`AND NOT (e.is_recurring AND
    e.is_lunar_calendar)`) from the solar CASE; a second query fetches the clan's
    lunar recurring events, computes `next_occurrence` in Python via
    `next_lunar_anniversary`, filters to `today <= next_occurrence <= end_date`,
    and merges with the SQL rows before sorting by `next_occurrence` and applying
    `limit`. Non-recurring events (lunar or not) are unaffected —
    `next_occurrence = event_date` as before. A per-row `ValueError` (e.g. a
    pre-1910 `event_date`) is caught and logged (`logger.warning`) and that row is
    skipped — one pathological lunar event must not 500 the whole
    `/events/upcoming` response for the rest of the clan's events.
- **Scope is recurrence math only.** This ADR covers computing *when* the next
  lunar anniversary falls. It does **not** touch `HistoricalDate.lunar` (the
  display-only string on person/event date responses, e.g. `"15/08 Nhâm Tý"`) —
  those remain stored, user-entered text (ADR-011), never derived from this
  engine. It also does not touch `event_date` write-path semantics: `event_date`
  on a lunar-flagged event still records the original event's solar date; the
  engine converts it to/from lunar terms purely for recurrence math.

## Consequences
Easier: giỗ âm lịch reminders now fire — the platform's primary notification use
case works for its primary calendar. `/events/upcoming` reports the correct
converted solar date for lunar recurring events instead of silently applying the
wrong (solar) formula. The engine is a small, dependency-free, unit-testable pure
function, verifiable against publicly published Vietnamese calendar tables and
regression-pinned against the VN/Chinese calendar divergence (Tết 1985, 2007
boundary cases) and round-trip properties (`lunar_to_solar(solar_to_lunar(d)) ==
d` for the full supported range, 1910-2199 — widened from an earlier 1950-2050
during the pre-merge review; see Finding 1 above for why 1910 is the floor).
Outside that range, every entry point now fails loud (`ValueError`) instead of
returning a plausible-but-wrong date.

Harder: the lunar path costs one extra query per call site (scheduler,
`get_upcoming`) plus a Python-side merge/sort instead of a single SQL statement —
acceptable because lunar recurring events are a small fraction of rows and the
conversion cannot be expressed as SQL date arithmetic. The giỗ conventions
(leap-month → regular month, day-30 clamp) are a fixed platform-wide rule, not
configurable per clan; a clan wanting a different convention (e.g. always
re-observing in the leap month when it recurs) needs a follow-up
`clan_settings`-scoped decision, not covered here. `HistoricalDate.lunar` display
strings still are not auto-derived from `event_date`/`birth_date`/`death_date` via
this engine — a clan must still type the lunar display string by hand; wiring
auto-generation is explicitly out of scope for this pass.
