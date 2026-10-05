"""Migration 040: ``clans.slug`` has one shape, the API's and the database's (#190).

Before 040 the two rules disagreed in both directions. The API's ``_SLUG_PATTERN``
admitted a one-character code that ``ck_clans_clans_slug_format`` (migration 001)
refused, and the CHECK admitted a doubled hyphen the API refused. Each test here
writes a row and reads what Postgres did with it, or runs the migration and reads
what it left behind. None of them reads the constraint's text from the catalog: a
CHECK whose text looks right and whose verdicts are wrong would pass that.
"""

from __future__ import annotations

import itertools
import uuid
from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from pydantic import ValidationError

from app.schemas.auth import AuthenticatedOnboardingRequest

pytestmark = pytest.mark.integration

_BEFORE = "039_drop_clan_settings"
_CONSTRAINT = "ck_clans_clans_slug_format"
_INSERT = sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'Họ Thử', :slug)")


@pytest.fixture()
def alembic_cfg(migrated_db_url: str) -> Iterator[Config]:
    """Points Alembic at the session database, and leaves it at head however the test
    ends, because every integration module after this one expects head."""
    cfg = Config("alembic.ini")
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", migrated_db_url)
    yield cfg
    command.upgrade(cfg, "head")


def _verdict(conn: sa.Connection, slug: str) -> tuple[str, str | None] | None:
    """Insert one ``clans`` row in a savepoint and roll it back.

    ``None`` when the row inserts. Otherwise the SQLSTATE and the constraint Postgres
    named, so a refusal by the wrong constraint cannot pass as a refusal by this one.
    """
    savepoint = conn.begin_nested()
    try:
        conn.execute(_INSERT, {"id": uuid.uuid4(), "slug": slug})
    except sa.exc.IntegrityError as exc:
        savepoint.rollback()
        diag = getattr(exc.orig, "diag", None)
        return getattr(exc.orig, "sqlstate", ""), getattr(diag, "constraint_name", None)
    savepoint.rollback()
    return None


def _verdicts(engine: sa.Engine, slugs: list[str]) -> dict[str, tuple[str, str | None] | None]:
    with engine.connect() as conn, conn.begin() as tx:
        try:
            return {slug: _verdict(conn, slug) for slug in slugs}
        finally:
            tx.rollback()


def _api_admits(slug: str) -> bool:
    try:
        AuthenticatedOnboardingRequest(clan_action="create", clan_name="Họ Thử", clan_slug=slug)
    except ValidationError:
        return False
    return True


def _version(engine: sa.Engine) -> str:
    with engine.connect() as conn:
        return str(conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one())


_REFUSED = ("23514", _CONSTRAINT)


def test_the_check_refuses_a_doubled_hyphen_and_a_single_character(
    sync_engine: sa.Engine,
) -> None:
    """Issue reading 3, at head. The API cannot send ``a--b``, so the row goes in
    directly: this is the database's own rule, with no API in front of it."""
    assert _verdicts(sync_engine, ["a--b", "a", "ab", "a-b"]) == {
        "a--b": _REFUSED,
        "a": _REFUSED,
        "ab": None,
        "a-b": None,
    }


def test_the_check_and_the_api_agree_on_every_short_string(sync_engine: sa.Engine) -> None:
    """The issue's title, as one reading: the database refuses exactly what the API
    refuses.

    Every string of length 0 to 4 over ``a``, ``0``, ``-`` and ``A``, 341 of them,
    which reaches each shape the two rules ever disagreed on: a one-character code,
    a doubled hyphen, an edge hyphen, a capital, the empty string. Before 040 this
    list held six disagreements: ``a`` and ``0`` one way, and the four four-character
    strings with ``--`` in the middle the other.
    """
    strings = [
        "".join(chars) for length in range(5) for chars in itertools.product("a0-A", repeat=length)
    ]
    database = _verdicts(sync_engine, strings)

    disagreements = [s for s in strings if (database[s] is None) != _api_admits(s)]

    assert disagreements == []
    # Both answers occur, so an agreement on "refuse everything" cannot pass.
    assert {s for s in strings if database[s] is None} >= {"ab", "a-b", "a0a0"}
    assert all(v == _REFUSED for v in database.values() if v is not None)


def test_downgrade_restores_the_001_check(sync_engine: sa.Engine, alembic_cfg: Config) -> None:
    """Issue reading 3's control: one revision down, the 001 rule is back. A doubled
    hyphen inserts again, and a single character is still refused, as it always was."""
    command.downgrade(alembic_cfg, _BEFORE)

    assert _version(sync_engine) == _BEFORE
    assert _verdicts(sync_engine, ["a--b", "a", "ab"]) == {
        "a--b": None,
        "a": _REFUSED,
        "ab": None,
    }


def test_upgrade_refuses_rows_that_break_the_shape_and_names_each_one(
    sync_engine: sa.Engine, alembic_cfg: Config
) -> None:
    """Issue reading 4, after migration 015's precedent: refuse and list, never rewrite.

    Postgres's own constraint validation would fail this upgrade too, without the
    pre-check, but it names no row. So the exception's type is not the reading; the
    slugs in its message are. Catching either type keeps that the deciding assertion.
    """
    command.downgrade(alembic_cfg, _BEFORE)
    bad = {uuid.uuid4(): "x--y", uuid.uuid4(): "tran--gia-2"}
    with sync_engine.begin() as conn:
        for clan_id, slug in bad.items():
            conn.execute(_INSERT, {"id": clan_id, "slug": slug})

    try:
        with pytest.raises((RuntimeError, sa.exc.DBAPIError)) as failure:
            command.upgrade(alembic_cfg, "head")

        message = str(failure.value)
        assert "'x--y'" in message, message
        assert "'tran--gia-2'" in message, message
        assert _version(sync_engine) == _BEFORE
        with sync_engine.connect() as conn:
            rows = conn.execute(
                sa.text("SELECT id, slug FROM clans WHERE id = ANY(:ids)"), {"ids": list(bad)}
            ).all()
        stored: dict[uuid.UUID, str] = {row.id: row.slug for row in rows}
        assert stored == bad
    finally:
        with sync_engine.begin() as conn:
            conn.execute(sa.text("DELETE FROM clans WHERE id = ANY(:ids)"), {"ids": list(bad)})
