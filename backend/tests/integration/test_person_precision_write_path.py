"""End-to-end (real DB) proof that the precision/display WRITE path is wired.

HistoricalDate contract, Task 5: create_person/update_person previously excluded
birth_date_precision/display (and death_*) from the payload passed to the command
handlers via a temporary shim, so a client-supplied precision/display was silently
DROPPED — never reaching the aggregate, the ORM row, or the database. Task 5 removed
those excludes and wired precision/display onto the Person aggregate's
`_UPDATABLE_FIELDS` + the mapper + `CreatePerson`/`UpdatePerson`.

These tests drive `PersonCommandHandler`/`PersonQueryHandler` (the exact code the
API routes call once the request body is unpacked) against the real migrated schema,
across a FRESH session per step, so a value that merely survives in an in-memory
domain object (without truly reaching the `persons` table) cannot fake a pass.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.application.person.commands import CreatePerson, GetPerson, UpdatePerson
from app.application.person.handlers import PersonCommandHandler, PersonQueryHandler
from app.domain.shared.value_objects import ActorInfo
from app.infrastructure.event_dispatcher import create_event_dispatcher
from app.infrastructure.persistence.person_repository import SqlAlchemyPersonRepository
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture()
def session_factory(migrated_db_url: str) -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(migrated_db_url)
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


def _command_handler(session: AsyncSession) -> PersonCommandHandler:
    uow = SqlAlchemyUnitOfWork(session, create_event_dispatcher(session))
    return PersonCommandHandler(SqlAlchemyPersonRepository(uow), uow)


def _query_handler(session: AsyncSession) -> PersonQueryHandler:
    uow = SqlAlchemyUnitOfWork(session, create_event_dispatcher(session))
    return PersonQueryHandler(SqlAlchemyPersonRepository(uow))


async def _seed_clan(session: AsyncSession) -> uuid.UUID:
    clan_id = uuid.uuid4()
    await session.execute(
        sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :s)"),
        {"id": clan_id, "s": f"c-{clan_id.hex[:8]}"},
    )
    return clan_id


async def test_create_person_persists_precision_and_display(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """CreatePerson's precision/display reach the DB — a FRESH session read confirms
    it, so a value only held on the in-memory domain object can't fake a pass."""
    actor = ActorInfo(user_id=uuid.uuid4(), role="editor")

    async with session_factory() as write_session:
        clan_id = await _seed_clan(write_session)
        handler = _command_handler(write_session)
        created = await handler.create(
            CreatePerson(
                actor=actor,
                clan_id=clan_id,
                full_name="Nguyễn Văn Cổ",
                birth_date=date(1900, 1, 1),
                birth_date_precision="circa",
                birth_date_display="khoảng 1900",
            )
        )
        await write_session.commit()

    # Same-process assertion on the command's own response.
    assert created.birth_date.precision == "circa"
    assert created.birth_date.display == "khoảng 1900"

    # FRESH session/handler — proves the value is in the `persons` table, not just
    # held on the in-memory Person the create() call returned.
    async with session_factory() as read_session:
        query_handler = _query_handler(read_session)
        fetched = await query_handler.get(GetPerson(person_id=created.id, clan_id=clan_id))

    assert fetched.birth_date.date == date(1900, 1, 1)
    assert fetched.birth_date.precision == "circa"
    assert fetched.birth_date.display == "khoảng 1900"


async def test_update_person_persists_precision_and_display(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """UpdatePerson's precision/display changes reach the DB (the update_person
    route shim that used to drop these fields is gone)."""
    actor = ActorInfo(user_id=uuid.uuid4(), role="editor")

    async with session_factory() as write_session:
        clan_id = await _seed_clan(write_session)
        handler = _command_handler(write_session)
        created = await handler.create(
            CreatePerson(actor=actor, clan_id=clan_id, full_name="Trần Thị B")
        )
        await write_session.commit()

    assert created.death_date.precision == "exact"  # baseline default, pre-update

    async with session_factory() as update_session:
        handler = _command_handler(update_session)
        await handler.update(
            UpdatePerson(
                person_id=created.id,
                clan_id=clan_id,
                actor=actor,
                expected_version=1,
                changes={
                    "death_date_precision": "unknown",
                    "death_date_display": "chưa rõ",
                },
            )
        )
        await update_session.commit()

    async with session_factory() as read_session:
        query_handler = _query_handler(read_session)
        fetched = await query_handler.get(GetPerson(person_id=created.id, clan_id=clan_id))

    assert fetched.death_date.precision == "unknown"
    assert fetched.death_date.display == "chưa rõ"
