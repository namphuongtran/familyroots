"""Migrations 041 and 042 on a database shaped like the Supabase project's (#251, ADR-066).

The suite's own database is migrated by a superuser. A superuser may ``SET ROLE`` to any
role, and no ``anon`` sits beside it, so that database can show neither defect this pair
fixes. This module builds the shape the local Supabase stack showed on 2026-10-10
(``supabase/postgres:17.6.1.084``) in a throwaway database of the same cluster. It applies
the real chain as that shape's login, then reads what each role can do:

- **The login** is ``NOSUPERUSER CREATEROLE CREATEDB BYPASSRLS``, like Supabase's
  ``postgres``.
- **The login's membership in ``familyroots_app``** is whatever this server gives a role's
  non-superuser creator. The fixture does not write those options down: the login creates
  a probe role, and the fixture copies the probe's options onto ``familyroots_app``. On
  Postgres 16+ with ``createrole_self_grant`` empty, that is ADMIN without SET. The login
  cannot be the role's literal creator here, because the role is cluster-wide and other
  suites share it.
- **``anon`` and ``authenticated``** hold ``USAGE`` on ``public``. Before the chain runs,
  they also hold Supabase's legacy default ``GRANT ALL`` on tables, sequences and
  functions, which is the worst case. That default is parametrized. ``per_schema`` is the
  form Supabase uses, and ``global`` is the form a per-schema revoke cannot undo.

**Every verdict reads an outcome**: a statement run as a role, and the error or rows it
produced (``.claude/rules/testing.md``, "A test pins an outcome, not a setting"). The
catalog is read only to build the fixture and to list what to try.

**Roles are cluster objects.** The login and the no-grant role carry a random suffix.
``anon`` and ``authenticated`` cannot, because 042 names them. So the fixture creates
whichever is missing and drops only those it created.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from collections.abc import AsyncGenerator, Generator, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)

import app.models  # noqa: F401  (registers every table on Base.metadata)
from app.core.database import RlsSession
from app.core.rls import set_request_clan_id
from app.models.base import Base
from tests.integration.conftest import ADMIN_URL, TEST_DB_NAME

pytestmark = pytest.mark.integration

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_APP_ROLE = "familyroots_app"
_DATA_API_ROLES = ("anon", "authenticated")
_BEFORE_041 = "040_clan_slug_one_shape"
# A throwaway login in a throwaway database, dropped at teardown.
_LOGIN_PASSWORD = "supabase-shaped-login"
_SET_ROLE_REFUSED = f'42501: permission denied to set role "{_APP_ROLE}"'
# The noun Postgres uses in "permission denied for <noun> <name>", per pg_class.relkind.
_RELKIND_NOUN = {
    "r": "table",
    "p": "table",
    "v": "view",
    "m": "materialized view",
    "f": "foreign table",
}
# One literal per argument type the app's routines take. A routine taking any other type
# fails the routine test by name, which is the prompt to add a row here.
_SAMPLE_ARGUMENT = {"uuid": "gen_random_uuid()", "integer": "3", "text": "'Nguyễn'"}


@dataclass(frozen=True)
class SupabaseShapedDb:
    shape: str
    login: str
    no_grant_role: str
    creator_options: tuple[bool, bool, bool]
    login_url: str
    admin_url: str


def _alembic(url: str, *args: str) -> subprocess.CompletedProcess[str]:
    """Run the Alembic CLI as its own process, as ``render.yaml``'s ``preDeployCommand``
    does, so the chain runs as *url*'s login.

    ``migrations/env.py`` takes its URL from ``settings.DATABASE_URL``, a cached singleton
    the session fixture already pointed at the suite's database, so an in-process run
    would migrate that database instead.
    """
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=_BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": url},
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )


def _alembic_ok(url: str, *args: str) -> None:
    done = _alembic(url, *args)
    assert done.returncode == 0, f"alembic {' '.join(args)} failed:\n{done.stderr[-4000:]}"


@contextmanager
def _autocommit(url: str) -> Iterator[sa.Connection]:
    engine = sa.create_engine(url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            yield conn
    finally:
        engine.dispose()


def _outcome(conn: sa.Connection, sql: str) -> str:
    """Run *sql* in a savepoint and roll it back. Report what the server did: ``"ran"``,
    ``"ran, N row(s)"``, or ``"<SQLSTATE>: <primary message>"``."""
    savepoint = conn.begin_nested()
    try:
        result = conn.execute(sa.text(sql))
        count = len(result.fetchall()) if result.returns_rows else result.rowcount
        return f"ran, {count} row(s)" if count >= 0 else "ran"
    except sa.exc.DBAPIError as exc:
        diag = getattr(exc.orig, "diag", None)
        message = getattr(diag, "message_primary", None) or str(exc.orig)
        return f"{getattr(exc.orig, 'sqlstate', '?')}: {message}"
    finally:
        savepoint.rollback()


def _creator_options(login_url: str, suffix: str) -> tuple[bool, bool, bool]:
    """The (ADMIN, INHERIT, SET) options this server gives a role's non-superuser
    creator, read by having the login create a role and drop it again."""
    probe = f"fr_probe_{suffix}"
    with _autocommit(login_url) as conn:
        conn.execute(sa.text(f"CREATE ROLE {probe} NOLOGIN"))
        try:
            row = conn.execute(
                sa.text(
                    "SELECT a.admin_option, a.inherit_option, a.set_option "
                    "FROM pg_auth_members a "
                    "JOIN pg_roles r ON r.oid = a.roleid "
                    "JOIN pg_roles m ON m.oid = a.member "
                    "WHERE r.rolname = :probe AND m.rolname = current_user"
                ),
                {"probe": probe},
            ).one()
        finally:
            conn.execute(sa.text(f"DROP ROLE {probe}"))
    return bool(row[0]), bool(row[1]), bool(row[2])


def _grant_creator_options(admin: sa.Connection, login: str, opts: tuple[bool, bool, bool]) -> None:
    admin_opt, inherit_opt, set_opt = (str(o).upper() for o in opts)
    admin.execute(
        sa.text(
            f"GRANT {_APP_ROLE} TO {login} "
            f"WITH ADMIN {admin_opt}, INHERIT {inherit_opt}, SET {set_opt}"
        )
    )


@contextmanager
def _supabase_shaped_database(shape: str) -> Iterator[SupabaseShapedDb]:
    suffix = uuid.uuid4().hex[:10]
    login = f"fr_supa_login_{suffix}"
    no_grant_role = f"fr_no_grant_{suffix}"
    db_name = f"{TEST_DB_NAME[:36]}_supa_{suffix}"
    server = make_url(ADMIN_URL)
    admin_url = server.set(database=db_name).render_as_string(hide_password=False)
    login_url = server.set(username=login, password=_LOGIN_PASSWORD, database=db_name)
    login_url_str = login_url.render_as_string(hide_password=False)
    created_api_roles: list[str] = []

    try:
        with _autocommit(ADMIN_URL) as admin:
            admin.execute(
                sa.text(
                    f"CREATE ROLE {login} LOGIN PASSWORD '{_LOGIN_PASSWORD}' "
                    "NOSUPERUSER CREATEROLE CREATEDB BYPASSRLS"
                )
            )
            admin.execute(sa.text(f"CREATE ROLE {no_grant_role} NOLOGIN"))
            for role in _DATA_API_ROLES:
                found = admin.execute(
                    sa.text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": role}
                ).first()
                if found is None:
                    admin.execute(sa.text(f"CREATE ROLE {role} NOLOGIN"))
                    created_api_roles.append(role)
            # Migration 002's own guard, so a cluster that has never run the chain works too.
            admin.execute(
                sa.text(
                    f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = "
                    f"'{_APP_ROLE}') THEN CREATE ROLE {_APP_ROLE} NOLOGIN; END IF; END $$"
                )
            )
            admin.execute(sa.text(f'CREATE DATABASE "{db_name}" OWNER {login}'))

        creator_options = _creator_options(login_url_str, suffix)
        with _autocommit(ADMIN_URL) as admin:
            _grant_creator_options(admin, login, creator_options)

        with _autocommit(login_url_str) as conn:
            conn.execute(sa.text("GRANT USAGE ON SCHEMA public TO anon, authenticated"))
            scope = "IN SCHEMA public " if shape == "per_schema" else ""
            for kind in ("TABLES", "SEQUENCES", "FUNCTIONS"):
                conn.execute(
                    sa.text(
                        f"ALTER DEFAULT PRIVILEGES {scope}"
                        f"GRANT ALL ON {kind} TO anon, authenticated"
                    )
                )

        _alembic_ok(login_url_str, "upgrade", "head")

        yield SupabaseShapedDb(
            shape=shape,
            login=login,
            no_grant_role=no_grant_role,
            creator_options=creator_options,
            login_url=login_url_str,
            admin_url=admin_url,
        )
    finally:
        with _autocommit(ADMIN_URL) as admin:
            admin.execute(sa.text(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)'))
            admin.execute(sa.text(f"DROP ROLE IF EXISTS {login}"))
            admin.execute(sa.text(f"DROP ROLE IF EXISTS {no_grant_role}"))
            for role in created_api_roles:
                admin.execute(sa.text(f"DROP ROLE IF EXISTS {role}"))


@pytest.fixture(scope="module", params=["per_schema", "global"])
def supabase_db(request: pytest.FixtureRequest) -> Iterator[SupabaseShapedDb]:
    with _supabase_shaped_database(request.param) as db:
        yield db


@pytest.fixture()
async def login_engine(supabase_db: SupabaseShapedDb) -> AsyncGenerator[AsyncEngine]:
    engine = create_async_engine(supabase_db.login_url)
    yield engine
    await engine.dispose()


@pytest.fixture(autouse=True)
def _reset_clan_context() -> Generator[None]:
    set_request_clan_id(None)
    yield
    set_request_clan_id(None)


# ---------------------------------------------------------------------------------------
# 041: the login can enter the request role
# ---------------------------------------------------------------------------------------


async def _seed_clan_with_doc(conn: AsyncConnection, clan_id: uuid.UUID) -> uuid.UUID:
    await conn.execute(
        sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'Họ Thử', :s)"),
        {"id": clan_id, "s": f"c{clan_id.hex[:10]}"},
    )
    doc_id = uuid.uuid4()
    await conn.execute(
        sa.text(
            "INSERT INTO documents (id, clan_id, title, document_type, storage_path, created_by) "
            "VALUES (:id, :c, 't', 'photo', :sp, :cb)"
        ),
        {"id": doc_id, "c": clan_id, "sp": f"p/{doc_id.hex}", "cb": uuid.uuid4()},
    )
    return doc_id


async def test_the_login_enters_the_request_role_and_two_clans_stay_apart(
    login_engine: AsyncEngine,
) -> None:
    """The boot gate's two questions, then two-sided isolation, through the app's own seam.

    ``RlsSession`` issues ``SET LOCAL ROLE familyroots_app`` and the ``app.clan_id`` GUC on
    every transaction (``app/core/rls.py``). Without 041 the first statement fails there,
    with ``permission denied to set role``. The login is BYPASSRLS, like Supabase's
    ``postgres``, so the isolation below holds only because the role really changed.
    """
    clan_a, clan_b = uuid.uuid4(), uuid.uuid4()
    async with login_engine.begin() as conn:  # the login itself: table owner, BYPASSRLS
        doc_a = await _seed_clan_with_doc(conn, clan_a)
        doc_b = await _seed_clan_with_doc(conn, clan_b)

    request_session = async_sessionmaker(
        login_engine, sync_session_class=RlsSession, expire_on_commit=False
    )
    seen: dict[uuid.UUID, tuple[object, object, set[uuid.UUID]]] = {}
    for clan in (clan_a, clan_b):
        set_request_clan_id(clan)
        async with request_session() as session:
            # app/main.py's production boot gate asks exactly these two.
            who = await session.scalar(sa.text("SELECT current_user"))
            bypass = await session.scalar(
                sa.text("SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user")
            )
            ids = set((await session.execute(sa.text("SELECT id FROM documents"))).scalars())
        seen[clan] = (who, bypass, ids)

    assert seen == {
        clan_a: (_APP_ROLE, False, {doc_a}),
        clan_b: (_APP_ROLE, False, {doc_b}),
    }
    # The privileged read: both rows exist, so each half above is isolation, not absence.
    async with login_engine.connect() as conn:
        both = set((await conn.execute(sa.text("SELECT id FROM documents"))).scalars())
    assert both == {doc_a, doc_b}


def _set_role_outcome(url: str) -> str:
    """What the server says to ``SET LOCAL ROLE familyroots_app`` from *url*'s login."""
    engine = sa.create_engine(url)
    try:
        with engine.connect() as conn:
            tx = conn.begin()
            try:
                return _outcome(conn, f"SET LOCAL ROLE {_APP_ROLE}")
            finally:
                tx.rollback()
    finally:
        engine.dispose()


