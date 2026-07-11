"""Pydantic v2 schema for HistoricalDate: a date with precision, display, and lunar metadata."""

import datetime

from pydantic import BaseModel, Field

# NOTE: the field below is named `date`, which would shadow a bare `from datetime import
# date` import inside the class body during Pydantic v2's (PEP 649 / Python 3.14) lazy
# annotation evaluation, raising `TypeError: unsupported operand type(s) for |: 'NoneType'
# and 'NoneType'`. Using the `datetime` module reference (`datetime.date`) avoids the
# name collision.


class HistoricalDate(BaseModel):
    """A historical date with precision and optional human-readable/lunar representation."""

    date: datetime.date | None = None
    precision: str = Field("exact", pattern="^(exact|year|month|circa|unknown)$")
    display: str | None = None
    lunar: str | None = None


def to_historical_date(
    value: datetime.date | None,
    precision: str | None,
    display: str | None,
    lunar: str | None,
) -> HistoricalDate:
    """Build a HistoricalDate from raw scalar fields, defaulting precision to 'exact'."""
    return HistoricalDate(date=value, precision=precision or "exact", display=display, lunar=lunar)
