"""The production boot gate admits a database ahead of the code, and nothing else new (#255).

A release migrates before its deployment goes live, so for as long as the new build takes, the
previous deployment cold-starts against a revision its own scripts do not know. Until ADR-070 that
cold start raised ``RuntimeError: Database is not ready (migrations: behind)`` and Vercel answered
``FUNCTION_INVOCATION_FAILED``, measured 2026-10-10 in run 38055909194.

Each test boots the real lifespan under ``APP_ENV=production`` against the migrated test database,
then reads ``GET /health`` through the same app. That is the outcome. The string
``migration_status()`` returns is a setting, and ``tests/unit/test_readiness.py`` covers it.

**The two refusals are the inversion control.** A gate that admits everything passes the ``ahead``
test too. So a database at the head's parent, and one with no ``alembic_version``, must still stop
the boot.

**The shared migrated database never sees a planted revision.** Each test changes
``alembic_version`` on one connection, inside a transaction the fixture rolls back, and binds every
session the app opens to that connection.

``RLS_ENABLED`` is off and the scheduler is off. The RLS gate later in the same lifespan is its own
subject (#255 leaves it out of scope), and APScheduler would only start real jobs on the app's own
engine.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

import httpx
import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import app.main as main_module
from app.core.database import get_db

pytestmark = pytest.mark.integration

# 24 characters, under the 32 that ``alembic_version.version_num`` holds.
_LATER_RELEASE_REVISION = "999_from_a_later_release"


def _head_and_parent() -> tuple[str, str]:
    """Read from the scripts here, not through ``app.core.readiness``, which is under test."""
    cfg = Config("alembic.ini")
    cfg.set_main_option("script_location", "migrations")
    scripts = ScriptDirectory.from_config(cfg)
    head_id = scripts.get_current_head()
    assert head_id is not None
    head = scripts.get_revision(head_id)
    assert head is not None and isinstance(head.down_revision, str), head
    return head.revision, head.down_revision


@pytest.fixture()
async def planted(migrated_db_url: str) -> AsyncIterator[AsyncConnection]:
    """One connection inside a transaction that is always rolled back."""
    engine = create_async_engine(migrated_db_url)
    try:
        async with engine.connect() as conn:
            transaction = await conn.begin()
            try:
                yield conn
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()


@pytest.fixture()
def production(monkeypatch: pytest.MonkeyPatch) -> None:
    # Through ``app.main``, which holds the settings object it imported: the integration
    # conftest rebinds ``app.core.config.settings`` to a new one, which the lifespan never reads.
    monkeypatch.setattr("app.main.settings.APP_ENV", "production")
    monkeypatch.setattr("app.main.settings.RLS_ENABLED", False)
    monkeypatch.setattr("app.main.settings.SCHEDULER_ENABLED", False)
    monkeypatch.setattr("app.main.settings.SENTRY_DSN", "")
    # configure_logging clears the root handlers, which would take caplog's with them.
    monkeypatch.setattr(main_module, "configure_logging", lambda: None)


async def _boot_and_read_health(
    conn: AsyncConnection, monkeypatch: pytest.MonkeyPatch
) -> httpx.Response:
    """Run the app's lifespan, then ``GET /health``, with every session on *conn*.

    ``create_savepoint`` keeps the planted change in the outer transaction: a session that rolls
    back, as ``migration_status`` does when ``alembic_version`` is missing, rolls back only its
    own savepoint."""
    maker = async_sessionmaker(
        bind=conn,
        class_=AsyncSession,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    monkeypatch.setattr(main_module, "AsyncSessionLocal", maker)
    app = main_module.create_app()

    async def _db() -> AsyncIterator[AsyncSession]:
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = _db
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get("/health")


async def test_production_boots_on_a_database_ahead_of_the_code(
    planted: AsyncConnection,
    production: None,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    head, _ = _head_and_parent()
    await planted.execute(
        text("UPDATE alembic_version SET version_num = :revision"),
        {"revision": _LATER_RELEASE_REVISION},
    )

    with caplog.at_level(logging.WARNING, logger="app.main"):
        response = await _boot_and_read_health(planted, monkeypatch)

    assert response.status_code == 200, response.text
    assert response.json() == {"status": "ok", "database": "connected", "migrations": "ahead"}
    warnings = [
        record.getMessage()
        for record in caplog.records
        if record.name == "app.main"
        and record.levelno == logging.WARNING
        and _LATER_RELEASE_REVISION in record.getMessage()
    ]
    assert len(warnings) == 1, warnings
    assert "ahead" in warnings[0] and head in warnings[0], warnings[0]


async def test_production_refuses_a_database_one_revision_behind(
    planted: AsyncConnection, production: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, parent = _head_and_parent()
    await planted.execute(
        text("UPDATE alembic_version SET version_num = :revision"), {"revision": parent}
    )

    with pytest.raises(RuntimeError, match=r"Database is not ready \(migrations: behind\)"):
        await _boot_and_read_health(planted, monkeypatch)


async def test_production_refuses_a_database_with_no_alembic_version(
    planted: AsyncConnection, production: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    await planted.execute(text("DROP TABLE alembic_version"))

    with pytest.raises(RuntimeError, match=r"Database is not ready \(migrations: behind\)"):
        await _boot_and_read_health(planted, monkeypatch)
