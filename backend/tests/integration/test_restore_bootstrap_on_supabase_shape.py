"""A restore into a Supabase-shaped database gets back what 041, 042 and 043 did (#283).

The backups dump with ``--no-owner --no-privileges`` (``scripts/db_backup.sh:40``), and the
restored ``alembic_version`` already reads head, so no migration runs again. Whatever the chain
did that the dump does not carry, ``scripts/restore_bootstrap_role.sql`` must do (ADR-052). On
plain Postgres, run as a superuser, that was what migrations 002 and 026 grant. A Supabase
project needs three more:

- **041.** Supabase's ``postgres`` is not a superuser, so it may enter ``familyroots_app`` only
  through a membership with SET. That membership is a cluster object, and the dump has none.
- **042.** Restored tables take the restoring login's default privileges, and Supabase's
  legacy default grants ``anon`` and ``authenticated`` ALL on them.
- **043.** The project's ``ensure_rls`` event trigger fires on every ``CREATE TABLE`` that
  ``pg_restore`` issues, so RLS comes back on for the four tables 043 turned it off on.

This module dumps the migrated chain from plain Postgres and restores it, as the shape's login,
into the shape ``test_supabase_shaped_database`` builds, left empty. It runs the bootstrap with
``psql`` as the same login, which is the runbook in ``docs/ops/backup-restore.md``, "Restoring
for real", and runs it twice, because the file must be idempotent. Then it reads outcomes by
running statements as the roles concerned (``.claude/rules/testing.md``):

1. the login enters the request role, and each clan sees its own rows (041);
2. the Data API's roles are refused every table privilege but ``REFERENCES`` on every relation
   in ``public``, and on the next table and sequence the login creates (042);
3. the request role reads a row from each table the chain leaves outside layer 2 (043).

**Each reading depends on one replay.** Readings 2 and 3 drop to their role from a superuser
session, which may ``SET ROLE`` to any role, so a missing 041 grant fails the first test alone.
One more test compares every table's RLS state with the dump's. It reads the catalog, as
``test_every_table_has_the_rls_state_plain_postgres_gives_it`` does, because a bootstrap that
turned RLS off on one table too many would leave the three readings above green.

**The client binaries are chosen, not found.** ``pg_dump`` refuses a server newer than itself,
and the ``pg_dump`` on the ubuntu runner's ``PATH`` is 16 while CI runs Postgres 18 (#282). So
the module reads the server's major version and takes ``pg_dump``, ``pg_restore`` and ``psql``
from one directory whose ``pg_dump`` is at least that version. ``TEST_PG_BIN_DIR`` names the
directory outright. Otherwise the candidates are Debian's ``/usr/lib/postgresql/<N>/bin``, where
``backend-ci.yml`` installs the client, Homebrew's keg-only ``libpq``, and ``PATH``, and the
module takes the oldest version that is new enough, the earlier candidate on a tie.
Finding none fails the module and lists what it tried. It never skips, because a restore test
that skips is as silent as the backup in #282 was.

**What it does not cover.** A Supabase project that never held ``familyroots_app``, where the
bootstrap's own ``CREATE ROLE`` hands the login its ADMIN membership. The role is a cluster
object shared with the rest of the suite, so the shape copies a creator's options onto the
existing role instead, as its fixture says. And which schemas a production dump holds (#285):
this dump holds only what the chain creates.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import uuid
from collections.abc import Generator, Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models  # noqa: F401  (registers every table on Base.metadata)
from app.core.database import RlsSession
from app.core.rls import set_request_clan_id
from app.models.base import Base
from tests.integration.conftest import ADMIN_URL, TEST_DB_NAME
from tests.integration.test_supabase_shaped_database import (
    _APP_ROLE,
    _DATA_API_ROLES,
    SupabaseShapedDb,
    _alembic_ok,
    _autocommit,
    _new_objects_not_refused,
    _outcome,
    _rls_by_table,
    _supabase_shaped_database,
    _table_privileges_not_refused,
)

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[3]
_BOOTSTRAP_SQL = _REPO_ROOT / "scripts" / "restore_bootstrap_role.sql"
_BIN_DIR_ENV = "TEST_PG_BIN_DIR"
_CLIENTS = ("pg_dump", "pg_restore", "psql")
# The four tables 043 turns RLS off on, from 043_rls_off_outside_layer_2.py:51.
_OUTSIDE_LAYER_2 = ("alembic_version", "clans", "user_profiles", "user_fcm_tokens")


# ---------------------------------------------------------------------------------------
# The client binaries
# ---------------------------------------------------------------------------------------


def _server_major() -> int:
    with _autocommit(ADMIN_URL) as conn:
        return int(conn.execute(sa.text("SHOW server_version_num")).scalar_one()) // 10000


def _client_major(bin_dir: Path) -> int | None:
    """The major version of *bin_dir*'s ``pg_dump``, or None when the directory lacks any
    of the three clients."""
    if not all((bin_dir / name).is_file() for name in _CLIENTS):
        return None
    done = subprocess.run(
        [str(bin_dir / "pg_dump"), "--version"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    found = re.search(r"\(PostgreSQL\) (\d+)", done.stdout)
    return int(found.group(1)) if found else None


def _candidate_bin_dirs() -> list[Path]:
    named = os.environ.get(_BIN_DIR_ENV)
    if named:
        return [Path(named)]
    on_path = shutil.which("pg_dump")
    return [
        *sorted(Path("/usr/lib/postgresql").glob("*/bin")),
        Path("/opt/homebrew/opt/libpq/bin"),
        Path("/usr/local/opt/libpq/bin"),
        *([Path(on_path).parent] if on_path else []),
    ]


@pytest.fixture(scope="module")
def pg_client() -> Path:
    """The directory to take ``pg_dump``, ``pg_restore`` and ``psql`` from."""
    server = _server_major()
    tried = {bin_dir: _client_major(bin_dir) for bin_dir in _candidate_bin_dirs()}
    usable = sorted(
        ((major, bin_dir) for bin_dir, major in tried.items() if major and major >= server),
        key=lambda pair: pair[0],
    )
    if not usable:
        pytest.fail(
            f"No directory holds {', '.join(_CLIENTS)} with a pg_dump of major {server} or "
            f"later, which this server needs. Tried: "
            + ", ".join(f"{d} ({m or 'absent'})" for d, m in tried.items())
            + f". Install postgresql-client-{server}, or Homebrew's libpq, or set "
            f"{_BIN_DIR_ENV} to a directory that holds all three."
        )
    return usable[0][1]


def _libpq(url: str) -> str:
    """*url* as the client binaries take it, without SQLAlchemy's driver suffix."""
    return make_url(url).set(drivername="postgresql").render_as_string(hide_password=False)


