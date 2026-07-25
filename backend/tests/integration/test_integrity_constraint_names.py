"""Pin that psycopg exposes the exact constraint/index NAME the integrity handler maps
on (A7 + M11 follow-ups). If Postgres/psycopg ever stopped populating
``diag.constraint_name`` for a unique INDEX or a CHECK — or a migration renamed one —
``integrity_error_handler``'s mapping would silently fall through to a 500/generic-409,
so these real-DB probes fail loudly instead.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture()
async def session(migrated_db_url: str) -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine(migrated_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as s:
        yield s
    await engine.dispose()


def _constraint_name(exc: IntegrityError) -> str | None:
    return getattr(getattr(getattr(exc, "orig", None), "diag", None), "constraint_name", None)


async def test_partial_unique_index_reports_its_name(session: AsyncSession) -> None:
    """A live-pending re-insert violates the partial unique INDEX; psycopg reports the
    index name in diag.constraint_name (the key the handler maps to
    invitation.pending_exists)."""
    clan_id, inviter = uuid.uuid4(), uuid.uuid4()
    email = "dup@example.com"
    await session.execute(
        sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :s)"),
        {"id": clan_id, "s": f"c{clan_id.hex[:8]}"},
    )
    ins = (
        "INSERT INTO clan_invitations (id, clan_id, email, role, invited_by, token, "
        "expires_at, status) VALUES (:id, :c, :e, 'editor', :ib, :t, :exp, 'pending')"
    )
    future = datetime(2999, 1, 1, tzinfo=UTC)
    await session.execute(
        sa.text(ins),
        {"id": uuid.uuid4(), "c": clan_id, "e": email, "ib": inviter, "t": "t1", "exp": future},
    )
    with pytest.raises(IntegrityError) as ei:
        await session.execute(
            sa.text(ins),
            {"id": uuid.uuid4(), "c": clan_id, "e": email, "ib": inviter, "t": "t2", "exp": future},
        )
        await session.flush()
    assert getattr(ei.value.orig, "sqlstate", None) == "23505"
    assert _constraint_name(ei.value) == "uq_clan_invitations_pending"


async def test_marriage_divorce_check_reports_its_name(session: AsyncSession) -> None:
    """A divorce_date < marriage_date row violates the named CHECK; psycopg reports
    marriages_divorce_after_marriage (the key mapped to relationship.divorce_before_marriage)."""
    clan_id, actor = uuid.uuid4(), uuid.uuid4()
    p1, p2 = uuid.uuid4(), uuid.uuid4()
    await session.execute(
        sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :s)"),
        {"id": clan_id, "s": f"c{clan_id.hex[:8]}"},
    )
    for pid in (p1, p2):
        await session.execute(
            sa.text(
                "INSERT INTO persons (id, full_name, created_by_clan_id, created_by) "
                "VALUES (:id, 'P', :c, :cb)"
            ),
            {"id": pid, "c": clan_id, "cb": actor},
        )
    with pytest.raises(IntegrityError) as ei:
        await session.execute(
            sa.text(
                "INSERT INTO marriages (id, person1_id, person2_id, created_by_clan_id, "
                "status, marriage_date, divorce_date, created_by) "
                "VALUES (:id, :p1, :p2, :c, 'divorced', '2000-01-01', '1990-01-01', :cb)"
            ),
            {"id": uuid.uuid4(), "p1": p1, "p2": p2, "c": clan_id, "cb": actor},
        )
        await session.flush()
    assert getattr(ei.value.orig, "sqlstate", None) == "23514"
    assert _constraint_name(ei.value) == "ck_marriages_marriages_divorce_after_marriage"
