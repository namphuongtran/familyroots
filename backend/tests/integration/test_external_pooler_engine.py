"""What `DB_EXTERNAL_POOLER=true` does to a real Postgres session (ADR-065).

The unit test beside this one reads the settings that reach psycopg. This one reads the two
outcomes those settings exist for, on the server, against the migrated throwaway database:

1. **No server-side prepared statement.** psycopg 3 prepares a query on the server once it
   has run five times on one connection. Behind a transaction pooler the next transaction may
   land on another server connection, where that statement is absent, or already present
   (``DuplicatePreparedStatement``). Read from ``pg_prepared_statements``, which is
   per-session, after running one query ten times. The direct engine is the control. It must
   show a prepared statement, or this test cannot fail for the reason it exists.
2. **No connection parked after use.** A serverless instance is frozen between requests, so
   a connection held in its own pool sits open against the pooler's client limit. After the
   engine's connection is closed, its server backend must be gone. The direct engine is the
   control again: there, the next checkout gets the same backend back.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import Settings
from app.core.database import make_engine

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

# psycopg's default prepare_threshold is 5, so ten runs is twice past it.
_RUNS = 10


def _engine(dsn: str, *, external_pooler: bool) -> AsyncEngine:
    settings = Settings(_env_file=None, DATABASE_URL=dsn, DB_EXTERNAL_POOLER=external_pooler)
    return make_engine(settings)


async def _prepared_after_repeating_a_query(engine: AsyncEngine) -> int:
    async with engine.connect() as conn:
        for i in range(_RUNS):
            await conn.execute(sa.text("SELECT CAST(:n AS int) + 1"), {"n": i})
        count = await conn.scalar(sa.text("SELECT count(*) FROM pg_prepared_statements"))
        await conn.rollback()
    return int(count or 0)


async def test_the_external_pooler_engine_prepares_nothing_on_the_server(
    migrated_db_url: str,
) -> None:
    direct = _engine(migrated_db_url, external_pooler=False)
    pooled = _engine(migrated_db_url, external_pooler=True)
    try:
        control = await _prepared_after_repeating_a_query(direct)
        reading = await _prepared_after_repeating_a_query(pooled)
    finally:
        await direct.dispose()
        await pooled.dispose()

    assert control >= 1, (
        "the control prepared nothing, so this test cannot tell the two engines apart: "
        f"psycopg's default threshold should have prepared after {_RUNS} runs"
    )
    assert reading == 0, f"the external-pooler engine left {reading} prepared statement(s)"


async def _backend_pids_across_two_checkouts(engine: AsyncEngine) -> tuple[int, int]:
    async with engine.connect() as conn:
        first = int(await conn.scalar(sa.text("SELECT pg_backend_pid()")) or 0)
        await conn.rollback()
    async with engine.connect() as conn:
        second = int(await conn.scalar(sa.text("SELECT pg_backend_pid()")) or 0)
        await conn.rollback()
    return first, second


async def _backend_is_alive(observer: AsyncEngine, pid: int) -> bool:
    async with observer.connect() as conn:
        alive = await conn.scalar(
            sa.text("SELECT count(*) FROM pg_stat_activity WHERE pid = :p"), {"p": pid}
        )
        await conn.rollback()
    return bool(alive)


async def test_the_external_pooler_engine_parks_no_connection(migrated_db_url: str) -> None:
    observer = create_async_engine(migrated_db_url)
    direct = _engine(migrated_db_url, external_pooler=False)
    pooled = _engine(migrated_db_url, external_pooler=True)
    try:
        direct_first, direct_second = await _backend_pids_across_two_checkouts(direct)
        pooled_first, pooled_second = await _backend_pids_across_two_checkouts(pooled)

        # Control: the direct engine keeps its connection and hands the same backend back.
        assert direct_first == direct_second
        assert await _backend_is_alive(observer, direct_first)

        # Reading: each checkout is a new backend, and a closed one does not linger. The
        # server notices the client's close asynchronously, so give it a moment.
        assert pooled_first != pooled_second
        lingering: Any = True
        for _ in range(50):
            lingering = await _backend_is_alive(observer, pooled_first)
            if not lingering:
                break
            await asyncio.sleep(0.05)
        assert not lingering, f"backend {pooled_first} outlived its NullPool checkout"
    finally:
        await direct.dispose()
        await pooled.dispose()
        await observer.dispose()
