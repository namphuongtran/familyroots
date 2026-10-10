"""``migrations/env.py`` reaches a database whose URL carries a percent-encoded password.

Alembic's ``Config`` is a ``ConfigParser`` with interpolation. ``set_main_option`` refuses a
value holding a ``%`` that is not doubled, with ``ValueError: invalid interpolation
syntax``. A password containing ``@``, ``:``, ``/`` or ``%`` has to be percent-encoded in a
URL, and the Supabase pooler URL that production migrates through carries one (#251,
reported by the #252 agent with Alembic 1.18.5). Before the fix, every Alembic command
failed in ``env.py`` before it opened a connection.

The test runs the Alembic CLI as its own process, so ``env.py`` reads the URL the way it
does in a deploy, from ``settings.DATABASE_URL``. It runs ``alembic stamp head``, which
goes through ``run_migrations_online`` exactly as ``upgrade`` does. Then it reads the row
that command wrote. A connection that never happened cannot leave a row behind.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from tests.integration.conftest import ADMIN_URL, TEST_DB_NAME

pytestmark = pytest.mark.integration

_BACKEND_DIR = Path(__file__).resolve().parents[2]
# Every character a URL password must encode, and ``%`` itself, which encodes to ``%25``.
_PASSWORD = "p@ss:w/rd%1"


def _head() -> str:
    config = Config()
    config.set_main_option("script_location", str(_BACKEND_DIR / "migrations"))
    (head,) = ScriptDirectory.from_config(config).get_heads()
    return str(head)


def test_alembic_reaches_a_database_whose_url_has_a_percent_encoded_password() -> None:
    suffix = uuid.uuid4().hex[:10]
    login = f"fr_encoded_pw_{suffix}"
    db_name = f"{TEST_DB_NAME[:36]}_encpw_{suffix}"
    server = make_url(ADMIN_URL)
    url = server.set(username=login, password=_PASSWORD, database=db_name).render_as_string(
        hide_password=False
    )
    admin = sa.create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            # The literal is a constant of this module, quoted for SQL by doubling.
            quoted = _PASSWORD.replace("'", "''")
            conn.execute(sa.text(f"CREATE ROLE {login} LOGIN PASSWORD '{quoted}'"))
            conn.execute(sa.text(f'CREATE DATABASE "{db_name}" OWNER {login}'))

        done = subprocess.run(
            [sys.executable, "-m", "alembic", "stamp", "head"],
            cwd=_BACKEND_DIR,
            env={**os.environ, "DATABASE_URL": url},
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )

        db_engine = sa.create_engine(server.set(database=db_name))
        try:
            with db_engine.connect() as conn:
                has_table = conn.execute(
                    sa.text("SELECT to_regclass('public.alembic_version') IS NOT NULL")
                ).scalar_one()
                stamped = (
                    conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalars().all()
                    if has_table
                    else []
                )
        finally:
            db_engine.dispose()
    finally:
        with admin.connect() as conn:
            conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)'))
            conn.execute(sa.text(f"DROP ROLE IF EXISTS {login}"))
        admin.dispose()

    # The URL really does carry the encoded characters this test exists for.
    assert "%40" in url and "%25" in url
    assert done.returncode == 0, done.stderr[-4000:]
    assert stamped == [_head()]
