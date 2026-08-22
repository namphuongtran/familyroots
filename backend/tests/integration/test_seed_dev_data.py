"""``scripts/seed_dev_data.py`` against a real, migrated Postgres (seed S-073).

**What these tests cover and what they do not, stated first because it matters.**

A seeded test user has two halves: an identity in the local Supabase stack's ``auth.users``
and a clan membership in the application database. These tests exercise the
**application-database half for real** — the real upserts, against the real schema, with
the real constraints — and drive the Supabase half through a stub.

They deliberately do **not** talk to the Supabase stack. The stack is one shared container
set on a developer machine, the fixture ids are constants, and two suites running at once
would create and delete the same four ``auth.users`` rows underneath each other. That is
the ``TEST_PG_DB_NAME`` trap (ADR-016) in another costume, and there is no
per-worktree name to give it. So the GoTrue half is verified by hand instead, and
``docs/ops/seed-test-users.md`` § "Verifying it end to end" holds the procedure and the
readings.

What the stub buys is the part worth pinning anyway: ``verify`` must name **which half** is
missing. That check is pure logic over two inputs, and a stub lets a test hand it a
disagreement that a real stack would take a container restart to produce.
"""

import importlib.util
import os
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import psycopg
import pytest
import sqlalchemy as sa

pytestmark = pytest.mark.integration

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "seed_dev_data.py"


def _load_seeder() -> ModuleType:
    """Import the script by path. It lives in ``scripts/``, which is not a package."""
    spec = importlib.util.spec_from_file_location("seed_dev_data_under_test", _SCRIPT)
    assert spec is not None and spec.loader is not None, f"cannot load {_SCRIPT}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


seeder = _load_seeder()


class StubGoTrue:
    """Stands in for the GoTrue admin API.

    Starts out agreeing with the fixture. A test that wants a disagreement removes an
    identity or re-registers an email, which is what a re-created stack does for real.
    """

    def __init__(self) -> None:
        self.by_id: dict[str, dict[str, Any]] = {
            str(u.id): {
                "id": str(u.id),
                "email": u.email,
                "email_confirmed_at": "2026-08-22T00:00:00Z",
                "user_metadata": {"full_name": u.display_name},
            }
            for u in seeder.USERS
        }

    def get_user(self, user_id: uuid.UUID) -> dict[str, Any] | None:
        return self.by_id.get(str(user_id))

    def find_by_email(self, email: str) -> dict[str, Any] | None:
        for row in self.by_id.values():
            if row["email"] == email:
                return row
        return None


@pytest.fixture()
def conn(migrated_db_url: str) -> Iterator[psycopg.Connection[Any]]:
    """A psycopg connection to the throwaway migrated database, as the script opens it.

    Routed through the script's own ``app_dsn()`` so the SQLAlchemy ``+psycopg`` suffix
    stripping is exercised rather than assumed.
    """
    os.environ["DATABASE_URL"] = migrated_db_url
    dsn = seeder.app_dsn()
    assert "+psycopg" not in dsn, f"app_dsn() left a driver suffix in {dsn!r}"
    with psycopg.connect(dsn) as connection:
        yield connection


@pytest.fixture()
def seeded(conn):
    """The fixture applied once, to a database that starts without it."""
    seeder.assert_schema(conn)
    written = seeder.apply_app_database(conn)
    return written


def _fixture_tuples() -> set[tuple[str, str, str]]:
    return {(u.email, u.clan.slug, u.role) for u in seeder.USERS}


def _rows_as_tuples(conn: psycopg.Connection[Any]) -> set[tuple[str, str, str]]:
    """(email, clan slug, role) read back from the database, for approved memberships."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT p.email, c.slug, r.role
            FROM user_clan_roles r
            JOIN user_profiles p ON p.id = r.user_id
            JOIN clans c ON c.id = r.clan_id
            WHERE r.is_approved
            """
        )
        return {(row[0], row[1], row[2]) for row in cur.fetchall()}


# ── The fixture lands, exactly ────────────────────────────────────────────────


def test_apply_writes_the_whole_fixture_and_nothing_else(conn, seeded):
    """Read the rows back, do not trust the return value.

    The assertion is the set of (email, clan, role) triples the database actually holds,
    joined through the real foreign keys. A seeder that wrote a role into the wrong clan,
    or left ``is_approved`` false, fails here — the counts it reported would not.
    """
    assert _rows_as_tuples(conn) == _fixture_tuples()
    assert seeded == {"clans": 2, "user_profiles": 4, "user_clan_roles": 4}


def test_the_fixture_covers_admin_editor_viewer_and_a_second_clan(conn, seeded):
    """S-073's end state, asserted against the database rather than the source."""
    rows = _rows_as_tuples(conn)
    roles_in_main_clan = {role for _, slug, role in rows if slug == seeder.CLAN_A.slug}
    assert {"admin", "editor", "viewer"} <= roles_in_main_clan
    other_clans = {slug for _, slug, _ in rows if slug != seeder.CLAN_A.slug}
    assert other_clans, "no user belongs to a second clan, so isolation has only one side"


