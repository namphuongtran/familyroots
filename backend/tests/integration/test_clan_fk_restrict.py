"""M10: clan-owned FKs are ON DELETE RESTRICT (real migrated DB).

Deleting a clan that still owns rows (branches, memberships, edges, …) now fails
loudly instead of silently cascading away the clan's genealogy. persons and audit
rows stay SET NULL — retained/de-provenanced, not destroyed. A revert of migration
010 (back to CASCADE) makes the RESTRICT test pass a delete that should have failed.
"""

import uuid
from collections.abc import AsyncGenerator

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture()
async def async_session(migrated_db_url: str) -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine(migrated_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as session:
        yield session
    await engine.dispose()


async def _clan(s: AsyncSession, cid: uuid.UUID) -> None:
    await s.execute(
        sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :sl)"),
        {"id": cid, "sl": f"c-{cid.hex[:8]}"},
    )


async def test_delete_clan_with_children_is_restricted(async_session: AsyncSession) -> None:
    clan_id = uuid.uuid4()
    await _clan(async_session, clan_id)
    # a branch is a clan-owned child; before M10 its FK CASCADE-deleted it silently
    await async_session.execute(
        sa.text("INSERT INTO branches (id, clan_id, name) VALUES (:id, :c, 'Chi')"),
        {"id": uuid.uuid4(), "c": clan_id},
    )
    await async_session.commit()

    with pytest.raises(IntegrityError):  # RESTRICT: the clan still owns a branch
        await async_session.execute(sa.text("DELETE FROM clans WHERE id = :c"), {"c": clan_id})
        await async_session.flush()
    await async_session.rollback()

    # the clan (and its branch) are still there — nothing was wiped
    assert (
        await async_session.scalar(
            sa.text("SELECT count(*) FROM branches WHERE clan_id = :c"), {"c": clan_id}
        )
        == 1
    )


async def test_delete_empty_clan_succeeds_and_orphans_person(async_session: AsyncSession) -> None:
    """A clan whose only reference is a person (SET NULL, not RESTRICT) can be deleted;
    the person survives with a nulled created_by_clan_id."""
    clan_id, person_id = uuid.uuid4(), uuid.uuid4()
    await _clan(async_session, clan_id)
    await async_session.execute(
        sa.text(
            "INSERT INTO persons (id, full_name, gender, created_by_clan_id, created_by) "
            "VALUES (:id, 'P', 'male', :c, :cb)"
        ),
        {"id": person_id, "c": clan_id, "cb": uuid.uuid4()},
    )
    await async_session.commit()

    await async_session.execute(sa.text("DELETE FROM clans WHERE id = :c"), {"c": clan_id})
    await async_session.commit()

    assert (
        await async_session.scalar(
            sa.text("SELECT count(*) FROM clans WHERE id = :c"), {"c": clan_id}
        )
        == 0
    )
    # person retained, provenance nulled (SET NULL, not cascade-deleted)
    survived = await async_session.execute(
        sa.text("SELECT created_by_clan_id FROM persons WHERE id = :p"), {"p": person_id}
    )
    assert survived.scalar_one() is None
