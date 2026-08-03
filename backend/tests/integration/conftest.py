"""Integration-test fixtures that run the real Alembic migration against Postgres.

Requires a running Postgres (see backend/docker-compose: `docker compose up -d pgdb`).
Override the admin DSN via TEST_PG_ADMIN_URL if your local Postgres differs, and the
throwaway database name via TEST_PG_DB_NAME if a second suite may run concurrently.
"""

import os
import re
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
    "TEST_PG_ADMIN_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/postgres"
)

TEST_DB_NAME_ENV = "TEST_PG_DB_NAME"
DEFAULT_TEST_DB_NAME = "family_roots_schema_test"

# Postgres unquoted-identifier alphabet, and nothing else. The name below is
# interpolated straight into DROP/CREATE DATABASE, which cannot take a bind
# parameter -- when the value was a literal constant that was safe by
# construction, but an environment variable is attacker-adjacent input the
# moment it comes from a CI matrix, a Makefile or a shell someone else wrote.
_SAFE_DB_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# Postgres NAMEDATALEN-1. Longer identifiers are silently truncated, so two
# runs whose names agree on the first 63 characters would still collide -- the
# exact failure this override exists to prevent. Reject rather than truncate.
_MAX_DB_NAME_LENGTH = 63


def resolve_test_db_name() -> str:
    """Return the throwaway database name, overridable via ``TEST_PG_DB_NAME``.

    The session fixture below drops this database with ``WITH (FORCE)``, which
    terminates other backends' connections. Two suites sharing one name
    therefore destroy each other's schema mid-run (``AsyncConnection [BAD]``
    and a wave of spurious failures). Anything that may run concurrently --
    a second agent in another worktree, a developer alongside CI -- must set
    ``TEST_PG_DB_NAME`` to a distinct value. The default is unchanged, so an
    invocation that sets nothing behaves exactly as before.
    """
    name = os.environ.get(TEST_DB_NAME_ENV, DEFAULT_TEST_DB_NAME)
    if not _SAFE_DB_NAME.fullmatch(name) or len(name) > _MAX_DB_NAME_LENGTH:
        raise ValueError(
            f"{TEST_DB_NAME_ENV}={name!r} is not a usable Postgres database name: "
            f"expected 1-{_MAX_DB_NAME_LENGTH} characters matching "
            f"{_SAFE_DB_NAME.pattern!r}"
        )
    return name


TEST_DB_NAME = resolve_test_db_name()


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
    # psycopg v3: one URL serves both alembic (sync) and the app (async).
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
