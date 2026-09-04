"""The RLS request seam sets `SET LOCAL ROLE` + `app.clan_id`, and NOTHING else.

ADR-008 § 2 promised the seam would inject `app.clan_id` *and* `app.user_id`.
The shipped seam never wrote the second one. That disagreement survived roughly two months
and was closed by [ADR-047](../../../docs/decisions/047-rls-seam-sets-clan-id-only.md) on
2026-08-22, which corrected the ADR rather than building the missing half. It survived
because **no gate could see it**: `test_rls_activation.py` asserts that `current_user` and
`app.clan_id` hold the right values, which stays true whether the seam writes two settings
or twenty. This file is the missing half — it pins the *exact set*, so a setting added to
the seam fails the suite until someone updates the assertion on purpose.

## Why the settings are captured at the driver, not read out of the database

The obvious mechanism is to enumerate the settings from Postgres and filter the built-in
noise. **On this Postgres that does not work.** The measurement is recorded here because
the next reader will reach for `pg_settings` too. Run 2026-08-22 against the
`familyroots-pgdb` container, `server_version` = `18.4`:

    $ psql -U postgres -c "BEGIN; SET LOCAL app.foo='bar';
          SELECT count(*) FROM pg_settings WHERE name LIKE 'app.%'; SHOW app.foo; COMMIT;"
    count: 0
    app.foo: bar

    $ psql -U postgres -c "BEGIN; SET LOCAL ROLE probe_role;
          SELECT name FROM pg_settings WHERE name='role'; SELECT current_user; COMMIT;"
    name: <no rows>
    current_user: probe_role

A custom placeholder GUC is readable by name with `SHOW` / `current_setting` and is absent
from `pg_settings`; `SHOW ALL` piped through a `grep` for the `app.` prefix returned `0`
the same day.
`role` has no `pg_settings` row at all, so `SET LOCAL ROLE familyroots_app` leaves no trace
there either even while `current_user` already reports the new role. The catalog therefore
cannot see **either** of the two things this seam writes, and a `pg_settings` test would
pass over a third one just as happily as the existing tests do.

So the settings are captured where they are issued: a `before_cursor_execute` listener on
the engine records every statement the seam sends, and the assertion is on the exact
rendered list. That is strictly wider than an `app.%` catalog filter — it fails on a new
`app.*` GUC (invisible to the catalog), on a built-in one such as `statement_timeout`, and
on a `SET ROLE` change alike, because the classifier keys on the *statement* (`SET…`,
`RESET…`, or any call to `set_config`) rather than on a list of known names.

The catalog is still used, for the half the driver cannot see: `pg_settings` where
`source = 'session'` must stay empty inside a request transaction. A built-in GUC set by
something other than a statement on this connection — a pool `connect` event, a `-c` option
in the DSN — would show up there.

## Both writers, re-read at source on 2026-08-22

The seam has **two** writers, which is the detail ADR-047's own text got wrong:

1. The `after_begin` event on `RlsSession`, at `app/core/rls.py:63` and `:65`. It issues
   `SET LOCAL ROLE <role>` and then `set_config('app.clan_id', …)`, at the start of every
   transaction on a request session.
2. `get_current_clan_id`, at `app/core/security.py:290`. It issues `set_config('app.clan_id', …)`
   once, mid-request, on the transaction that is already open.

A test that pinned only the first would miss half the surface, so `test_mid_request_writer_*`
below drives the real `get_current_clan_id` and pins the full three-statement sequence.

`tests/unit/test_rls_seam_writer_inventory.py` is the third guard: it pins the writers that
exist in `app/` at all, so a **third** writer on a path no test drives still fails.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import AsyncGenerator, Generator, Iterator
from contextlib import contextmanager
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.core.database import RlsSession
from app.core.rls import set_request_clan_id
from app.core.security import get_current_clan_id

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

# A statement that CHANGES session/transaction state: any `SET …` / `RESET …`, or any call
# to `set_config(...)` in any form. Deliberately not a list of GUC names — a name list is
# exactly the assertion that would pass over a setting nobody thought of.
_SETTING_WRITE_RE = re.compile(r"(?is)^\s*(?:set|reset)\s|set_config\s*\(")

# Two compiler artifacts that carry no information about WHICH setting is written, and
# would otherwise make the assertion depend on SQLAlchemy's rendering rather than on the
# seam: the label on a scalar function call (`SELECT set_config(...) AS set_config_1`) and
# the inline casts it stamps on bound parameters (`%(set_config_1)s::VARCHAR`).
_TRAILING_LABEL_RE = re.compile(r"(?i)\s+AS\s+\w+\s*$")
_BIND_CAST_RE = re.compile(r"::[A-Za-z_][A-Za-z0-9_]*")


def _literal(value: object) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "null"
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    return str(value)


def _render(statement: str, parameters: Any) -> str:
    """Inline the bound parameters so the GUC NAME is visible in the asserted string.

    It has to be inlined: `get_current_clan_id` goes through the ORM, which binds the GUC
    name itself (`SELECT set_config(%(set_config_2)s, …)`), so asserting on raw SQL text
    would assert nothing about *which* setting is written.
    """
    params = parameters
    if isinstance(params, list | tuple) and params and isinstance(params[0], dict | list | tuple):
        params = params[0]  # executemany: one shape is enough
    if isinstance(params, dict):
        rendered = statement
        for key, value in params.items():
            rendered = rendered.replace(f"%({key})s", _literal(value))
    else:
        values = iter(list(params or ()))
        rendered = re.sub(r"%s", lambda _m: _literal(next(values)), statement)
    rendered = _BIND_CAST_RE.sub("", " ".join(rendered.split()))
    return _TRAILING_LABEL_RE.sub("", rendered)


@contextmanager
def _capture_setting_writes(engine: AsyncEngine) -> Iterator[list[str]]:
    """Record every state-changing statement issued on *engine*, in order."""
    writes: list[str] = []

    def _before_cursor_execute(
        _conn: Any,
        _cursor: Any,
        statement: str,
        parameters: Any,
        _context: Any,
        _executemany: bool,
    ) -> None:
        if _SETTING_WRITE_RE.search(statement):
            writes.append(_render(statement, parameters))

    event.listen(engine.sync_engine, "before_cursor_execute", _before_cursor_execute)
    try:
        yield writes
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _before_cursor_execute)


def _set_role(role: str) -> str:
    return f"SET LOCAL ROLE {role}"


def _set_clan(value: str) -> str:
    return f"SELECT set_config('app.clan_id', '{value}', true)"


@pytest.fixture()
async def engine(migrated_db_url: str) -> AsyncGenerator[AsyncEngine]:
    eng = create_async_engine(migrated_db_url)
    yield eng
    await eng.dispose()


@pytest.fixture(autouse=True)
def _reset_clan_context() -> Generator[None]:
    set_request_clan_id(None)
    yield
    set_request_clan_id(None)


def _rls_sessions(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        engine, sync_session_class=RlsSession, expire_on_commit=False, class_=AsyncSession
    )


async def _seed_user_in_clan(engine: AsyncEngine) -> tuple[uuid.UUID, uuid.UUID]:
    """One approved membership, written privileged. Enough for `get_current_clan_id`."""
    user_id, clan_id = uuid.uuid4(), uuid.uuid4()
    async with engine.begin() as conn:
        await conn.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :s)"),
            {"id": clan_id, "s": f"c-{clan_id.hex[:10]}"},
        )
        await conn.execute(
            sa.text("INSERT INTO user_profiles (id, email, display_name) VALUES (:id, :e, 'u')"),
            {"id": user_id, "e": f"{user_id.hex[:12]}@example.com"},
        )
        await conn.execute(
            sa.text(
                "INSERT INTO user_clan_roles "
                "(user_id, clan_id, role, is_approved, approved_by, approved_at) "
                "VALUES (:u, :c, 'editor', true, :u, now())"
            ),
            {"u": user_id, "c": clan_id},
        )
    return user_id, clan_id


async def test_after_begin_writer_sets_exactly_the_role_and_the_clan_guc(
    engine: AsyncEngine,
) -> None:
    """`app/core/rls.py:63,65` — the whole of what a request transaction begins with.

    The list is asserted whole, not searched. A third statement here — an `app.user_id`
    that someone decided to build after all, a `SET LOCAL statement_timeout`, a stray
    probe — makes this fail, which is the entire point of the file.
    """
    clan_id = uuid.uuid4()
    set_request_clan_id(clan_id)

    with _capture_setting_writes(engine) as writes:
        async with _rls_sessions(engine)() as session:
            await session.execute(sa.text("SELECT 1"))  # forces after_begin

    assert writes == [
        _set_role(settings.RLS_APP_ROLE),
        _set_clan(str(clan_id)),
    ], f"the RLS seam's statement set drifted: {writes}"


async def test_no_clan_selected_still_sets_exactly_the_same_two(engine: AsyncEngine) -> None:
    """Fail-closed path (ADR-008 § 3): the GUC is written EMPTY, never skipped.

    Skipping it would leave whatever the pooled connection last held, which is the one
    way a default-deny seam turns into a cross-clan read. So `''` here is load-bearing,
    and the set is still exactly two.
    """
    set_request_clan_id(None)

    with _capture_setting_writes(engine) as writes:
        async with _rls_sessions(engine)() as session:
            await session.execute(sa.text("SELECT 1"))

    assert writes == [_set_role(settings.RLS_APP_ROLE), _set_clan("")], writes


async def test_mid_request_writer_adds_no_setting_beyond_the_clan_guc(
    engine: AsyncEngine,
) -> None:
    """`app/core/security.py:290` — the SECOND writer, which ADR-047's text missed.

    The transaction begins during auth, before the clan is known, so `after_begin` writes
    an empty GUC and `get_current_clan_id` re-applies the resolved one to the *same*
    transaction. Three statements, one GUC name, one role. Driven through the real
    dependency so a fourth statement added inside it fails here.
    """
    user_id, clan_id = await _seed_user_in_clan(engine)

    with _capture_setting_writes(engine) as writes:
        async with _rls_sessions(engine)() as session:
            resolved = await get_current_clan_id(
                current_user={"sub": str(user_id)},
                db=session,
                x_current_clan_id=str(clan_id),
            )

    assert resolved == clan_id
    assert writes == [
        _set_role(settings.RLS_APP_ROLE),
        _set_clan(""),  # after_begin, before the clan was known
        _set_clan(str(clan_id)),  # security.py:290, same transaction
    ], f"the mid-request writer's statement set drifted: {writes}"

    names = {m.group(1) for w in writes if (m := re.search(r"set_config\('([^']*)'", w))}
    assert names == {"app.clan_id"}, f"a second GUC name reached the seam: {names}"


async def test_seam_leaves_no_builtin_guc_changed_in_the_catalog(engine: AsyncEngine) -> None:
    """The half the driver capture cannot see.

    `pg_settings` cannot show `app.clan_id` or `role` on Postgres 18 (see the module
    docstring), but it does show every built-in GUC changed in this session. Empty here
    means the seam changed none of them — including by a route that issues no statement on
    this connection, such as a pool `connect` event or a `-c` option in the DSN.
    """
    set_request_clan_id(uuid.uuid4())
    async with _rls_sessions(engine)() as session:
        changed = list(
            (
                await session.execute(
                    sa.text(
                        "SELECT name || '=' || setting FROM pg_settings WHERE source = 'session'"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert changed == [], f"the seam changed a built-in setting: {changed}"
        # And the two settings it DOES write have landed, which is what ADR-047 names.
        assert await session.scalar(sa.text("SELECT current_user")) == settings.RLS_APP_ROLE
        assert await session.scalar(sa.text("SELECT current_setting('app.clan_id', true)"))