def _run(binary: Path, *args: str) -> None:
    done = subprocess.run(
        [str(binary), *args], capture_output=True, text=True, timeout=600, check=False
    )
    assert done.returncode == 0, f"{binary.name} exited {done.returncode}:\n{done.stderr[-4000:]}"


def _bootstrap(pg_client: Path, url: str) -> None:
    """``psql -f``, as the runbook and ``scripts/restore_drill.sh:149`` run the file, so it is
    read as a script, not as one statement."""
    _run(pg_client / "psql", _libpq(url), "-q", "-v", "ON_ERROR_STOP=1", "-f", str(_BOOTSTRAP_SQL))


def _restore_and_bootstrap_twice(pg_client: Path, dump: Path, url: str) -> None:
    """The runbook's two commands (``docs/ops/backup-restore.md``, "Restoring for real"), as
    *url*'s login. The bootstrap runs a second time because the file must be idempotent: the
    second run must succeed, and every reading comes after it."""
    _run(
        pg_client / "pg_restore",
        "--no-owner",
        "--no-privileges",
        "--exit-on-error",
        f"--dbname={_libpq(url)}",
        str(dump),
    )
    _bootstrap(pg_client, url)
    _bootstrap(pg_client, url)


# ---------------------------------------------------------------------------------------
# The dump, and the restore
# ---------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ChainDump:
    path: Path
    docs: dict[uuid.UUID, uuid.UUID]  # clan id -> the one document it owns
    user_id: uuid.UUID
    rls: dict[str, bool]  # table -> RLS on, read from the database the dump was taken from


