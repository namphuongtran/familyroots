"""Events: soft-delete + optimistic concurrency (ADR-022).

Events were the one aggregate left with destructive delete and no version
column — a misclick permanently destroyed a giỗ record (exactly the data
loss ADR-019 fixed for documents), and concurrent PATCHes silently
last-write-wins'd. Events now match persons/marriages: soft-delete with
restore, and PATCH requires expected_version (422 missing, 409 stale_write
with current_version, version echoed +1; delete/restore bump).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import date, timedelta
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
    editor_id = uuid.uuid4()
    async with session_factory() as s:
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :slug)"),
            {"id": clan_id, "slug": f"e-{clan_id.hex[:8]}"},
        )
        await s.execute(
            sa.text("INSERT INTO user_profiles (id, email, display_name) VALUES (:id, :e, 'ed')"),
            {"id": editor_id, "e": f"{editor_id.hex[:8]}@example.com"},
        )
        await s.execute(
            sa.text(
                "INSERT INTO user_clan_roles "
                "(user_id, clan_id, role, is_approved, approved_by, approved_at) "
                "VALUES (:uid, :cid, 'editor', true, :uid, now())"
            ),
            {"uid": editor_id, "cid": clan_id},
        )
        await s.commit()
    return {"clan_id": clan_id, "editor_id": editor_id}


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
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        yield ac


@pytest.fixture()
def headers(seeded: dict[str, Any]) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {seeded['editor_id']}",
        "X-Current-Clan-Id": str(seeded["clan_id"]),
    }


async def _create_event(client: AsyncClient, headers: dict[str, str]) -> dict[str, Any]:
    resp = await client.post(
        "/api/v1/events",
        headers=headers,
        json={
            "event_type": "death_anniversary",
            "title": "Giỗ cụ tổ",
            "event_date": (date.today() + timedelta(days=30)).isoformat(),
            "is_recurring": True,
        },
    )
    assert resp.status_code == 201, resp.text
    data: dict[str, Any] = resp.json()["data"]
    return data


async def test_create_returns_version_1(client: AsyncClient, headers: dict[str, str]) -> None:
    created = await _create_event(client, headers)
    assert created["version"] == 1


async def test_delete_is_soft_and_restorable(
    client: AsyncClient,
    headers: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    created = await _create_event(client, headers)
    event_id = created["id"]

    resp = await client.delete(f"/api/v1/events/{event_id}", headers=headers)
    assert resp.status_code == 200, resp.text

    # Gone from read paths …
    assert (await client.get(f"/api/v1/events/{event_id}", headers=headers)).status_code == 404
    listing = await client.get("/api/v1/events", headers=headers)
    assert all(e["id"] != event_id for e in listing.json()["data"])
    upcoming = await client.get("/api/v1/events/upcoming", headers=headers)
    assert all(e["id"] != event_id for e in upcoming.json()["data"])

    # … but the row survives, flagged.
    async with session_factory() as s:
        row = (
            await s.execute(
                sa.text("SELECT is_deleted, deleted_at, deleted_by FROM events WHERE id = :id"),
                {"id": uuid.UUID(event_id)},
            )
        ).one()
    assert row.is_deleted is True
    assert row.deleted_at is not None

    # Restore brings it back.
    resp = await client.post(f"/api/v1/events/{event_id}/restore", headers=headers)
    assert resp.status_code == 200, resp.text
    assert (await client.get(f"/api/v1/events/{event_id}", headers=headers)).status_code == 200


async def test_patch_requires_expected_version(
    client: AsyncClient, headers: dict[str, str]
) -> None:
    created = await _create_event(client, headers)
    resp = await client.patch(
        f"/api/v1/events/{created['id']}", headers=headers, json={"title": "Đổi tên"}
    )
    assert resp.status_code == 422, resp.text


async def test_patch_stale_version_conflicts(
    client: AsyncClient, headers: dict[str, str]
) -> None:
    created = await _create_event(client, headers)
    event_id = created["id"]

    ok = await client.patch(
        f"/api/v1/events/{event_id}",
        headers=headers,
        json={"title": "Lần 1", "expected_version": 1},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["data"]["version"] == 2

    stale = await client.patch(
        f"/api/v1/events/{event_id}",
        headers=headers,
        json={"title": "Lần 2 cũ", "expected_version": 1},
    )
    assert stale.status_code == 409, stale.text
    body = stale.json()["error"]
    assert body["code"] == "stale_write"
    assert body["detail"]["current_version"] == 2
