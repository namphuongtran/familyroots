"""GET /persons/search must honor the persons contract.

docs/contracts/README.md: every person birth_date in a response is a
HistoricalDate object {date, precision, display, lunar} — search is not in
the exemption list. docs/contracts/rest-persons-api.md: list/search/batch
items carry `version` (the OCC token a client needs to start an edit).
The hand-rolled search serializer emitted a bare ISO string and no version:
a client rendering circa dates showed "1750-01-01" as exact, and an edit
started from a search hit had no expected_version to send.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi import Header
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.core.security import get_current_user
from app.main import create_app

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _override_current_user(
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    assert authorization is not None
    return {"sub": authorization.removeprefix("Bearer ")}


@pytest.fixture()
async def session_factory(
    migrated_db_url: str,
) -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(migrated_db_url)
    yield async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    await engine.dispose()


@pytest.fixture()
async def seeded(session_factory: async_sessionmaker[AsyncSession]) -> dict[str, Any]:
    clan_id = uuid.uuid4()
    viewer_id = uuid.uuid4()
    person_id = uuid.uuid4()
    async with session_factory() as s:
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :slug)"),
            {"id": clan_id, "slug": f"s-{clan_id.hex[:8]}"},
        )
        await s.execute(
            sa.text("INSERT INTO user_profiles (id, email, display_name) VALUES (:id, :e, 'v')"),
            {"id": viewer_id, "e": f"{viewer_id.hex[:8]}@example.com"},
        )
        await s.execute(
            sa.text(
                "INSERT INTO user_clan_roles "
                "(user_id, clan_id, role, is_approved, approved_by, approved_at) "
                "VALUES (:uid, :cid, 'viewer', true, :uid, now())"
            ),
            {"uid": viewer_id, "cid": clan_id},
        )
        await s.execute(
            sa.text(
                "INSERT INTO persons (id, full_name, gender, created_by_clan_id, created_by, "
                " birth_date, birth_date_precision, birth_date_display) "
                "VALUES (:id, 'Nguyễn Thị Tổ', 'female', :cid, :uid, "
                "        '1750-01-01', 'circa', 'khoảng 1750')"
            ),
            {"id": person_id, "cid": clan_id, "uid": viewer_id},
        )
        await s.execute(
            sa.text("INSERT INTO clan_memberships (person_id, clan_id) VALUES (:p, :c)"),
            {"p": person_id, "c": clan_id},
        )
        await s.commit()
    return {"clan_id": clan_id, "viewer_id": viewer_id, "person_id": person_id}


@pytest.fixture()
async def client(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncClient]:
    app = create_app()

    async def _override_db() -> AsyncGenerator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_current_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


async def test_search_items_carry_historical_date_and_version(
    client: AsyncClient, seeded: dict[str, Any]
) -> None:
    resp = await client.get(
        "/api/v1/persons/search",
        params={"q": "Tổ"},
        headers={
            "Authorization": f"Bearer {seeded['viewer_id']}",
            "X-Current-Clan-Id": str(seeded["clan_id"]),
        },
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["data"]
    item = next(i for i in items if i["id"] == str(seeded["person_id"]))
    assert item["birth_date"] == {
        "date": "1750-01-01",
        "precision": "circa",
        "display": "khoảng 1750",
        "lunar": None,
    }
    assert item["version"] == 1


async def test_search_wire_matches_person_search_result_schema(
    client: AsyncClient, seeded: dict[str, Any]
) -> None:
    """Coherence guard: /persons/search hand-builds its rows — validate a real
    search body against PersonSearchResult so schema/handler drift fails CI."""
    from app.schemas.person import PersonSearchResult

    resp = await client.get(
        "/api/v1/persons/search",
        params={"q": "Tổ"},
        headers={
            "Authorization": f"Bearer {seeded['viewer_id']}",
            "X-Current-Clan-Id": str(seeded["clan_id"]),
        },
    )
    assert resp.status_code == 200, resp.text
    results = resp.json()["data"]
    assert results  # non-empty
    for row in results:
        PersonSearchResult.model_validate(row)  # raises on drift
