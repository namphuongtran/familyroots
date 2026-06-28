"""When the job's advisory lock is already held, the run is a clean no-op."""

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.core.database  # noqa: F401 — imported early so _reset_settings can't break it
from app.services import scheduler


@pytest.fixture()
async def async_engine(migrated_db_url):
    async_dsn = migrated_db_url.replace("postgresql+psycopg2", "postgresql+asyncpg")
    engine = create_async_engine(async_dsn)
    yield engine
    await engine.dispose()


@pytest.mark.asyncio
async def test_job_skips_when_lock_held(async_engine, monkeypatch):
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    # Point the job at the test DB.
    monkeypatch.setattr("app.core.database.AsyncSessionLocal", maker)

    # Seed a clan + a recurring event due today so the job WOULD send if it ran.
    async with maker() as s:
        clan_id = uuid.uuid4()
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :sg)"),
            {"id": clan_id, "sg": f"c{clan_id.hex[:6]}"},
        )
        await s.commit()

    # Hold the advisory lock on a dedicated connection for the whole test.
    holder = await async_engine.connect()
    try:
        got = await holder.execute(
            sa.text("SELECT pg_try_advisory_lock(:k)"), {"k": scheduler._JOB_LOCK_KEY}
        )
        assert got.scalar() is True  # we hold it

        # Run the job — it must fail to acquire the lock and no-op.
        await scheduler.send_anniversary_notifications()

        async with maker() as s:
            n = await s.execute(sa.text("SELECT COUNT(*) FROM notification_log"))
            assert n.scalar() == 0  # job did not process anything
    finally:
        await holder.execute(
            sa.text("SELECT pg_advisory_unlock(:k)"), {"k": scheduler._JOB_LOCK_KEY}
        )
        await holder.close()