def test_the_two_clans_have_disjoint_member_sets(conn, seeded):
    """The reason the second clan exists, asserted at the database layer.

    Clan isolation cannot be tested from inside one clan. If every seeded user were a
    member of both clans, every "clan B cannot see this" assertion built on this fixture
    would be vacuous and would still pass.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT clan_id, array_agg(user_id ORDER BY user_id) "
            "FROM user_clan_roles WHERE is_approved GROUP BY clan_id"
        )
        members = {str(row[0]): {str(u) for u in row[1]} for row in cur.fetchall()}
    assert {str(seeder.CLAN_A.id), str(seeder.CLAN_B.id)} <= set(members), (
        f"both seeded clans must have approved members; found only {sorted(members)}"
    )
    a = members[str(seeder.CLAN_A.id)]
    b = members[str(seeder.CLAN_B.id)]
    assert a and b, f"both clans must have members: A={a}, B={b}"
    assert a.isdisjoint(b), f"a user is in both clans, so neither side is 'outside': {a & b}"


# ── Running it twice ──────────────────────────────────────────────────────────


def test_a_second_apply_writes_no_row_and_changes_no_timestamp(conn, seeded):
    """Idempotency, asserted as a state diff and not as "it did not crash".

    ``updated_at`` is part of the compared state on purpose. Without the ``WHERE`` guard
    on each ``DO UPDATE``, every row would be rewritten and every ``updated_at`` would
    move, while a test that compared only the business columns stayed green.
    """
    before = seeder.read_app_database(conn)
    written = seeder.apply_app_database(conn)
    after = seeder.read_app_database(conn)

    assert written == {"clans": 0, "user_profiles": 0, "user_clan_roles": 0}
    assert after == before


def test_apply_repairs_only_the_row_that_drifted(conn, seeded):
    """A repair run must not rewrite the rows that were already right."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE user_clan_roles SET role = 'viewer' WHERE user_id = %s",
            (str(seeder.USERS[1].id),),
        )
    conn.commit()

    written = seeder.apply_app_database(conn)

    assert written == {"clans": 0, "user_profiles": 0, "user_clan_roles": 1}
    assert _rows_as_tuples(conn) == _fixture_tuples()


# ── The negative control: a missing half must be named as one ─────────────────


def test_verify_is_silent_when_both_halves_agree(conn, seeded):
    """The passing reading. It has to differ from the failing one below, or neither
    reading is evidence."""
    assert seeder.verify(conn, StubGoTrue(), "http://supabase.localhost:54321") == []


def test_a_missing_membership_row_is_named_as_a_missing_half(conn, seeded):
    """**This is the defect S-073 exists to prevent, planted on purpose.**

    Delete one user's ``user_clan_roles`` row and leave the Supabase identity. The user
    still logs in. Every clan-scoped request then answers
    ``403 no_approved_clan_membership`` — measured through the running API on 2026-08-22
    and quoted in docs/ops/seed-test-users.md — which reads as an authorization bug and
    is not one.

    So the assertion is not "verify returned a problem". It is that the problem text
    names the table whose row is gone and says, in words, that this is not a permissions
    error. A message that only said "user cannot access clan" would pass a weaker test
    and would leave the reader exactly where they started.
    """
    user = seeder.USERS[1]
    with conn.cursor() as cur:
        cur.execute("DELETE FROM user_clan_roles WHERE user_id = %s", (str(user.id),))
    conn.commit()

    problems = seeder.verify(conn, StubGoTrue(), "http://supabase.localhost:54321")

    assert len(problems) == 1, problems
    text = problems[0]
    assert user.email in text
    assert "user_clan_roles" in text
    assert "MISSING" in text
    assert "application database" in text
    assert "NOT a permissions bug" in text
    assert user.role in text and user.clan.slug in text


def test_a_missing_identity_is_named_against_the_supabase_half(conn, seeded):
    """The other direction. The application database is complete; the identity is gone.

    The message must point at ``auth.users``, not at the application database, or it
    sends the reader to re-run migrations for a problem migrations cannot fix.
    """
    stub = StubGoTrue()
    user = seeder.USERS[2]
    del stub.by_id[str(user.id)]

    problems = seeder.verify(conn, stub, "http://supabase.localhost:54321")

    assert len(problems) == 1, problems
    assert "auth.users" in problems[0]
    assert user.email in problems[0]
    assert "user_clan_roles" not in problems[0]


