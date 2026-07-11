"""Pydantic v2 schema for HistoricalDate: a date with precision, display, and lunar metadata."""

import datetime
from collections.abc import Mapping
from typing import Any

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


def _source_get(source: Any, key: str, default: Any = None) -> Any:
    """Read `key` off a dict-like source or via attribute access, defaulting when absent.

    Supports both a plain ``Mapping`` (constructor kwargs collected by Pydantic v2 for a
    `Model(**kwargs)` call) and an arbitrary object — ORM row, domain entity, or another
    Pydantic model instance — accessed via ``getattr``.
    """
    if isinstance(source, Mapping):
        return source.get(key, default)
    return getattr(source, key, default)


def historical_date_field(
    source: Any, field: str, *, lunar_field: str | None = None
) -> HistoricalDate:
    """Build (or pass through) the `HistoricalDate` for a response field.

    `source` may be an ORM row / domain entity with flat `<field>`, `<field>_precision`,
    `<field>_display` (+ optional lunar) attributes, a dict of constructor kwargs, or
    another response model whose `field` is already a `HistoricalDate` (or an equivalent
    mapping) — in which case it passes through unchanged. This lets a narrower response
    profile (e.g. a person "summary" schema) be re-validated from a fuller response model
    (e.g. the "full" person schema) without re-deriving precision/display/lunar.
    """
    current = _source_get(source, field)
    if isinstance(current, HistoricalDate):
        return current
    if isinstance(current, Mapping):
        return HistoricalDate(**current)
    precision = _source_get(source, f"{field}_precision", "exact") or "exact"
    display = _source_get(source, f"{field}_display")
    lunar = _source_get(source, lunar_field) if lunar_field else None
    return to_historical_date(current, precision, display, lunar)


def coerce_response_dates(
    cls: type[BaseModel], data: Any, date_fields: Mapping[str, str | None]
) -> Any:
    """Shared body for a response model's `@model_validator(mode="before")`.

    Nests each field named in `date_fields` (mapped to its lunar source attribute, or
    `None` when the aggregate has no lunar column) into a `HistoricalDate`, while leaving
    every other field's value untouched. Works whether `data` is a dict of constructor
    kwargs, an ORM row / domain entity (flat attributes read via `getattr`, one per
    declared model field), or another response model instance (same attribute-access path
    — see `historical_date_field` for the pass-through case).
    """
    result: dict[str, Any]
    if isinstance(data, Mapping):
        result = dict(data)
    else:
        _missing = object()
        result = {}
        for name in cls.model_fields:
            value = getattr(data, name, _missing)
            if value is not _missing:
                result[name] = value
    for field, lunar_field in date_fields.items():
        if field in cls.model_fields:
            result[field] = historical_date_field(data, field, lunar_field=lunar_field)
    return result
