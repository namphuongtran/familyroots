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
    os.environ["DATABASE_URL"] = test_dsn
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
