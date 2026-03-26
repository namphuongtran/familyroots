"""Sparse fieldset utilities for API response filtering.

Provides reusable helpers for parsing and applying ``?fields=``
and ``?include=`` query parameters across all endpoints.
"""

from typing import Any


def parse_field_set(fields: str | None, *, include: str | None = None) -> set[str] | None:
    """Parse comma-separated field names into a set.

    If ``include`` is given, its entries are merged so that included
    compound-document keys are never accidentally filtered out.

    Returns ``None`` when no filtering is requested.
    """
    if not fields:
        return None

    field_set = {f.strip() for f in fields.split(",") if f.strip()}
    if include:
        field_set.update(i.strip() for i in include.split(",") if i.strip())
    return field_set


def parse_includes(include: str | None) -> list[str]:
    """Parse comma-separated ``?include=`` value into a list."""
    if not include:
        return []
    return [i.strip() for i in include.split(",") if i.strip()]


def filter_dict(data: dict[str, Any], field_set: set[str] | None) -> dict[str, Any]:
    """Filter a dict to only keep keys in ``field_set``.

    Returns the original dict unchanged if ``field_set`` is None.
    """
    if field_set is None:
        return data
    return {k: v for k, v in data.items() if k in field_set}


def filter_list(
    items: list[Any],
    field_set: set[str] | None,
) -> list[Any]:
    """Filter each item in a list to only keep allowed fields.

    Items can be dicts or Pydantic models (which are converted via
    ``model_dump()``).
    """
    if field_set is None or not items:
        return items

    filtered = []
    for item in items:
        d = item if isinstance(item, dict) else item.model_dump()
        filtered.append({k: v for k, v in d.items() if k in field_set})
    return filtered