@pytest.fixture(scope="module")
def chain_dump(pg_client: Path, tmp_path_factory: pytest.TempPathFactory) -> ChainDump:
    """The chain migrated on plain Postgres by the superuser, as the suite's own database
    is, holding two clans' documents and one user's rows, dumped with the flags
    ``scripts/db_backup.sh:40`` passes."""
    db_name = f"{TEST_DB_NAME[:36]}_dumpsrc_{uuid.uuid4().hex[:10]}"
    url = make_url(ADMIN_URL).set(database=db_name).render_as_string(hide_password=False)
    path = tmp_path_factory.mktemp("restore") / "chain.dump"
    docs = {uuid.uuid4(): uuid.uuid4() for _ in range(2)}
    user_id = uuid.uuid4()
    try:
        with _autocommit(ADMIN_URL) as admin:
            admin.execute(sa.text(f'CREATE DATABASE "{db_name}"'))
        _alembic_ok(url, "upgrade", "head")
        engine = sa.create_engine(url)
        try:
            with engine.begin() as conn:
                for clan_id, doc_id in docs.items():
                    conn.execute(
                        sa.text("INSERT INTO clans (id, name, slug) VALUES (:c, 'Họ Thử', :s)"),
                        {"c": clan_id, "s": f"c{clan_id.hex[:10]}"},
                    )
                    conn.execute(
                        sa.text(
                            "INSERT INTO documents "
                            "(id, clan_id, title, document_type, storage_path, created_by) "
                            "VALUES (:d, :c, 't', 'photo', :sp, :u)"
                        ),
                        {"d": doc_id, "c": clan_id, "sp": f"p/{doc_id.hex}", "u": user_id},
                    )
                conn.execute(
                    sa.text("INSERT INTO user_profiles (id, email) VALUES (:u, :e)"),
                    {"u": user_id, "e": f"{user_id.hex}@example.test"},
                )
                conn.execute(
                    sa.text("INSERT INTO user_fcm_tokens (user_id, token) VALUES (:u, :t)"),
                    {"u": user_id, "t": f"fcm-{user_id.hex}"},
                )
        finally:
            engine.dispose()
        _run(
            pg_client / "pg_dump",
            "--format=custom",
            "--no-owner",
            "--no-privileges",
            f"--file={path}",
            _libpq(url),
        )
        rls = _rls_by_table(url)
    finally:
        with _autocommit(ADMIN_URL) as admin:
            admin.execute(sa.text(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)'))
    return ChainDump(path=path, docs=docs, user_id=user_id, rls=rls)


@pytest.fixture(scope="module", params=["per_schema", "global"])
def restored(
    request: pytest.FixtureRequest, pg_client: Path, chain_dump: ChainDump
) -> Iterator[SupabaseShapedDb]:
    """The dump restored into an empty Supabase-shaped database, then the bootstrap twice,
    all as that shape's login."""
    with _supabase_shaped_database(request.param, migrate=False) as db:
        _restore_and_bootstrap_twice(pg_client, chain_dump.path, db.login_url)
        yield db


@pytest.fixture(autouse=True)
def _reset_clan_context() -> Generator[None]:
    set_request_clan_id(None)
    yield
    set_request_clan_id(None)


# ---------------------------------------------------------------------------------------
# 041: the login can enter the request role
# ---------------------------------------------------------------------------------------


async def test_the_login_enters_the_request_role_and_each_clan_sees_its_own_rows(
    restored: SupabaseShapedDb, chain_dump: ChainDump
) -> None:
    """Through the app's own seam: ``RlsSession`` issues ``SET LOCAL ROLE familyroots_app``
    on every transaction. Without 041's grant replayed the login holds ADMIN without SET,
    and the first statement fails with ``permission denied to set role``."""
    engine = create_async_engine(restored.login_url)
    request_session = async_sessionmaker(
        engine, sync_session_class=RlsSession, expire_on_commit=False
    )
    seen: dict[uuid.UUID, object] = {}
    try:
        for clan_id in chain_dump.docs:
            set_request_clan_id(clan_id)
            try:
                async with request_session() as session:
                    who = await session.scalar(sa.text("SELECT current_user"))
                    ids = await session.execute(sa.text("SELECT id FROM documents"))
                    seen[clan_id] = (who, set(ids.scalars()))
            except sa.exc.DBAPIError as exc:
                diag = getattr(exc.orig, "diag", None)
                message = getattr(diag, "message_primary", None) or str(exc.orig)
                seen[clan_id] = f"{getattr(exc.orig, 'sqlstate', '?')}: {message}"
        # The privileged read: the login owns the tables and bypasses RLS, so both
        # documents came through the dump, and each half above is isolation, not absence.
        async with engine.connect() as conn:
            every = set((await conn.execute(sa.text("SELECT id FROM documents"))).scalars())
    finally:
        await engine.dispose()

    assert seen == {clan_id: (_APP_ROLE, {doc_id}) for clan_id, doc_id in chain_dump.docs.items()}
    assert every == set(chain_dump.docs.values())


# ---------------------------------------------------------------------------------------
# 042: the Data API's roles get nothing in public
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("api_role", _DATA_API_ROLES)
def test_the_data_api_roles_are_refused_every_restored_relation(
    restored: SupabaseShapedDb, chain_dump: ChainDump, api_role: str
) -> None:
    """``pg_restore`` created every table as the login, so Supabase's default privileges
    granted these roles ALL on each. ``user_profiles`` is the one that matters most: it has
    no RLS (ADR-059), so a granted ``SELECT`` there reads every user's email. Every table
    privilege but ``REFERENCES`` is tried, because the local Supabase image grants
    ``TRUNCATE``, ``TRIGGER`` and ``MAINTAIN`` and no ``SELECT`` (042's docstring)."""
    relations, not_refused = _table_privileges_not_refused(restored.admin_url, api_role)

    assert set(Base.metadata.tables) | {"alembic_version"} <= relations
    assert not_refused == {}
    # The privileged read: the row a granted SELECT on user_profiles would return is there.
    with _autocommit(restored.login_url) as conn:
        profiles = conn.execute(
            sa.text("SELECT count(*) FROM user_profiles WHERE id = :u"), {"u": chain_dump.user_id}
        ).scalar_one()
    assert profiles == 1


@pytest.mark.parametrize("api_role", _DATA_API_ROLES)
def test_a_table_and_a_sequence_created_after_the_bootstrap_are_refused_too(
    restored: SupabaseShapedDb, api_role: str
) -> None:
    """The first migration after the recovery. The login's default privileges decide its
    grants, and in the ``global`` shape only the bootstrap's global revoke clears them."""
    assert _new_objects_not_refused(restored, api_role, "fr_after_restore") == {}


# ---------------------------------------------------------------------------------------
# 043: RLS comes back as the dump carried it
# ---------------------------------------------------------------------------------------


def test_the_request_role_reads_each_table_the_chain_leaves_outside_layer_2(
    restored: SupabaseShapedDb, chain_dump: ChainDump
) -> None:
    """Under ``ensure_rls`` each of these four came back with RLS on and no policy, so the
    request role read no row from any of them: ``/health`` answered ``behind``, and login
    found no profile. The session is the superuser's, so this does not lean on 041."""
    clan_id = next(iter(chain_dump.docs))
    user_id = chain_dump.user_id
    engine = sa.create_engine(restored.admin_url)
    try:
        with engine.connect() as conn:
            tx = conn.begin()
            try:
                conn.execute(sa.text(f"SET LOCAL ROLE {_APP_ROLE}"))
                who = conn.execute(sa.text("SELECT current_user")).scalar_one()
                seen = {
                    "alembic_version": _outcome(conn, "SELECT version_num FROM alembic_version"),
                    "clans": _outcome(conn, f"SELECT id FROM clans WHERE id = '{clan_id}'"),
                    "user_profiles": _outcome(
                        conn, f"SELECT id FROM user_profiles WHERE id = '{user_id}'"
                    ),
                    "user_fcm_tokens": _outcome(
                        conn, f"SELECT token FROM user_fcm_tokens WHERE user_id = '{user_id}'"
                    ),
                }
            finally:
                tx.rollback()
    finally:
        engine.dispose()

    assert who == _APP_ROLE
    assert seen == dict.fromkeys(_OUTSIDE_LAYER_2, "ran, 1 row(s)")


def test_every_table_keeps_the_rls_state_the_dump_carried(
    restored: SupabaseShapedDb, chain_dump: ChainDump
) -> None:
    """The bootstrap turns RLS off on 043's four tables and on nothing else."""
    after = _rls_by_table(restored.admin_url)

    # Not vacuous: the dump carries both states, and every application table is compared.
    assert set(chain_dump.rls.values()) == {True, False}
    assert set(Base.metadata.tables) | {"alembic_version"} <= set(after)
    differs = {
        name: {"dump": chain_dump.rls.get(name), "restored": after.get(name)}
        for name in sorted(set(chain_dump.rls) | set(after))
        if chain_dump.rls.get(name) != after.get(name)
    }
    assert differs == {}


# ---------------------------------------------------------------------------------------
# Plain Postgres, as a superuser: what the drill does
# ---------------------------------------------------------------------------------------


def _memberships_of_current_user(url: str) -> set[tuple[str, bool, bool, bool]]:
    with _autocommit(url) as conn:
        rows = conn.execute(
            sa.text(
                "SELECT r.rolname, a.admin_option, a.inherit_option, a.set_option "
                "FROM pg_auth_members a "
                "JOIN pg_roles r ON r.oid = a.roleid "
                "JOIN pg_roles m ON m.oid = a.member "
                "WHERE m.rolname = current_user"
            )
        ).all()
    return {(str(name), bool(adm), bool(inh), bool(st)) for name, adm, inh, st in rows}


def test_on_plain_postgres_as_a_superuser_the_bootstrap_runs_twice_and_grants_no_membership(
    pg_client: Path, chain_dump: ChainDump
) -> None:
    """``scripts/restore_drill.sh`` restores into plain Postgres as a superuser. There the
    new statements are no-ops: a superuser already may ``SET ROLE``, so 041's replay grants
    nothing; there is no ``anon``; and RLS is already off on the four tables."""
    db_name = f"{TEST_DB_NAME[:36]}_plain_{uuid.uuid4().hex[:10]}"
    url = make_url(ADMIN_URL).set(database=db_name).render_as_string(hide_password=False)
    try:
        with _autocommit(ADMIN_URL) as admin:
            admin.execute(sa.text(f'CREATE DATABASE "{db_name}"'))
        before = _memberships_of_current_user(url)
        _restore_and_bootstrap_twice(pg_client, chain_dump.path, url)
        after = _memberships_of_current_user(url)
        rls = _rls_by_table(url)
        engine = sa.create_engine(url)
        try:
            with engine.connect() as conn:
                seen: dict[uuid.UUID, set[uuid.UUID]] = {}
                for clan_id in chain_dump.docs:
                    tx = conn.begin()
                    try:
                        conn.execute(sa.text(f"SET LOCAL ROLE {_APP_ROLE}"))
                        conn.execute(
                            sa.text("SELECT set_config('app.clan_id', :c, true)"),
                            {"c": str(clan_id)},
                        )
                        seen[clan_id] = set(
                            conn.execute(sa.text("SELECT id FROM documents")).scalars()
                        )
                    finally:
                        tx.rollback()
        finally:
            engine.dispose()
    finally:
        with _autocommit(ADMIN_URL) as admin:
            admin.execute(sa.text(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)'))

    assert after == before
    assert rls == chain_dump.rls
    assert seen == {clan_id: {doc_id} for clan_id, doc_id in chain_dump.docs.items()}
