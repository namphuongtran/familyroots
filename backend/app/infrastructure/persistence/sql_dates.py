"""Leap-safe SQL date fragments shared by the anniversary job and event reads.

``MAKE_DATE(year, month, day)`` raises for Feb 29 in non-leap years — and one
such error aborts the WHOLE statement it appears in (C2,
seam-review-2026-07-04). These fragments never construct an invalid date:
they build day 1 of the month and add day-offsets, clamping to the month's
last day. Owner decision 2026-07-04: Feb-29 anniversaries observe Feb 28 in
non-leap years.
"""


def next_anniversary_sql(year_sql: str, date_col: str = "e.event_date") -> str:
    """SQL ``::date`` expression: the month/day of ``date_col`` in year
    ``year_sql``, clamped to that month's last day (Feb 29 → Feb 28).

    WARNING: this interpolates ``year_sql``/``date_col`` into the returned SQL
    via f-strings, unescaped. Callers MUST pass only code-level constants
    (e.g. ``"EXTRACT(YEAR FROM CURRENT_DATE)"``, ``"e.event_date"``) — never
    request-derived or otherwise untrusted input.
    """
    first_of_month = f"MAKE_DATE(({year_sql})::int, EXTRACT(MONTH FROM {date_col})::int, 1)"
    day_offset = f"(EXTRACT(DAY FROM {date_col})::int - 1) * INTERVAL '1 day'"
    last_of_month = f"({first_of_month} + INTERVAL '1 month' - INTERVAL '1 day')::date"
    return f"LEAST(({first_of_month} + {day_offset})::date, {last_of_month})"