def test_an_unconfirmed_identity_is_named_before_anyone_blames_the_password(conn, seeded):
    """An unconfirmed user gets ``400 email_not_confirmed`` from the password grant, so
    they never reach the backend at all. Recorded in docs/ops/local-supabase.md."""
    stub = StubGoTrue()
    user = seeder.USERS[0]
    stub.by_id[str(user.id)]["email_confirmed_at"] = None

    problems = seeder.verify(conn, stub, "http://supabase.localhost:54321")

    assert len(problems) == 1, problems
    assert "UNCONFIRMED" in problems[0]
    assert "email_not_confirmed" in problems[0]


def test_a_deactivated_profile_is_named_rather_than_read_as_a_role_problem(conn, seeded):
    """``is_active = false`` gives ``403 account_deactivated``, which is a different row
    from a missing membership and must not be reported as one."""
    user = seeder.USERS[0]
    with conn.cursor() as cur:
        cur.execute("UPDATE user_profiles SET is_active = false WHERE id = %s", (str(user.id),))
    conn.commit()

    problems = seeder.verify(conn, StubGoTrue(), "http://supabase.localhost:54321")

    assert len(problems) == 1, problems
    assert "account_deactivated" in problems[0]


def test_an_email_registered_under_another_id_stops_apply_before_it_writes(conn, seeded):
    """The one drift ``apply`` cannot repair, so it must refuse rather than half-run.

    GoTrue answers ``422 email_exists`` when a fixture id is absent and its email is held
    by another id — measured 2026-08-22 by planting it against the live stack. Without
    this guard the run creates some identities, hits the 422, and leaves the two
    databases further apart than it found them.
    """
    stub = StubGoTrue()
    user = seeder.USERS[2]
    stray_id = "99999999-9999-4999-8999-999999999999"
    del stub.by_id[str(user.id)]
    stub.by_id[stray_id] = {
        "id": stray_id,
        "email": user.email,
        "email_confirmed_at": "2026-08-22T00:00:00Z",
        "user_metadata": {"full_name": user.display_name},
    }

    with pytest.raises(seeder.ConfigError) as exc:
        seeder.assert_no_email_drift(stub)

    message = str(exc.value)
    assert str(user.id) in message and stray_id in message
    assert "422" in message
    assert "CANNOT" in seeder.verify(conn, stub, "http://x")[0]


# ── The other loud failure: a database nobody migrated ────────────────────────


def test_an_unmigrated_database_is_named_as_unmigrated(migrated_db_url: str) -> None:
    """A database with no ``user_clan_roles`` must produce "run alembic", not a
    ``psycopg.errors.UndefinedTable`` traceback the reader has to interpret."""
    admin_dsn = migrated_db_url.replace("+psycopg", "").rsplit("/", 1)[0] + "/postgres"
    with psycopg.connect(admin_dsn) as bare, pytest.raises(seeder.ConfigError) as exc:
        seeder.assert_schema(bare)
    message = str(exc.value)
    assert "alembic upgrade head" in message
    assert "user_clan_roles" in message


# ── Guards on the fixture itself ──────────────────────────────────────────────


def test_every_fixture_email_survives_the_api_s_own_email_validator():
    """``.test`` and ``.local`` are rejected by ``EmailStr`` as reserved names, so an
    identity at such an address logs in nowhere: ``POST /api/v1/auth/login`` answers
    ``422 validation_error`` on ``body.email`` before it ever reaches Supabase. Measured
    2026-08-22. This asserts the outcome — the request DTO accepting the address — rather
    than the domain string the fixture happens to use.
    """
    from app.schemas.auth import LoginRequest

    for user in seeder.USERS:
        LoginRequest(email=user.email, password="dev-password-s073")


def test_the_seeder_refuses_a_supabase_url_that_is_not_local(monkeypatch):
    """It creates users with a published password. Pointing it at a hosted project must
    fail before the first request, not after it."""
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "irrelevant")
    monkeypatch.setenv("SUPABASE_URL", "https://abcdefgh.supabase.co")
    with pytest.raises(seeder.ConfigError) as exc:
        seeder.supabase_config()
    assert "local" in str(exc.value)

    monkeypatch.setenv("SUPABASE_URL", "http://supabase.localhost:54321")
    url, service_role_key = seeder.supabase_config()
    assert url == "http://supabase.localhost:54321"
    assert service_role_key == "irrelevant"


def test_the_migrated_schema_still_carries_what_the_seeder_writes_into(sync_engine):
    """If a later migration renames a column the seeder writes, this fails here rather
    than at 2 a.m. inside a `make seed` a developer is running for the first time."""
    inspector = sa.inspect(sync_engine)
    for table, needed in (
        ("clans", {"id", "name", "slug", "description", "is_active"}),
        ("user_profiles", {"id", "email", "display_name", "is_active", "platform_role"}),
        (
            "user_clan_roles",
            {"id", "clan_id", "user_id", "role", "is_approved", "approved_by"},
        ),
    ):
        columns = {c["name"] for c in inspector.get_columns(table)}
        assert needed <= columns, f"{table} is missing {needed - columns}"
