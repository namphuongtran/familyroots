"""Vietnamese lunar calendar engine — table-tested against publicly verifiable dates.

Sources: Hồ Ngọc Đức's amlich tables / Vietnamese official calendars. The 1985 case
pins UTC+7 correctness: Vietnam celebrated Tết Ất Sửu on 1985-01-21 while the
Chinese (UTC+8) calendar placed it on 1985-02-20 — a Chinese-calendar library
would fail this test by a month.
"""

from datetime import date, timedelta
from pathlib import Path

import pytest

from app.services.lunar_calendar import (
    SUPPORTED_MAX_YEAR,
    SUPPORTED_MIN_YEAR,
    LunarDate,
    lunar_to_solar,
    next_lunar_anniversary,
    solar_to_lunar,
)

# (solar, lunar year, month, day, leap)
KNOWN_DATES = [
    # Tết Nguyên Đán (1/1 âm)
    (date(2007, 2, 17), 2007, 1, 1, False),
    (date(2023, 1, 22), 2023, 1, 1, False),
    (date(2024, 2, 10), 2024, 1, 1, False),
    (date(2025, 1, 29), 2025, 1, 1, False),
    (date(2026, 2, 17), 2026, 1, 1, False),
    # VN/CN divergence: Tết Ất Sửu — Vietnam 1985-01-21 (China: 1985-02-20)
    (date(1985, 1, 21), 1985, 1, 1, False),
    # Giỗ tổ Hùng Vương (10/3 âm)
    (date(2019, 4, 14), 2019, 3, 10, False),
    (date(2024, 4, 18), 2024, 3, 10, False),
    (date(2025, 4, 7), 2025, 3, 10, False),
    (date(2026, 4, 26), 2026, 3, 10, False),
    # Inside tháng 2 nhuận 2023 (lunar 2023 has leap month 2): 2023-04-05 = 15/2 nhuận
    (date(2023, 4, 5), 2023, 2, 15, True),
    # Regular month 2 of the same year for contrast: 2023-03-06 = 15/2 thường
    (date(2023, 3, 6), 2023, 2, 15, False),
]


@pytest.mark.parametrize("solar, ly, lm, ld, leap", KNOWN_DATES)
def test_solar_to_lunar_known_dates(solar, ly, lm, ld, leap):
    assert solar_to_lunar(solar) == LunarDate(year=ly, month=lm, day=ld, leap=leap)


@pytest.mark.parametrize("solar, ly, lm, ld, leap", KNOWN_DATES)
def test_lunar_to_solar_known_dates(solar, ly, lm, ld, leap):
    assert lunar_to_solar(ly, lm, ld, leap) == solar


# Discovered by widening this test from 1950-2050 to the full 1910-2199 range: two
# calendar days where the raw new-moon instant lands a hair past local midnight, so the
# +0.5-day/tz rounding in `_new_moon_day` resolves the wrong month boundary by one day
# and `solar_to_lunar` would otherwise compute an impossible day (0). `solar_to_lunar`
# now fails loud on this (same principle as the range guard) instead of returning it;
# full 1910-2199 scan found exactly these two — no others.
KNOWN_NEW_MOON_BOUNDARY_ANOMALIES = {date(2054, 5, 7), date(2062, 4, 9)}


def test_new_moon_boundary_anomaly_dates_raise():
    for d in KNOWN_NEW_MOON_BOUNDARY_ANOMALIES:
        with pytest.raises(ValueError, match="boundary anomaly"):
            solar_to_lunar(d)


def test_round_trip_1910_2199():
    # Full supported range (~106k days, ~2s locally — not marked slow). 1900-1909 was
    # probed and found to have ~350 round-trip mismatches concentrated in 1900 itself
    # (algorithm epoch effects); 1910 onward is clean, hence SUPPORTED_MIN_YEAR=1910.
    d = date(SUPPORTED_MIN_YEAR, 1, 1)
    end = date(SUPPORTED_MAX_YEAR, 12, 31)
    while d <= end:
        if d in KNOWN_NEW_MOON_BOUNDARY_ANOMALIES:
            d += timedelta(days=1)
            continue
        lunar = solar_to_lunar(d)
        assert lunar_to_solar(lunar.year, lunar.month, lunar.day, lunar.leap) == d, d
        d += timedelta(days=1)


def test_lunar_to_solar_nonexistent_leap_month_falls_back_to_regular():
    # Lunar 2024 has no leap month 2 → leap=True falls back to the regular month.
    assert lunar_to_solar(2024, 2, 15, leap=True) == lunar_to_solar(2024, 2, 15, leap=False)


