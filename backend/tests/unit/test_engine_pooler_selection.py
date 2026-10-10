"""`DB_EXTERNAL_POOLER` picks the engine's shape (ADR-065), and false leaves it as it was.

Reads two things for each value: the pool class the engine was built with, and the keyword
arguments that actually reach ``psycopg.AsyncConnection.connect`` when the engine opens a
connection. The second is read at psycopg's own door rather than from ``engine.dialect``,
because a ``connect_args`` that SQLAlchemy accepted and then dropped would still show up on
the dialect. No database is needed: the stand-in records the call and refuses it.

The outcomes these settings exist for (no server-side prepared statement, no connection
parked between checkouts) are read against a real Postgres in
``tests/integration/test_external_pooler_engine.py``.
"""

from __future__ import annotations

from typing import Any

import psycopg
import pytest
from sqlalchemy.pool import AsyncAdaptedQueuePool, NullPool

from app.core.config import Settings
from app.core.database import make_engine

pytestmark = pytest.mark.unit

_DSN = "postgresql+psycopg://u:p@db.invalid:5432/familyroots"


class _Refused(Exception):
    """Raised by the stand-in so no real connection is attempted."""


def _settings(**overrides: Any) -> Settings:
    return Settings(_env_file=None, DATABASE_URL=_DSN, **overrides)


async def _kwargs_reaching_psycopg(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> dict[str, Any]:
    seen: list[dict[str, Any]] = []

    async def stand_in(*args: Any, **kwargs: Any) -> Any:
        seen.append(kwargs)
        raise _Refused

    # SQLAlchemy's async psycopg adapter looks this attribute up at call time
    # (sqlalchemy/dialects/postgresql/psycopg.py, AsyncAdapt_psycopg_dbapi.connect).
    monkeypatch.setattr(psycopg.AsyncConnection, "connect", stand_in)
    engine = make_engine(settings)
    try:
        with pytest.raises(_Refused):
            async with engine.connect():
                pass
    finally:
        await engine.dispose()
    assert len(seen) == 1, seen
    return seen[0]


async def test_a_direct_postgres_keeps_the_sized_queue_pool_and_psycopgs_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(DB_EXTERNAL_POOLER=False, DB_POOL_SIZE=7, DB_MAX_OVERFLOW=3)
    engine = make_engine(settings)
    try:
        assert type(engine.pool) is AsyncAdaptedQueuePool
        assert engine.pool.size() == 7
        assert engine.pool._max_overflow == 3
    finally:
        await engine.dispose()

    kwargs = await _kwargs_reaching_psycopg(settings, monkeypatch)
    assert "prepare_threshold" not in kwargs, kwargs


async def test_an_external_pooler_gets_nullpool_and_no_server_side_prepare(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The pool-size settings are present and must not matter.
    settings = _settings(DB_EXTERNAL_POOLER=True, DB_POOL_SIZE=7, DB_MAX_OVERFLOW=3)
    engine = make_engine(settings)
    try:
        assert type(engine.pool) is NullPool
    finally:
        await engine.dispose()

    kwargs = await _kwargs_reaching_psycopg(settings, monkeypatch)
    assert "prepare_threshold" in kwargs, kwargs
    assert kwargs["prepare_threshold"] is None


def test_the_default_is_the_direct_shape() -> None:
    """Local and Docker set nothing, and must keep today's engine."""
    assert _settings().DB_EXTERNAL_POOLER is False
