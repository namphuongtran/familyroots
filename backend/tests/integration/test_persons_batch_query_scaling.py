"""POST /persons/batch must issue a constant number of queries, not O(N).

The endpoint used to asyncio.gather one handler.get per person plus one
_fetch_included_data per person (up to 4 sub-queries each, timeline alone = 3)
— all on ONE request-scoped AsyncSession, so the gather yielded zero real
concurrency and a 100-id batch with all includes issued ~500-700 sequential
round-trips. Person fetch and every include are now single ANY(:ids) queries.

The pin: the same request shape with 1 person and with 4 persons must execute
the SAME number of SQL statements.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi import Header
from httpx2 import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.database import get_db
from app.core.security import get_current_user
from app.main import create_app

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_INCLUDES = "marriages,parent_child,timeline,documents"


async def _override_current_user(
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    assert authorization is not None
    return {"sub": authorization.removeprefix("Bearer ")}


@pytest.fixture()
async def engine(migrated_db_url: str) -> AsyncGenerator[AsyncEngine]:
    eng = create_async_engine(migrated_db_url)
    yield eng
    await eng.dispose()


@pytest.fixture()
async def seeded(engine: AsyncEngine) -> dict[str, Any]:
    """A clan with 4 member persons, each with a spouse, a child edge, a
    document, and an event — so every include token has per-person data."""
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    clan_id = uuid.uuid4()
    viewer_id = uuid.uuid4()
    member_ids: list[uuid.UUID] = []
    async with maker() as s:
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :slug)"),
            {"id": clan_id, "slug": f"b-{clan_id.hex[:8]}"},
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
        for i in range(4):
            member = uuid.uuid4()
            spouse = uuid.uuid4()
            child = uuid.uuid4()
            member_ids.append(member)
            for pid, name, gender in (
                (member, f"Thành viên {i}", "male"),
                (spouse, f"Vợ {i}", "female"),
                (child, f"Con {i}", "male"),
            ):
                await s.execute(
                    sa.text(
                        "INSERT INTO persons "
                        "(id, full_name, gender, created_by_clan_id, created_by, birth_date) "
                        "VALUES (:id, :n, :g, :cid, :uid, '1950-01-01')"
                    ),
                    {"id": pid, "n": name, "g": gender, "cid": clan_id, "uid": viewer_id},
                )
            await s.execute(
                sa.text("INSERT INTO clan_memberships (person_id, clan_id) VALUES (:p, :c)"),
                {"p": member, "c": clan_id},
            )
            await s.execute(
                sa.text(
                    "INSERT INTO marriages (id, person1_id, person2_id, status, spouse_order, "
                    " marriage_date, created_by_clan_id, created_by) "
                    "VALUES (:id, :p1, :p2, 'married', 1, '1970-01-01', :cid, :uid)"
                ),
                {"id": uuid.uuid4(), "p1": member, "p2": spouse, "cid": clan_id, "uid": viewer_id},
            )
            await s.execute(
                sa.text(
                    "INSERT INTO parent_child (id, parent_id, child_id, relationship_type, "
                    " created_by_clan_id, created_by) "
                    "VALUES (:id, :p, :c, 'biological', :cid, :uid)"
                ),
                {"id": uuid.uuid4(), "p": member, "c": child, "cid": clan_id, "uid": viewer_id},
            )
            await s.execute(
                sa.text(
                    "INSERT INTO documents (id, clan_id, person_id, title, document_type, "
                    " storage_path, created_by) "
                    "VALUES (:id, :cid, :p, 'Ảnh', 'photo', :path, :uid)"
                ),
                {
                    "id": uuid.uuid4(),
                    "cid": clan_id,
                    "p": member,
                    "path": f"clans/{clan_id}/d/{uuid.uuid4()}.png",
                    "uid": viewer_id,
                },
            )
            await s.execute(
                sa.text(
                    "INSERT INTO events (id, clan_id, person_id, event_type, title, event_date, "
                    " created_by) "
                    "VALUES (:id, :cid, :p, 'death_anniversary', 'Giỗ', '2000-01-01', :uid)"
                ),
                {"id": uuid.uuid4(), "cid": clan_id, "p": member, "uid": viewer_id},
            )
        await s.commit()
    return {"clan_id": clan_id, "viewer_id": viewer_id, "member_ids": member_ids}


async def _batch_request_statement_count(
    engine: AsyncEngine, seeded: dict[str, Any], ids: list[uuid.UUID]
) -> tuple[int, dict[str, Any]]:
    """Run one batch request and return (SQL statement count, response json)."""
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    app = create_app()

    async def _override_db() -> AsyncGenerator[AsyncSession]:
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_current_user

    statements: list[str] = []

    def _count(conn: Any, cursor: Any, statement: str, *args: Any) -> None:
        statements.append(statement)

    sa.event.listen(engine.sync_engine, "before_cursor_execute", _count)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
            resp = await ac.post(
                "/api/v1/persons/batch",
                json={"ids": [str(i) for i in ids], "include": _INCLUDES},
                headers={
                    "Authorization": f"Bearer {seeded['viewer_id']}",
                    "X-Current-Clan-Id": str(seeded["clan_id"]),
                },
            )
    finally:
        sa.event.remove(engine.sync_engine, "before_cursor_execute", _count)
    assert resp.status_code == 200, resp.text
    return len(statements), resp.json()


async def test_batch_query_count_does_not_scale_with_ids(
    engine: AsyncEngine, seeded: dict[str, Any]
) -> None:
    count_1, body_1 = await _batch_request_statement_count(engine, seeded, seeded["member_ids"][:1])
    count_4, body_4 = await _batch_request_statement_count(engine, seeded, seeded["member_ids"])

    # Correctness first: every person came back with every include populated.
    assert len(body_4["data"]) == 4
    for item in body_4["data"]:
        assert len(item["marriages"]) == 1
        assert len(item["parent_child"]) == 1
        assert len(item["documents"]) == 1
        # timeline: birth + marriage + event
        assert {e["event_type"] for e in item["timeline"]} >= {"birth", "marriage"}
    assert body_1["data"][0]["marriages"] == body_4["data"][0]["marriages"]

    # The pin: same statement count for 1 and 4 persons (constant, not O(N)).
    assert count_4 == count_1, f"batch queries scale with ids: {count_1} -> {count_4}"


async def test_batch_wire_matches_batch_envelope_schema(
    engine: AsyncEngine, seeded: dict[str, Any]
) -> None:
    """Coherence guard: validate a real /persons/batch body (including a populated
    meta.errors) against PersonBatchEnvelope."""
    from app.schemas.person import PersonBatchEnvelope

    real_id = seeded["member_ids"][0]
    missing_id = uuid.uuid4()
    # Default profile ("full") and no `fields=` — data items must be full
    # PersonResponse-complete for PersonBatchEnvelope.model_validate to hold.
    _count, body = await _batch_request_statement_count(engine, seeded, [real_id, missing_id])

    assert body["meta"]["errors"]  # the missing id populated errors — non-vacuous
    PersonBatchEnvelope.model_validate(body)  # raises on drift