def _restore_head(db: SupabaseShapedDb) -> None:
    """Put the shaped database back as the fixture left it, whatever a test did: at 040
    with no self-grant, the creator's options back on, then upgrade so 041 grants again."""
    _alembic_ok(db.login_url, "downgrade", _BEFORE_041)
    with _autocommit(db.login_url) as conn:
        conn.execute(
            sa.text(
                f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_auth_members a "
                f"JOIN pg_roles r ON r.oid = a.roleid JOIN pg_roles m ON m.oid = a.member "
                f"WHERE r.rolname = '{_APP_ROLE}' AND m.rolname = current_user "
                f"AND a.grantor = a.member) THEN "
                f"REVOKE {_APP_ROLE} FROM CURRENT_USER GRANTED BY CURRENT_USER; END IF; END $$"
            )
        )
    with _autocommit(ADMIN_URL) as admin:
        _grant_creator_options(admin, db.login, db.creator_options)
    _alembic_ok(db.login_url, "upgrade", "head")


def test_041_downgrade_revokes_the_grant_it_made_and_no_other(
    supabase_db: SupabaseShapedDb,
) -> None:
    url = supabase_db.login_url
    try:
        at_head = _set_role_outcome(url)
        _alembic_ok(url, "downgrade", _BEFORE_041)
        after_downgrade = _set_role_outcome(url)

        # A self-grant made by hand, with INHERIT, is not the grant 041 makes. 041 finds
        # SET already held and does nothing, and its downgrade must leave the hand grant.
        with _autocommit(url) as conn:
            conn.execute(sa.text(f"GRANT {_APP_ROLE} TO CURRENT_USER WITH INHERIT TRUE, SET TRUE"))
        _alembic_ok(url, "upgrade", "head")
        _alembic_ok(url, "downgrade", _BEFORE_041)
        hand_grant_after_downgrade = _set_role_outcome(url)
    finally:
        _restore_head(supabase_db)

    assert (at_head, after_downgrade, hand_grant_after_downgrade) == (
        "ran",
        _SET_ROLE_REFUSED,
        "ran",
    )
    assert _set_role_outcome(url) == "ran"


