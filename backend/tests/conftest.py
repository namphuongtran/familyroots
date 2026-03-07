"""Pytest configuration and shared fixtures for tree builder tests."""

import uuid
from datetime import date
from typing import Any
from unittest.mock import AsyncMock

import pytest

# ---------------------------------------------------------------------------
# Helpers to build mock DB rows (MappingResult-style dicts)
# ---------------------------------------------------------------------------


def make_member_row(
    *,
    member_id: uuid.UUID | None = None,
    full_name: str = "Test Member",
    birth_name: str | None = None,
    gender: str = "male",
    birth_date: date | None = None,
    birth_date_approx: bool = False,
    death_date: date | None = None,
    death_date_approx: bool = False,
    birth_place: str | None = None,
    generation: int | None = 1,
    avatar_url: str | None = None,
    is_clan_member: bool = True,
    is_clan_founder: bool = False,
    parent_id: uuid.UUID | None = None,
    depth: int = 0,
) -> dict[str, Any]:
    """Create a dict mimicking a row from get_family_tree_flat()."""
    return {
        "member_id": member_id or uuid.uuid4(),
        "full_name": full_name,
        "birth_name": birth_name,
        "gender": gender,
        "birth_date": birth_date,
        "birth_date_approx": birth_date_approx,
        "death_date": death_date,
        "death_date_approx": death_date_approx,
        "birth_place": birth_place,
        "generation": generation,
        "avatar_url": avatar_url,
        "is_clan_member": is_clan_member,
        "is_clan_founder": is_clan_founder,
        "parent_id": parent_id,
        "depth": depth,
        "path": [member_id or uuid.uuid4()],
    }


def make_spouse_row(
    *,
    for_member_id: uuid.UUID,
    spouse_id: uuid.UUID | None = None,
    full_name: str = "Spouse",
    gender: str = "female",
    birth_date: date | None = None,
    death_date: date | None = None,
    avatar_url: str | None = None,
    relation_subtype: str = "married",
    start_date: date | None = None,
    end_date: date | None = None,
    is_primary: bool = True,
) -> dict[str, Any]:
    """Create a dict mimicking a spouse join row."""
    return {
        "for_member_id": for_member_id,
        "spouse_id": spouse_id or uuid.uuid4(),
        "full_name": full_name,
        "gender": gender,
        "birth_date": birth_date,
        "death_date": death_date,
        "avatar_url": avatar_url,
        "relation_subtype": relation_subtype,
        "start_date": start_date,
        "end_date": end_date,
        "is_primary": is_primary,
    }


class MockMappingResult:
    """Mimics SQLAlchemy result.mappings().all()."""

    def __init__(self, rows: list[dict[str, Any]]):
        self._rows = rows

    def mappings(self) -> MockMappingResult:
        return self

    def all(self) -> list[dict[str, Any]]:
        return self._rows

    def first(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None


class MockScalarResult:
    """Mimics SQLAlchemy result.first() returning a tuple-like row."""

    def __init__(self, value: Any = None):
        self._value = value

    def first(self) -> tuple[Any, ...] | None:
        if self._value is not None:
            return (self._value,)
        return None


def make_mock_db(*execute_returns: Any) -> AsyncMock:
    """Create an AsyncMock pretending to be an AsyncSession.

    Each call to db.execute() returns the next item in execute_returns.
    """
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=list(execute_returns))
    return db


@pytest.fixture
def clan_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture
def root_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-000000000010")
