"""Soft-deleted documents must not leak through the person read paths.

ADR-019 made document deletion soft; every document read path must filter
`is_deleted`. The document router paths were covered in
test_document_soft_delete.py — these tests pin the *person*-side projections
(`GET /persons/{id}/documents` and `GET /persons/{id}?include=documents`),
which go through SqlAlchemyPersonQueryPort.get_documents.

Real Postgres (migrated_db_url); JWT verification stubbed as in
tests/integration/test_document_soft_delete.py. Two-sided: the live document
must appear (negative control), the soft-deleted one must not.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi import Header
from httpx2 import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.core.security import get_current_user
from app.main import create_app

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _override_current_user(
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    assert authorization is not None, "test client must send an Authorization header"
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
    """A clan, an approved viewer, a member person, one live and one
    soft-deleted document attached to that person."""
    clan_id = uuid.uuid4()
    viewer_id = uuid.uuid4()
    person_id = uuid.uuid4()
    live_doc_id = uuid.uuid4()
    deleted_doc_id = uuid.uuid4()
    async with session_factory() as s:
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'Doc Leak Clan', :slug)"),
            {"id": clan_id, "slug": f"leak-{clan_id.hex[:8]}"},
        )
        await s.execute(
            sa.text(
                "INSERT INTO user_profiles (id, email, display_name) VALUES (:id, :email, 'v')"
            ),
            {"id": viewer_id, "email": f"{viewer_id.hex[:8]}@example.com"},
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
                "INSERT INTO persons (id, full_name, gender, created_by_clan_id, created_by) "
                "VALUES (:id, 'Nguyễn Văn A', 'male', :cid, :uid)"
            ),
            {"id": person_id, "cid": clan_id, "uid": viewer_id},
        )
        await s.execute(
            sa.text(
                "INSERT INTO clan_memberships (person_id, clan_id, joined_at) "
                "VALUES (:pid, :cid, now())"
            ),
            {"pid": person_id, "cid": clan_id},
        )
        for doc_id, title, deleted in (
            (live_doc_id, "Ảnh thờ", False),
            (deleted_doc_id, "Giấy tờ đã xoá", True),
        ):
            await s.execute(
                sa.text(
                    "INSERT INTO documents "
                    "(id, clan_id, person_id, title, document_type, storage_path, "
                    " created_by, is_deleted, deleted_at, deleted_by) "
                    "VALUES (:id, :cid, :pid, :title, 'photo', :path, :uid, "
                    "        :deleted, CASE WHEN :deleted THEN now() END, "
                    "        CASE WHEN :deleted THEN :uid END)"
                ),
                {
                    "id": doc_id,
                    "cid": clan_id,
                    "pid": person_id,
                    "title": title,
                    "path": f"clans/{clan_id}/documents/{doc_id}.png",
                    "uid": viewer_id,
                    "deleted": deleted,
                },
            )
        await s.commit()
    return {
        "clan_id": clan_id,
        "viewer_id": viewer_id,
        "person_id": person_id,
        "live_doc_id": live_doc_id,
        "deleted_doc_id": deleted_doc_id,
    }


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

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest.fixture()
def viewer_headers(seeded: dict[str, Any]) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {seeded['viewer_id']}",
        "X-Current-Clan-Id": str(seeded["clan_id"]),
    }


async def test_person_documents_excludes_soft_deleted(
    client: AsyncClient, seeded: dict[str, Any], viewer_headers: dict[str, str]
) -> None:
    resp = await client.get(
        f"/api/v1/persons/{seeded['person_id']}/documents", headers=viewer_headers
    )
    assert resp.status_code == 200, resp.text
    ids = {d["id"] for d in resp.json()["data"]}
    assert str(seeded["live_doc_id"]) in ids  # negative control: live doc visible
    assert str(seeded["deleted_doc_id"]) not in ids


async def test_person_include_documents_excludes_soft_deleted(
    client: AsyncClient, seeded: dict[str, Any], viewer_headers: dict[str, str]
) -> None:
    resp = await client.get(
        f"/api/v1/persons/{seeded['person_id']}?include=documents", headers=viewer_headers
    )
    assert resp.status_code == 200, resp.text
    docs = resp.json()["data"]["documents"]
    ids = {d["id"] for d in docs}
    assert str(seeded["live_doc_id"]) in ids  # negative control: live doc visible
    assert str(seeded["deleted_doc_id"]) not in ids