def test_041_names_a_login_that_can_neither_enter_nor_grant_the_role(
    supabase_db: SupabaseShapedDb,
) -> None:
    """Without the creator's ADMIN grant there is nothing 041 can do. The upgrade fails
    and names the login, rather than leaving a database the application cannot open."""
    url = supabase_db.login_url
    try:
        _alembic_ok(url, "downgrade", _BEFORE_041)
        with _autocommit(ADMIN_URL) as admin:
            admin.execute(sa.text(f"REVOKE {_APP_ROLE} FROM {supabase_db.login}"))
        done = _alembic(url, "upgrade", "head")
        with _autocommit(url) as conn:
            version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar()
    finally:
        _restore_head(supabase_db)

    assert done.returncode != 0
    assert (
        f"login {supabase_db.login} can neither SET ROLE {_APP_ROLE} nor grant it"
    ) in done.stderr
    assert version == _BEFORE_041  # the whole upgrade rolled back, 042 included


# ---------------------------------------------------------------------------------------
# 042: the Data API's roles hold nothing in public
# ---------------------------------------------------------------------------------------


def _seed_user_rows(login_url: str) -> dict[str, uuid.UUID]:
    """One row in each table ADR-059 leaves outside layer 2, plus a role row, so that a
    read the privilege layer let through would have something to return."""
    clan_id, user_id = uuid.uuid4(), uuid.uuid4()
    engine = sa.create_engine(login_url)
    try:
        with engine.begin() as conn:
            conn.execute(
                sa.text("INSERT INTO clans (id, name, slug) VALUES (:c, 'Họ Thử', :s)"),
                {"c": clan_id, "s": f"c{clan_id.hex[:10]}"},
            )
            conn.execute(
                sa.text("INSERT INTO user_profiles (id, email) VALUES (:u, :e)"),
                {"u": user_id, "e": f"{user_id.hex}@example.test"},
            )
            conn.execute(
                sa.text("INSERT INTO user_fcm_tokens (user_id, token) VALUES (:u, :t)"),
                {"u": user_id, "t": f"fcm-{user_id.hex}"},
            )
            conn.execute(
                sa.text(
                    "INSERT INTO user_clan_roles "
                    "(clan_id, user_id, role, is_approved, approved_by, approved_at) "
                    "VALUES (:c, :u, 'admin', true, :u, now())"
                ),
                {"c": clan_id, "u": user_id},
            )
    finally:
        engine.dispose()
    return {"clan_id": clan_id, "user_id": user_id}


