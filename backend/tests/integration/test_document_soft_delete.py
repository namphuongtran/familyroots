"""ADR-019: document delete is recoverable — blob survives, restore works.

Real Postgres (migrated_db_url), real RBAC, real Document aggregate +
repository. Only JWT *verification* is stubbed (mirrors
tests/integration/test_occ_persons.py) — the Authorization header carries the
user id directly instead of a signed token. The storage adapter is swapped for
an in-memory spy (via dependency_overrides) so these tests never hit real
Supabase Storage and can assert exactly when `delete` is (not) called.
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
from app.infrastructure.dependencies import get_document_command_handler, get_document_query_handler
from app.main import create_app
from app.services.translator import load_translations, t

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

# A minimal (invalid but non-empty) PNG-ish payload — content bytes are never
# validated beyond size, only content_type against ALLOWED_MIME_TYPES.
_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


async def _override_current_user(
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    assert authorization is not None, "test client must send an Authorization header"
    return {"sub": authorization.removeprefix("Bearer ")}


class FakeStorage:
    """In-memory StoragePort double — records calls so tests can assert the blob
    was never touched by a soft-delete."""

    def __init__(self) -> None:
        self.uploaded: list[str] = []
        self.deleted: list[str] = []

    async def upload(self, path: str, content: bytes, content_type: str | None) -> str:
        self.uploaded.append(path)
        return path

    async def delete(self, storage_path: str) -> bool:
        self.deleted.append(storage_path)
        return True

    async def get_presigned_url(self, storage_path: str, expires_in: int = 3600) -> str:
        return f"https://signed.example/{storage_path}"


@pytest.fixture()
async def session_factory(
    migrated_db_url: str,
) -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(migrated_db_url)
    yield async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    await engine.dispose()


@pytest.fixture()
async def seeded(session_factory: async_sessionmaker[AsyncSession]) -> dict[str, Any]:
    """A clan plus an approved editor and an approved admin membership."""
    clan_id = uuid.uuid4()
    editor_id = uuid.uuid4()
    admin_id = uuid.uuid4()
    async with session_factory() as s:
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'Doc Clan', :slug)"),
            {"id": clan_id, "slug": f"doc-{clan_id.hex[:8]}"},
        )
        for uid, role in ((editor_id, "editor"), (admin_id, "admin")):
            await s.execute(
                sa.text(
                    "INSERT INTO user_profiles (id, email, display_name) "
                    "VALUES (:id, :email, :name)"
                ),
                {"id": uid, "email": f"{uid.hex[:8]}@example.com", "name": role},
            )
            await s.execute(
                sa.text(
                    "INSERT INTO user_clan_roles "
                    "(user_id, clan_id, role, is_approved, approved_by, approved_at) "
                    "VALUES (:uid, :cid, :role, true, :uid, now())"
                ),
                {"uid": uid, "cid": clan_id, "role": role},
            )
        await s.commit()
    return {"clan_id": clan_id, "editor_id": editor_id, "admin_id": admin_id}


@pytest.fixture()
def fake_storage() -> FakeStorage:
    return FakeStorage()


@pytest.fixture()
async def client(
    session_factory: async_sessionmaker[AsyncSession],
    fake_storage: FakeStorage,
) -> AsyncGenerator[AsyncClient]:
    from app.infrastructure.event_dispatcher import create_event_dispatcher
    from app.infrastructure.persistence.document_repository import SqlAlchemyDocumentRepository
    from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork

    app = create_app()
    # This suite runs without lifespan; localized response messages need the
    # translation catalogs loaded explicitly.
    load_translations()

    async def _override_db() -> AsyncGenerator[AsyncSession]:
        async with session_factory() as session:
            yield session

    # Handler-factory overrides that open their own session (independent of the
    # get_db override above — a document command/query handler needs exactly one
    # session per request) and swap in the fake storage adapter instead of
    # SupabaseStorageAdapter, so these tests never hit real Supabase Storage.
    async def _make_cmd_handler() -> AsyncGenerator[Any]:
        from app.application.document.handlers import DocumentCommandHandler

        async with session_factory() as db:
            uow = SqlAlchemyUnitOfWork(db, create_event_dispatcher(db))
            yield DocumentCommandHandler(SqlAlchemyDocumentRepository(uow), fake_storage, uow)

    async def _make_query_handler() -> AsyncGenerator[Any]:
        from app.application.document.handlers import DocumentQueryHandler

        async with session_factory() as db:
            uow = SqlAlchemyUnitOfWork(db, create_event_dispatcher(db))
            yield DocumentQueryHandler(SqlAlchemyDocumentRepository(uow), fake_storage)

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_current_user
    app.dependency_overrides[get_document_command_handler] = _make_cmd_handler
    app.dependency_overrides[get_document_query_handler] = _make_query_handler

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest.fixture()
def editor_headers(seeded: dict[str, Any]) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {seeded['editor_id']}",
        "X-Current-Clan-Id": str(seeded["clan_id"]),
    }


@pytest.fixture()
def admin_headers(seeded: dict[str, Any]) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {seeded['admin_id']}",
        "X-Current-Clan-Id": str(seeded["clan_id"]),
    }


@pytest.fixture()
async def uploaded_document(client: AsyncClient, admin_headers: dict[str, str]) -> tuple[str, str]:
    resp = await client.post(
        "/api/v1/documents",
        headers=admin_headers,
        data={"title": "Giấy khai sinh", "document_type": "photo"},
        files={"file": ("test.png", _PNG_BYTES, "image/png")},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    return data["id"], data["storage_path"]


# ── Tests ─────────────────────────────────────────────────────────────────


async def test_delete_soft_deletes_and_keeps_blob(
    client: AsyncClient,
    admin_headers: dict[str, str],
    uploaded_document: tuple[str, str],
    fake_storage: FakeStorage,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    doc_id, storage_path = uploaded_document
    resp = await client.delete(f"/api/v1/documents/{doc_id}", headers=admin_headers)
    assert resp.status_code == 200  # existing message-envelope shape unchanged
    # Localized message (default locale vi) — was hardcoded English before.
    assert resp.json()["data"] == {"message": t("document.deleted", locale="vi"), "id": doc_id}
    assert resp.json()["data"]["message"] != "document.deleted"  # key must resolve

    # gone from the list and from GET
    listing = await client.get("/api/v1/documents", headers=admin_headers)
    assert all(d["id"] != doc_id for d in listing.json()["data"])
    get_resp = await client.get(f"/api/v1/documents/{doc_id}", headers=admin_headers)
    assert get_resp.status_code == 404

    # but the row is flagged, not gone, and the blob was NOT deleted
    async with session_factory() as s:
        row = (
            await s.execute(
                sa.text("SELECT is_deleted, deleted_at, deleted_by FROM documents WHERE id = :id"),
                {"id": uuid.UUID(doc_id)},
            )
        ).one()
    assert row.is_deleted is True
    assert row.deleted_at is not None
    assert row.deleted_by == uuid.UUID(admin_headers["Authorization"].removeprefix("Bearer "))
    assert fake_storage.deleted == []  # blob untouched — survives until the purge job
    assert storage_path in fake_storage.uploaded  # sanity: it really was uploaded


async def test_restore_brings_document_back(
    client: AsyncClient,
    admin_headers: dict[str, str],
    uploaded_document: tuple[str, str],
) -> None:
    doc_id, _ = uploaded_document
    await client.delete(f"/api/v1/documents/{doc_id}", headers=admin_headers)
    resp = await client.post(f"/api/v1/documents/{doc_id}/restore", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["id"] == doc_id
    get_resp = await client.get(f"/api/v1/documents/{doc_id}", headers=admin_headers)
    assert get_resp.status_code == 200  # presigned URL flows again


async def test_restore_requires_admin_and_404s(
    client: AsyncClient,
    editor_headers: dict[str, str],
    admin_headers: dict[str, str],
    uploaded_document: tuple[str, str],
) -> None:
    doc_id, _ = uploaded_document
    await client.delete(f"/api/v1/documents/{doc_id}", headers=admin_headers)
    forbidden = await client.post(f"/api/v1/documents/{doc_id}/restore", headers=editor_headers)
    assert forbidden.status_code == 403
    ok = await client.post(f"/api/v1/documents/{doc_id}/restore", headers=admin_headers)
    assert ok.status_code == 200
    again = await client.post(f"/api/v1/documents/{doc_id}/restore", headers=admin_headers)
    assert again.status_code == 404  # not-deleted → restore has nothing to do
