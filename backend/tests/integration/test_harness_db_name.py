"""The migrated database the whole integration suite runs against is the one
`TEST_PG_DB_NAME` names.

The unit test for `resolve_test_db_name` proves the resolver reads the env var;
this proves the *fixture* is wired to it — that `migrated_db_url` builds its DSN
from the resolved name rather than a constant, so setting the variable really
does move every integration test onto a private database.
"""

import pytest
import sqlalchemy as sa

from tests.integration.conftest import TEST_DB_NAME

pytestmark = pytest.mark.integration


def test_suite_runs_against_the_resolved_database_name(sync_engine: sa.Engine) -> None:
    with sync_engine.connect() as conn:
        assert conn.scalar(sa.text("SELECT current_database()")) == TEST_DB_NAME


def test_the_migration_chain_landed_in_that_database(sync_engine: sa.Engine) -> None:
    """Not just connected to it — migrated inside it. A DSN pointing somewhere
    else that happened to be named right would still fail this."""
    with sync_engine.connect() as conn:
        assert conn.scalar(sa.text("SELECT count(*) FROM alembic_version")) == 1
        assert conn.scalar(sa.text("SELECT to_regclass('public.clans') IS NOT NULL"))