def _public_relations(conn: sa.Connection) -> dict[str, str]:
    """Every relation in ``public`` an API could address, by name, with its noun. Extension
    members are left out: they belong to the extension, not to the application."""
    rows = conn.execute(
        sa.text(
            "SELECT c.relname, c.relkind FROM pg_class c "
            "WHERE c.relnamespace = 'public'::regnamespace "
            "AND c.relkind IN ('r', 'p', 'v', 'm', 'f') "
            "AND NOT EXISTS (SELECT 1 FROM pg_depend d "
            "WHERE d.classid = 'pg_class'::regclass AND d.objid = c.oid AND d.deptype = 'e')"
        )
    ).all()
    return {str(name): _RELKIND_NOUN[str(kind)] for name, kind in rows}


@pytest.mark.parametrize("api_role", _DATA_API_ROLES)
def test_the_data_api_roles_are_refused_select_and_insert_on_every_table(
    supabase_db: SupabaseShapedDb, api_role: str
) -> None:
    seeded = _seed_user_rows(supabase_db.login_url)
    engine = sa.create_engine(supabase_db.admin_url)
    try:
        with engine.connect() as conn:
            relations = _public_relations(conn)
            conn.rollback()  # end the catalog read's implicit transaction
            tx = conn.begin()
            try:
                conn.execute(sa.text(f"SET LOCAL ROLE {api_role}"))
                not_refused: dict[str, str] = {}
                for name, noun in sorted(relations.items()):
                    refused = f"42501: permission denied for {noun} {name}"
                    for verb, sql in (
                        ("SELECT", f'SELECT * FROM public."{name}"'),
                        ("INSERT", f'INSERT INTO public."{name}" DEFAULT VALUES'),
                    ):
                        outcome = _outcome(conn, sql)
                        if outcome != refused:
                            not_refused[f"{verb} {name}"] = outcome
            finally:
                tx.rollback()
    finally:
        engine.dispose()

    # Every application table was tried, so an empty list of tries cannot pass.
    assert set(Base.metadata.tables) | {"alembic_version"} <= set(relations)
    assert not_refused == {}
    # The privileged read: the rows a refused read would have returned are there.
    with _autocommit(supabase_db.login_url) as conn:
        present = conn.execute(
            sa.text(
                "SELECT (SELECT count(*) FROM user_profiles WHERE id = :u), "
                "(SELECT count(*) FROM user_fcm_tokens WHERE user_id = :u), "
                "(SELECT count(*) FROM user_clan_roles WHERE user_id = :u AND clan_id = :c)"
            ),
            {"u": seeded["user_id"], "c": seeded["clan_id"]},
        ).one()
    assert tuple(present) == (1, 1, 1)


