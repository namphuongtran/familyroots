"""L11 end-to-end (real DB): the query handler + real linked-person lookup redact PII.

Proves the whole gate: an ordinary member viewing someone else gets phone/email nulled;
viewing their OWN linked person (resolved via user_profiles.person_id) keeps them.

**AMENDED 2026-08-22 by seed S-058: "end-to-end" above means the handler and the real
database, not the API.** Every case below calls ``handler.redact_pii(...)`` itself and no
case issues an HTTP request, so this file proves the function and proves nothing about
whether any route calls it. ADR-049 § "Measurement 5" deleted a route's redaction call
and watched the whole suite stay at ``1351 passed``. Two other files cited this one as
covering that wiring, and both citations were wrong.

The four routes that redact are proved separately, by request and response body, in
``tests/integration/test_person_pii_over_http.py``. Keep the two files apart: this one
owns the rule, that one owns the wiring.
"""

import uuid
from collections.abc import AsyncGenerator

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.application.person.commands import GetPerson
from app.application.person.handlers import PersonQueryHandler
from app.infrastructure.event_dispatcher import create_event_dispatcher
from app.infrastructure.persistence.person_repository import SqlAlchemyPersonRepository
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture()
async def async_session(migrated_db_url: str) -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine(migrated_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as session:
        yield session
    await engine.dispose()


async def _seed_person(s: AsyncSession, clan_id: uuid.UUID, *, phone: str) -> uuid.UUID:
    pid = uuid.uuid4()
    await s.execute(
        sa.text(
            "INSERT INTO persons (id, full_name, gender, created_by_clan_id, created_by, "
            "phone, email) VALUES (:id, 'P', 'male', :c, :cb, :ph, :em)"
        ),
        {"id": pid, "c": clan_id, "cb": uuid.uuid4(), "ph": phone, "em": f"{pid.hex[:6]}@ex.com"},
    )
    await s.execute(
        sa.text("INSERT INTO clan_memberships (id, person_id, clan_id) VALUES (:i, :p, :c)"),
        {"i": uuid.uuid4(), "p": pid, "c": clan_id},
    )
    return pid


async def test_member_sees_own_pii_but_not_others(async_session: AsyncSession) -> None:
    clan_id, viewer_id = uuid.uuid4(), uuid.uuid4()
    await async_session.execute(
        sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :s)"),
        {"id": clan_id, "s": f"c{clan_id.hex[:8]}"},
    )
    target = await _seed_person(async_session, clan_id, phone="0900000000")
    viewer_person = await _seed_person(async_session, clan_id, phone="0911111111")
    # viewer's account is linked to viewer_person (NOT to target)
    await async_session.execute(
        sa.text(
            "INSERT INTO user_profiles (id, email, display_name, person_id) "
            "VALUES (:id, :e, 'V', :pp)"
        ),
        {"id": viewer_id, "e": f"v-{viewer_id.hex[:6]}@ex.com", "pp": viewer_person},
    )
    await async_session.commit()

    repo = SqlAlchemyPersonRepository(
        SqlAlchemyUnitOfWork(async_session, create_event_dispatcher(async_session))
    )
    handler = PersonQueryHandler(repo)

    # viewing SOMEONE ELSE (target) as a viewer → phone/email redacted
    other = await handler.get(GetPerson(person_id=target, clan_id=clan_id))
    assert other.phone == "0900000000"  # present before redaction
    await handler.redact_pii([other], viewer_role="viewer", viewer_user_id=viewer_id)
    assert other.phone is None and other.email is None

    # viewing their OWN linked person → phone/email kept
    mine = await handler.get(GetPerson(person_id=viewer_person, clan_id=clan_id))
    await handler.redact_pii([mine], viewer_role="viewer", viewer_user_id=viewer_id)
    assert mine.phone == "0911111111"

    # an admin sees the target's contact details
    target_for_admin = await handler.get(GetPerson(person_id=target, clan_id=clan_id))
    await handler.redact_pii([target_for_admin], viewer_role="admin", viewer_user_id=viewer_id)
    assert target_for_admin.phone == "0900000000"
