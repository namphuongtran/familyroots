"""Readiness against a real database: migrated → current; unmigrated → behind;
and /health surfaces the state with the right status code."""

from collections.abc import AsyncGenerator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.core.readiness import MIGRATIONS_BEHIND, MIGRATIONS_CURRENT, migration_status
from app.main import create_app
from tests.integration.conftest import ADMIN_URL


@pytest.fixture()
async def migrated_session(migrated_db_url: str) -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine(migrated_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_migrated_db_reports_current(migrated_session: AsyncSession) -> None:
    assert await migration_status(migrated_session) == MIGRATIONS_CURRENT


@pytest.mark.asyncio
async def test_unmigrated_db_reports_behind() -> None:
    """The admin `postgres` database has no alembic_version table."""
    engine = create_async_engine(ADMIN_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as session:
        assert await migration_status(session) == MIGRATIONS_BEHIND
    await engine.dispose()


def _client_with_db(db_url: str) -> TestClient:
    app = create_app()
    engine = create_async_engine(db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def _override() -> AsyncGenerator[AsyncSession]:
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = _override
    return TestClient(app)


def test_health_ok_on_migrated_db(migrated_db_url: str) -> None:
    resp = _client_with_db(migrated_db_url).get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["migrations"] == MIGRATIONS_CURRENT


def test_health_degraded_on_unmigrated_db() -> None:
    resp = _client_with_db(ADMIN_URL).get("/health")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["migrations"] == MIGRATIONS_BEHIND