@pytest.mark.parametrize("api_role", _DATA_API_ROLES)
def test_a_routine_gives_the_data_api_roles_nothing_a_role_without_grants_lacks(
    supabase_db: SupabaseShapedDb, api_role: str
) -> None:
    """The Data API serves a routine in an exposed schema at ``/rpc``.

    042 revokes the two roles' own EXECUTE, but ``PUBLIC`` keeps Postgres's default
    EXECUTE on functions, and every role inherits that. So the claim is the comparison:
    called as ``anon``, each routine does exactly what it does for a role that holds no
    grant at all. Trigger routines cannot be called, and extension members are not the
    application's.
    """
    engine = sa.create_engine(supabase_db.admin_url)
    try:
        with engine.connect() as conn:
            routines = conn.execute(
                sa.text(
                    "SELECT p.proname, "
                    "array(SELECT format_type(t, NULL) FROM unnest(p.proargtypes) t) "
                    "FROM pg_proc p "
                    "WHERE p.pronamespace = 'public'::regnamespace AND p.prokind = 'f' "
                    "AND p.prorettype <> 'trigger'::regtype "
                    "AND NOT EXISTS (SELECT 1 FROM pg_depend d "
                    "WHERE d.classid = 'pg_proc'::regclass AND d.objid = p.oid "
                    "AND d.deptype = 'e') "
                    "ORDER BY 1"
                )
            ).all()
            unknown = sorted(
                {str(t) for _, types in routines for t in types} - set(_SAMPLE_ARGUMENT)
            )
            conn.rollback()  # end the catalog read's implicit transaction
            assert unknown == [], f"add a sample argument for {unknown}"
            calls = {
                str(name): (
                    f'SELECT * FROM public."{name}"('
                    + ", ".join(_SAMPLE_ARGUMENT[str(t)] for t in types)
                    + ")"
                )
                for name, types in routines
            }

            outcomes: dict[str, dict[str, str]] = {}
            for role in (supabase_db.no_grant_role, api_role):
                tx = conn.begin()
                try:
                    conn.execute(sa.text(f"SET LOCAL ROLE {role}"))
                    outcomes[role] = {name: _outcome(conn, sql) for name, sql in calls.items()}
                finally:
                    tx.rollback()
    finally:
        engine.dispose()

    baseline = outcomes[supabase_db.no_grant_role]
    # Not vacuous: some routine reads a table, and the no-grant role is refused there.
    assert any(o.startswith("42501: permission denied for table") for o in baseline.values())
    assert outcomes[api_role] == baseline


