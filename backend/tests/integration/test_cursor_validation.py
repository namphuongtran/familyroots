"""M9: a malformed ?cursor= must 400 invalid_cursor, not 500 — across both cursor
decode paths.

Two decode paths exist:
- ``GET /persons`` uses ``decode_fields_cursor`` then the repository extracts
  ``decoded["full_name"]`` / ``uuid.UUID(decoded["id"])`` — so BOTH malformed
  base64 AND valid-base64/valid-JSON-but-wrong-shape must 400 (the repo
  extraction is its own guard, not covered by decode_fields_cursor alone).
- ``GET /documents`` uses ``decode_cursor`` (via ``paginate_query``) — the
  lightest-to-seed ``decode_cursor``-backed list endpoint (no super-admin
  auth, unlike platform-admin ``/platform/clans``).

RED today: the malformed/wrong-shape cases 500 (unhandled ``binascii.Error`` /
``ValueError`` / ``KeyError`` caught only by the generic ``Exception`` handler,
see ``app.core.exceptions.unhandled_exception_handler``) instead of 400
``invalid_cursor``. The valid-cursor control must PASS today and after the fix.
"""

import base64
import json
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi import Header
from httpx import ASGITransport, AsyncClient
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


async def _seed_clan_with_viewer(
    session: AsyncSession, clan_id: uuid.UUID, viewer_id: uuid.UUID
) -> None:
    await session.execute(
        sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :slug)"),
        {"id": clan_id, "slug": f"c-{clan_id.hex[:8]}"},
    )
    await session.execute(
        sa.text("INSERT INTO user_profiles (id, email, display_name) VALUES (:id, :e, 'V')"),
        {"id": viewer_id, "e": f"{viewer_id.hex[:8]}@example.com"},
    )
    await session.execute(
        sa.text(
            "INSERT INTO user_clan_roles "
            "(user_id, clan_id, role, is_approved, approved_by, approved_at) "
            "VALUES (:uid, :cid, 'viewer', true, :uid, now())"
        ),
        {"uid": viewer_id, "cid": clan_id},
    )


async def _seed_persons(session: AsyncSession, clan_id: uuid.UUID, count: int) -> None:
    actor = uuid.uuid4()
    for i in range(count):
        pid = uuid.uuid4()
        await session.execute(
            sa.text(
                "INSERT INTO persons (id, full_name, gender, created_by_clan_id, created_by) "
                "VALUES (:id, :n, 'unknown', :cid, :cb)"
            ),
            {"id": pid, "n": f"Person {i:04d}", "cid": clan_id, "cb": actor},
        )
        await session.execute(
            sa.text("INSERT INTO clan_memberships (person_id, clan_id) VALUES (:p, :c)"),
            {"p": pid, "c": clan_id},
        )


@pytest.fixture()
async def seeded(engine: AsyncEngine) -> dict[str, Any]:
    """A clan with an approved viewer and 3 persons (> the limit=2 used below), so
    the valid-cursor control has a real second page to follow."""
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    clan_id, viewer_id = uuid.uuid4(), uuid.uuid4()
    async with maker() as s:
        await _seed_clan_with_viewer(s, clan_id, viewer_id)
        await _seed_persons(s, clan_id, count=3)
        await s.commit()
    return {"clan_id": clan_id, "viewer_id": viewer_id}


def _make_app(engine: AsyncEngine) -> Any:
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    app = create_app()

    async def _override_db() -> AsyncGenerator[AsyncSession]:
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_current_user
    return app


def _headers(seeded: dict[str, Any]) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {seeded['viewer_id']}",
        "X-Current-Clan-Id": str(seeded["clan_id"]),
    }


# ── decode_fields_cursor path: GET /persons ─────────────────────────────────


async def test_persons_malformed_cursor_400(engine: AsyncEngine, seeded: dict[str, Any]) -> None:
    """Malformed base64 in ?cursor= must 400 invalid_cursor.

    RED today: decode_fields_cursor raises binascii.Error, uncaught -> 500
    internal_error.
    """
    app = _make_app(engine)
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://t"
    ) as ac:
        resp = await ac.get(
            "/api/v1/persons",
            params={"cursor": "%%%not-base64%%%"},
            headers=_headers(seeded),
        )

    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "invalid_cursor"


async def test_persons_wrong_shape_cursor_400(engine: AsyncEngine, seeded: dict[str, Any]) -> None:
    """Valid base64 + valid JSON, but missing full_name/id, must still 400.

    Exercises the repo-extraction guard (person_repository reads
    decoded["full_name"] / uuid.UUID(decoded["id"])), not just decode_fields_cursor
    itself (which happily returns {"foo": 1}).
    RED today: KeyError("full_name") in person_repository, uncaught -> 500
    internal_error.
    """
    wrong_shape_cursor = base64.urlsafe_b64encode(json.dumps({"foo": 1}).encode()).decode()
    app = _make_app(engine)
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://t"
    ) as ac:
        resp = await ac.get(
            "/api/v1/persons",
            params={"cursor": wrong_shape_cursor},
            headers=_headers(seeded),
        )

    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "invalid_cursor"


async def test_persons_valid_cursor_paginates(engine: AsyncEngine, seeded: dict[str, Any]) -> None:
    """Control: a real, well-formed cursor must keep working end to end.

    Seeds 3 persons with limit=2 so page 1 has a real has_more/cursor, then
    follows the ACTUAL issued cursor (not a hand-built one) to page 2.
    """
    app = _make_app(engine)
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://t"
    ) as ac:
        page1 = await ac.get("/api/v1/persons", params={"limit": 2}, headers=_headers(seeded))
        assert page1.status_code == 200, page1.text
        body1 = page1.json()
        assert len(body1["data"]) == 2
        assert body1["meta"]["has_more"] is True
        cursor = body1["meta"]["cursor"]
        assert cursor is not None

        page2 = await ac.get(
            "/api/v1/persons",
            params={"limit": 2, "cursor": cursor},
            headers=_headers(seeded),
        )
        assert page2.status_code == 200, page2.text
        body2 = page2.json()
        assert len(body2["data"]) == 1  # the remaining seeded person

        ids_page1 = {p["id"] for p in body1["data"]}
        ids_page2 = {p["id"] for p in body2["data"]}
        assert ids_page1.isdisjoint(ids_page2), "page 2 must not repeat a person from page 1"


# ── decode_cursor path: GET /documents ───────────────────────────────────────


async def test_paginate_query_malformed_cursor_400(
    engine: AsyncEngine, seeded: dict[str, Any]
) -> None:
    """GET /documents exercises decode_cursor (via paginate_query) — the
    lightest-to-seed decode_cursor-backed list endpoint (no seeded rows needed;
    an empty, viewer-approved clan is enough to reach the decode call).

    RED today: decode_cursor raises binascii.Error, uncaught -> 500
    internal_error.
    """
    app = _make_app(engine)
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://t"
    ) as ac:
        resp = await ac.get(
            "/api/v1/documents",
            params={"cursor": "%%%not-base64%%%"},
            headers=_headers(seeded),
        )

    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "invalid_cursor"
