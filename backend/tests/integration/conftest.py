"""Integration-test fixtures that run the real Alembic migration against Postgres.

Requires a running Postgres (see backend/docker-compose: `docker compose up -d pgdb`).
Override the admin DSN via TEST_PG_ADMIN_URL if your local Postgres differs.
"""

import os
from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config


def _reset_settings(dsn: str) -> None:
    """Force-reinitialise cached settings to use *dsn* as DATABASE_URL.

    ``app.core.config.settings`` is a module-level singleton frozen by
    ``@lru_cache``.  When app modules are imported during pytest collection
    (before any fixture runs) the cache fills with the default DATABASE_URL.
    Subsequent calls to ``get_settings()`` from ``migrations/env.py`` return
    the stale cached value, so Alembic ignores the DSN we passed to
    ``cfg.set_main_option``.  Clearing the cache and re-creating the singleton
    after we set ``os.environ["DATABASE_URL"]`` guarantees that every Alembic
    run in this session targets the throw-away test database.
    """
    import app.core.config as _cfg_module

    _cfg_module.get_settings.cache_clear()
    os.environ["DATABASE_URL"] = dsn
    # Re-populate the module-level singleton that migrations/env.py reads.
    new_settings = _cfg_module.get_settings()
    _cfg_module.settings = new_settings

# Admin connection used to CREATE/DROP the throwaway test database.
ADMIN_URL = os.environ.get(
    "TEST_PG_ADMIN_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/postgres"
)
TEST_DB_NAME = "family_roots_schema_test"


def _sync_dsn(db_name: str) -> str:
    base = ADMIN_URL.rsplit("/", 1)[0]
    return f"{base}/{db_name}"


@pytest.fixture(scope="session")
def migrated_db_url() -> Iterator[str]:
    admin = sa.create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}" WITH (FORCE)'))
        conn.execute(sa.text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    admin.dispose()

    test_dsn = _sync_dsn(TEST_DB_NAME)
    cfg = Config("alembic.ini")
    cfg.set_main_option("script_location", "migrations")
    # env.py strips +asyncpg; pass the sync DSN directly.
    cfg.set_main_option("sqlalchemy.url", test_dsn)
    # Clear the @lru_cache on get_settings() so that migrations/env.py uses the
    # test DSN even when app modules were already imported during collection.
    _reset_settings(test_dsn)
    command.upgrade(cfg, "head")

    yield test_dsn

    admin = sa.create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}" WITH (FORCE)'))
    admin.dispose()


@pytest.fixture()
def sync_engine(migrated_db_url: str) -> Iterator[sa.Engine]:
    engine = sa.create_engine(migrated_db_url)
    yield engine
    engine.dispose()