@pytest.mark.parametrize("api_role", _DATA_API_ROLES)
def test_a_table_and_a_sequence_created_after_042_are_refused_too(
    supabase_db: SupabaseShapedDb, api_role: str
) -> None:
    """The next migration's objects. They are created by the login, so the login's default
    privileges decide their grants, in whichever shape the fixture set them."""
    engine = sa.create_engine(supabase_db.admin_url)
    try:
        with engine.connect() as conn:
            tx = conn.begin()
            try:
                conn.execute(sa.text(f"SET LOCAL ROLE {supabase_db.login}"))
                conn.execute(sa.text("CREATE TABLE public.fr_after_042 (id integer)"))
                conn.execute(sa.text("CREATE SEQUENCE public.fr_after_042_seq"))
                conn.execute(sa.text("INSERT INTO public.fr_after_042 VALUES (1)"))
                conn.execute(sa.text(f"SET LOCAL ROLE {api_role}"))
                outcomes = {
                    "SELECT": _outcome(conn, "SELECT * FROM public.fr_after_042"),
                    "INSERT": _outcome(conn, "INSERT INTO public.fr_after_042 VALUES (2)"),
                    "nextval": _outcome(conn, "SELECT nextval('public.fr_after_042_seq')"),
                }
            finally:
                tx.rollback()
    finally:
        engine.dispose()

    assert outcomes == {
        "SELECT": "42501: permission denied for table fr_after_042",
        "INSERT": "42501: permission denied for table fr_after_042",
        "nextval": "42501: permission denied for sequence fr_after_042_seq",
    }
