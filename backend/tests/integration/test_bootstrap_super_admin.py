"""``scripts/bootstrap_super_admin.py`` against a real, migrated Postgres.

The super admin has two halves, like every user (``docs/ops/local-supabase.md`` § "The
topology"): an identity in the Supabase project's ``auth.users`` and a ``user_profiles`` row
in the application database. ``get_super_admin`` reads only the second. Until issue #168 the
script wrote that row, and ran its "already exists" check, through the Supabase Data API —
into a database that holds no ``user_profiles`` table.

These tests exercise the **application-database half for real** and stub the identity half,
for the reason ``test_seed_dev_data.py`` gives: the Supabase stack is one shared container
set, and two suites creating the same identity in it would collide. The reading against the
local stack, and the old script's negative control, are in the commit message that added
this file.

What they pin is the outcome, read back from the database: after a run the row the API will
check is there, and a second run refuses **before** it creates a second identity.
"""

import importlib.util
import os
import sys
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from types import ModuleType

import psycopg
import pytest

pytestmark = pytest.mark.integration

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "bootstrap_super_admin.py"


def _load_script() -> ModuleType:
    """Import the script by path. It lives in ``scripts/``, which is not a package."""
    spec = importlib.util.spec_from_file_location("bootstrap_super_admin_under_test", _SCRIPT)
    assert spec is not None and spec.loader is not None, f"cannot load {_SCRIPT}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


script = _load_script()


class StubIdentities:
    """Stands in for the GoTrue admin API. Every call mints a new identity, as GoTrue does."""

    def __init__(self) -> None:
        self.created: list[tuple[str, str, str]] = []

    def __call__(self, email: str, password: str) -> str:
        user_id = str(uuid.uuid4())
        self.created.append((user_id, email, password))
        return user_id


def _credentials(email: str) -> Callable[[], tuple[str, str]]:
    def read() -> tuple[str, str]:
        return email, "correct-horse-battery"

    return read


def _never_prompt() -> tuple[str, str]:
    raise AssertionError("the script prompted for credentials it was going to refuse")


def _super_admins(dsn: str) -> list[tuple[str, str]]:
    """(id, email) of every super admin, read on a fresh connection so only committed rows count."""
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT id::text, email FROM user_profiles WHERE platform_role = 'super_admin'")
        return sorted(cur.fetchall())


def _run(
    dsn: str, identities: StubIdentities, read_credentials: Callable[[], tuple[str, str]]
) -> str:
    """One run of the script's body, on a connection closed **without** a commit.

    Closing discards an open transaction, so a row counts only if ``bootstrap`` committed it.
    A ``with psycopg.connect(...)`` block here would commit on exit and hide a missing one.
    """
    conn = psycopg.connect(dsn)
    try:
        email: str = script.bootstrap(conn, identities, read_credentials)
        return email
    finally:
        conn.close()


@pytest.fixture()
def dsn(migrated_db_url: str) -> Iterator[str]:
    """The migrated database, routed through the script's own ``app_dsn()``.

    Starts with no super admin, so a pass cannot be borrowed from another test's row, and
    removes the ones it made: the database is shared by the whole session.
    """
    os.environ["DATABASE_URL"] = migrated_db_url
    resolved = script.app_dsn()
    assert "+psycopg" not in resolved, f"app_dsn() left a driver suffix in {resolved!r}"
    assert _super_admins(resolved) == [], "a super admin already exists before the test ran"
    yield resolved
    with psycopg.connect(resolved) as conn:
        conn.execute("DELETE FROM user_profiles WHERE platform_role = 'super_admin'")


def test_a_run_writes_the_profile_row_get_super_admin_reads(dsn):
    identities = StubIdentities()
    email = _run(dsn, identities, _credentials("root@familyroots.example.com"))

    [(user_id, created_email, _)] = identities.created
    assert email == created_email == "root@familyroots.example.com"
    assert _super_admins(dsn) == [(user_id, "root@familyroots.example.com")]


def test_a_second_run_refuses_before_it_creates_a_second_identity(dsn):
    """The failure this exists to catch: an existence check that reads a database not holding
    the row. Then the second run passes the check, mints a second identity, and writes a
    second super admin under a different email."""
    identities = StubIdentities()
    _run(dsn, identities, _credentials("root@familyroots.example.com"))
    first = _super_admins(dsn)

    with pytest.raises(script.Refused, match="already exists"):
        _run(dsn, identities, _never_prompt)

    assert len(identities.created) == 1
    assert _super_admins(dsn) == first


def test_a_database_without_user_profiles_is_named_as_the_wrong_database(migrated_db_url):
    """Pointing ``DATABASE_URL`` at the Supabase database is the mistake #168 was about.

    The cluster's ``postgres`` database stands in for it: reachable, and holding no
    ``user_profiles``. The run must stop at the check and name the variable to fix.
    """
    identities = StubIdentities()
    other = migrated_db_url.replace("+psycopg", "").rsplit("/", 1)[0] + "/postgres"
    with pytest.raises(script.Refused, match="DATABASE_URL"):
        _run(other, identities, _never_prompt)

    assert identities.created == []
