"""Readiness logic: head detection from scripts + DB comparison states."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.readiness import (
    MIGRATIONS_BEHIND,
    MIGRATIONS_CURRENT,
    expected_head,
    migration_status,
)

pytestmark = [pytest.mark.unit]


def test_expected_head_reads_migration_scripts() -> None:
    """A ``None`` head silently disables the whole readiness check.

    This asserts only the **source tree** layout, whatever its docstring used to
    claim. It was green for the entire life of the readiness-path fix, during which the deployed
    wheel carried no migration scripts at all and the production image could not
    boot. The deployed layout is pinned by
    ``tests/unit/test_wheel_carries_migration_scripts.py`` instead."""
    assert expected_head() is not None


def _session_returning(version: str | None) -> AsyncMock:
    result = MagicMock()
    result.scalar.return_value = version
    session = AsyncMock()
    session.execute.return_value = result
    return session


@pytest.mark.asyncio
async def test_status_current_when_db_matches_head() -> None:
    session = _session_returning(expected_head())
    assert await migration_status(session) == MIGRATIONS_CURRENT


@pytest.mark.asyncio
async def test_status_behind_when_db_on_older_revision() -> None:
    session = _session_returning("001_initial")
    assert await migration_status(session) == MIGRATIONS_BEHIND


@pytest.mark.asyncio
async def test_status_behind_and_rolls_back_when_table_missing() -> None:
    """A never-migrated DB has no alembic_version table; the failed SELECT must
    not leave the caller's session in an aborted transaction."""
    session = AsyncMock()
    session.execute.side_effect = RuntimeError("relation does not exist")
    assert await migration_status(session) == MIGRATIONS_BEHIND
    session.rollback.assert_awaited_once()