def test_lunar_to_solar_day_beyond_month_length_raises():
    # Lunar 2023 month 1 (Tết month) has only 29 days (2023-01-22..2023-02-19):
    # month 2 begins 2023-02-20 (derived from the verified 15/2/2023 = 2023-03-06
    # ground-truth entry above), so day 30 of month 1 does not exist.
    # NOTE: the brief's original pin here (month 2, day 30) was itself wrong —
    # lunar 2023 regular month 2 actually has 30 days (2023-02-20..2023-03-21),
    # immediately followed by leap month 2 (2023-03-22..2023-04-19); see
    # task-1-report.md for the correction.
    with pytest.raises(ValueError):
        lunar_to_solar(2023, 1, 30, leap=False)


# ── next_lunar_anniversary ────────────────────────────────────────────────


def test_anniversary_basic_this_lunar_year():
    # Death 2019-04-14 = 10/3 âm. Today 2025-04-01 → giỗ 2025-04-07.
    assert next_lunar_anniversary(date(2019, 4, 14), date(2025, 4, 1)) == date(2025, 4, 7)


def test_anniversary_on_the_day_returns_today():
    assert next_lunar_anniversary(date(2019, 4, 14), date(2025, 4, 7)) == date(2025, 4, 7)


def test_anniversary_passed_rolls_to_next_lunar_year():
    # Today 2025-04-08 (day after giỗ) → next occurrence 2026-04-26.
    assert next_lunar_anniversary(date(2019, 4, 14), date(2025, 4, 8)) == date(2026, 4, 26)


def test_anniversary_leap_month_death_observed_in_regular_month():
    # Death 2023-04-05 = 15/2 NHUẬN 2023. Convention: giỗ in REGULAR month 2.
    # Lunar 2024 month 2 day 15 = 2024-03-24.
    assert lunar_to_solar(2024, 2, 15, False) == date(2024, 3, 24)  # pin the target
    assert next_lunar_anniversary(date(2023, 4, 5), date(2024, 3, 1)) == date(2024, 3, 24)


def test_anniversary_day30_clamps_to_29_in_short_month():
    # Find a death on lunar day 30, then a year where that month has 29 days:
    # 30/2 âm 2023 (regular month 2 has 29 days → does not exist).
    # Use 30/4 âm: lunar 2023 month 4 has 30 days → 30/4/2023 = solar 2023-06-17.
    d30 = lunar_to_solar(2023, 4, 30, False)
    assert solar_to_lunar(d30) == LunarDate(2023, 4, 30, False)
    # Lunar 2024 month 4 has 29 days (30/4/2024 does not exist) → giỗ = 29/4 âm 2024.
    with pytest.raises(ValueError):
        lunar_to_solar(2024, 4, 30, False)
    expected = lunar_to_solar(2024, 4, 29, False)
    assert next_lunar_anniversary(d30, date(2024, 5, 1)) == expected


# ── fail-loud domain guard (pre-merge review, Finding 1) ────────────────────
# Outside SUPPORTED_MIN_YEAR..SUPPORTED_MAX_YEAR the algorithm silently returns
# wrong dates (e.g. negative lunar days) instead of raising — a plausible-looking
# but WRONG result is worse than a loud failure for a giỗ reminder date.


def test_solar_to_lunar_rejects_pre_1910():
    with pytest.raises(ValueError, match="1890-01-21"):
        solar_to_lunar(date(1890, 1, 21))


def test_solar_to_lunar_rejects_post_2199():
    with pytest.raises(ValueError):
        solar_to_lunar(date(2200, 1, 1))


def test_next_lunar_anniversary_rejects_pre_1910_event_date():
    # Proven pre-fix bug: this used to return a plausible-but-wrong 2025-02-22
    # with no exception (negative lunar day bypassed the day-length guard).
    with pytest.raises(ValueError):
        next_lunar_anniversary(date(1890, 3, 15), date(2025, 1, 1))


def test_lunar_to_solar_rejects_negative_day():
    with pytest.raises(ValueError):
        lunar_to_solar(2023, 2, -5)


def test_lunar_to_solar_rejects_month_out_of_range():
    with pytest.raises(ValueError):
        lunar_to_solar(2023, 13, 1)
    with pytest.raises(ValueError):
        lunar_to_solar(2023, 0, 1)


def test_lunar_to_solar_rejects_year_out_of_range():
    with pytest.raises(ValueError):
        lunar_to_solar(1890, 1, 1)
    with pytest.raises(ValueError):
        lunar_to_solar(2200, 1, 1)


def test_boundary_years_do_not_raise():
    # SUPPORTED_MIN_YEAR/SUPPORTED_MAX_YEAR are inclusive.
    solar_to_lunar(date(SUPPORTED_MIN_YEAR, 1, 1))
    solar_to_lunar(date(SUPPORTED_MAX_YEAR, 12, 31))


def test_engine_is_pure_stdlib():
    import app.services.lunar_calendar as m

    banned = ("sqlalchemy", "fastapi", "pydantic")
    src = Path(m.__file__).read_text(encoding="utf-8")
    assert not any(f"import {b}" in src or f"from {b}" in src for b in banned)
