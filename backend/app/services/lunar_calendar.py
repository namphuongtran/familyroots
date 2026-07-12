"""Vietnamese lunar calendar (âm lịch) conversion — Hồ Ngọc Đức's algorithm.

Pure stdlib, no framework imports. All computations use the Vietnamese meridian
(UTC+7, ``tz=7.0``) — the Vietnamese calendar diverges from the Chinese (UTC+8)
on boundary days and occasionally by a whole leap month (e.g. Tết 1985).

Giỗ conventions (owner decision 2026-07-12, ADR-018):
- death in a leap month (tháng nhuận) → annual giỗ in the REGULAR month;
- death on lunar day 30 → day 29 in years where that month has only 29 days.

Algorithm: Hồ Ngọc Đức, "Thuật toán tính âm lịch" — new-moon and sun-longitude
approximations (Jean Meeus, Astronomical Algorithms), month numbering anchored
to the month containing the winter solstice (tháng 11 âm).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

_LUNAR_MONTH = 29.530588853  # mean synodic month, days


@dataclass(frozen=True)
class LunarDate:
    year: int
    month: int  # 1..12
    day: int  # 1..30
    leap: bool  # this month is the leap month (tháng nhuận)


def _jd_from_date(dd: int, mm: int, yy: int) -> int:
    """Julian day number of calendar date (proleptic Gregorian/Julian switch 1582)."""
    a = (14 - mm) // 12
    y = yy + 4800 - a
    m = mm + 12 * a - 3
    jd = dd + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045
    if jd < 2299161:
        jd = dd + (153 * m + 2) // 5 + 365 * y + y // 4 - 32083
    return jd


def _jd_to_date(jd: int) -> tuple[int, int, int]:
    """Inverse of _jd_from_date → (dd, mm, yy)."""
    if jd > 2299160:
        a = jd + 32044
        b = (4 * a + 3) // 146097
        c = a - (b * 146097) // 4
    else:
        b = 0
        c = jd + 32082
    d = (4 * c + 3) // 1461
    e = c - (1461 * d) // 4
    m = (5 * e + 2) // 153
    dd = e - (153 * m + 2) // 5 + 1
    mm = m + 3 - 12 * (m // 10)
    yy = b * 100 + d - 4800 + m // 10
    return dd, mm, yy


def _new_moon(k: int) -> float:
    """Julian day (UT) of the k-th new moon after 1900-01-01 (Meeus)."""
    t = k / 1236.85
    t2, t3 = t * t, t * t * t
    dr = math.pi / 180
    jd1 = 2415020.75933 + 29.53058868 * k + 0.0001178 * t2 - 0.000000155 * t3
    jd1 += 0.00033 * math.sin((166.56 + 132.87 * t - 0.009173 * t2) * dr)
    m = 359.2242 + 29.10535608 * k - 0.0000333 * t2 - 0.00000347 * t3
    mpr = 306.0253 + 385.81691806 * k + 0.0107306 * t2 + 0.00001236 * t3
    f = 21.2964 + 390.67050646 * k - 0.0016528 * t2 - 0.00000239 * t3
    c1 = (0.1734 - 0.000393 * t) * math.sin(m * dr) + 0.0021 * math.sin(2 * dr * m)
    c1 += -0.4068 * math.sin(mpr * dr) + 0.0161 * math.sin(dr * 2 * mpr)
    c1 += -0.0004 * math.sin(dr * 3 * mpr)
    c1 += 0.0104 * math.sin(dr * 2 * f) - 0.0051 * math.sin(dr * (m + mpr))
    c1 += -0.0074 * math.sin(dr * (m - mpr)) + 0.0004 * math.sin(dr * (2 * f + m))
    c1 += -0.0004 * math.sin(dr * (2 * f - m)) - 0.0006 * math.sin(dr * (2 * f + mpr))
    c1 += 0.0010 * math.sin(dr * (2 * f - mpr)) + 0.0005 * math.sin(dr * (2 * mpr + m))
    deltat: float
    if t < -11:
        deltat = 0.001 + 0.000839 * t + 0.0002261 * t2 - 0.00000845 * t3 - 0.000000081 * t * t3
    else:
        deltat = -0.000278 + 0.000265 * t + 0.000262 * t2
    return jd1 + c1 - deltat


def _new_moon_day(k: int, tz: float) -> int:
    """Local-midnight-truncated day of the k-th new moon."""
    return int(_new_moon(k) + 0.5 + tz / 24)


def _sun_longitude(jdn: int, tz: float) -> int:
    """Sun-longitude section (0..11; each = 30°) at local midnight of day jdn."""
    t = (jdn - 2451545.5 - tz / 24) / 36525
    t2 = t * t
    dr = math.pi / 180
    m = 357.52910 + 35999.05030 * t - 0.0001559 * t2 - 0.00000048 * t * t2
    l0 = 280.46645 + 36000.76983 * t + 0.0003032 * t2
    dl = (1.914600 - 0.004817 * t - 0.000014 * t2) * math.sin(dr * m)
    dl += (0.019993 - 0.000101 * t) * math.sin(dr * 2 * m) + 0.000290 * math.sin(dr * 3 * m)
    lon = (l0 + dl) * dr
    lon -= math.pi * 2 * math.floor(lon / (math.pi * 2))
    return int(lon / math.pi * 6)


def _lunar_month_11(yy: int, tz: float) -> int:
    """New-moon day starting tháng 11 âm of year yy (the month containing the
    winter solstice, sun longitude section 9)."""
    off = _jd_from_date(31, 12, yy) - 2415021
    k = int(off / _LUNAR_MONTH)
    nm = _new_moon_day(k, tz)
    if _sun_longitude(nm, tz) >= 9:
        nm = _new_moon_day(k - 1, tz)
    return nm


def _leap_month_offset(a11: int, tz: float) -> int:
    """Offset (1..13) from tháng-11 to the leap month in a 13-month lunar year:
    the first month during which the sun stays in one longitude section."""
    k = int((a11 - 2415021.076998695) / _LUNAR_MONTH + 0.5)
    last = 0
    i = 1
    arc = _sun_longitude(_new_moon_day(k + i, tz), tz)
    while True:
        last = arc
        i += 1
        arc = _sun_longitude(_new_moon_day(k + i, tz), tz)
        if arc == last or i >= 14:
            break
    return i - 1


def solar_to_lunar(d: date, tz: float = 7.0) -> LunarDate:
    dd, mm, yy = d.day, d.month, d.year
    day_number = _jd_from_date(dd, mm, yy)
    k = int((day_number - 2415021.076998695) / _LUNAR_MONTH)
    month_start = _new_moon_day(k + 1, tz)
    if month_start > day_number:
        month_start = _new_moon_day(k, tz)
    a11 = _lunar_month_11(yy, tz)
    b11 = a11
    if a11 >= month_start:
        lunar_year = yy
        a11 = _lunar_month_11(yy - 1, tz)
    else:
        lunar_year = yy + 1
        b11 = _lunar_month_11(yy + 1, tz)
    lunar_day = day_number - month_start + 1
    diff = int((month_start - a11) / 29)
    lunar_leap = False
    lunar_month = diff + 11
    if b11 - a11 > 365:
        leap_diff = _leap_month_offset(a11, tz)
        if diff >= leap_diff:
            lunar_month = diff + 10
            if diff == leap_diff:
                lunar_leap = True
    if lunar_month > 12:
        lunar_month -= 12
    if lunar_month >= 11 and diff < 4:
        lunar_year -= 1
    return LunarDate(year=lunar_year, month=lunar_month, day=lunar_day, leap=lunar_leap)


def lunar_to_solar(year: int, month: int, day: int, leap: bool = False, tz: float = 7.0) -> date:
    """Solar date of a lunar date. A leap flag for a month that has no leap
    counterpart falls back to the regular month. Raises ValueError when ``day``
    exceeds the month's length (29-day month asked for day 30)."""
    if month < 11:
        a11 = _lunar_month_11(year - 1, tz)
        b11 = _lunar_month_11(year, tz)
    else:
        a11 = _lunar_month_11(year, tz)
        b11 = _lunar_month_11(year + 1, tz)
    k = int(0.5 + (a11 - 2415021.076998695) / _LUNAR_MONTH)
    off = month - 11
    if off < 0:
        off += 12
    if b11 - a11 > 365:
        leap_off = _leap_month_offset(a11, tz)
        leap_month = leap_off - 2
        if leap_month < 0:
            leap_month += 12
        if leap and month != leap_month:
            leap = False  # no such leap month → regular month (spec fallback)
        if leap or off >= leap_off:
            off += 1
    else:
        leap = False
    month_start = _new_moon_day(k + off, tz)
    next_start = _new_moon_day(k + off + 1, tz)
    if day > next_start - month_start:
        raise ValueError(
            f"lunar {year}-{month:02d}-{day:02d}{' leap' if leap else ''} does not exist "
            f"(month has {next_start - month_start} days)"
        )
    dd, mm, yy = _jd_to_date(month_start + day - 1)
    return date(yy, mm, dd)


def _days_in_lunar_month(year: int, month: int, tz: float = 7.0) -> int:
    """Length (29 or 30) of the REGULAR lunar month."""
    # day 30 exists iff the next new moon is 30 days after this one
    try:
        lunar_to_solar(year, month, 30, False, tz)
        return 30
    except ValueError:
        return 29


def next_lunar_anniversary(event_date: date, today: date, tz: float = 7.0) -> date:
    """First solar date >= today of the lunar anniversary of event_date.

    Conventions (ADR-018): the anniversary month is always the REGULAR month
    (a leap-month death is observed in the regular month); day 30 clamps to 29
    in years where the month has 29 days. Mirrors the solar rule's semantics
    ("this year's anniversary if not yet passed, else next year's").
    """
    lunar = solar_to_lunar(event_date, tz)
    lunar_today = solar_to_lunar(today, tz)
    year = lunar_today.year
    while True:
        day = min(lunar.day, _days_in_lunar_month(year, lunar.month, tz))
        candidate = lunar_to_solar(year, lunar.month, day, False, tz)
        if candidate >= today:
            return candidate
        year += 1
