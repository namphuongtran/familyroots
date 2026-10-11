"""Direct-to-Storage upload over HTTP: what a confirm call refuses (ADR-068, #256).

Real Postgres, real RBAC and repository; JWT *verification* is stubbed (the Authorization
header carries the user id), and the private bucket is an in-memory object store, so a
test can read both the HTTP response and what the bucket holds afterwards. ``put`` plays
the browser's PUT to the signed URL.

Each refusal is read twice: in the response's status and code, and in Storage. A path
that names another clan must leave that clan's file where it was. A file that breaks the
type or size rule must be gone, so that it can never be confirmed later.

Negative controls, run 2026-10-11:
- with the clan prefix removed from ``parse_staged_upload_path``, the cross-clan case
  fails with 201 and the other clan's file moved into this clan's documents;
- with the ``check_upload_file`` re-read at confirm removed, the HTML-as-JPEG case
  fails with 201.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi import Header
from httpx2 import ASGITransport, AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.domain.document.repository import SignedUpload, StorageNotFoundError, StoredObject
from app.infrastructure.dependencies import get_document_upload_handler
from app.main import create_app
from app.services.translator import load_translations

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
_MB = 1024 * 1024


async def _override_current_user(
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    assert authorization is not None, "test client must send an Authorization header"
    return {"sub": authorization.removeprefix("Bearer ")}


class ObjectStore:
    """The private bucket, in memory."""

    def __init__(self) -> None:
        self.objects: dict[str, StoredObject] = {}

    def put(self, path: str, size_bytes: int, content_type: str | None) -> None:
        """What the browser's PUT to the signed URL does."""
        self.objects[path] = StoredObject(size_bytes=size_bytes, content_type=content_type)

    async def create_signed_upload(self, path: str) -> SignedUpload:
        return SignedUpload(upload_url=f"https://storage.example/sign/{path}", token="t")

    async def stat(self, path: str) -> StoredObject:
        if path not in self.objects:
            raise StorageNotFoundError(path)
        return self.objects[path]

    async def move(self, from_path: str, to_path: str) -> None:
        if from_path not in self.objects:
            raise StorageNotFoundError(from_path)
        self.objects[to_path] = self.objects.pop(from_path)

    async def delete(self, storage_path: str) -> bool:
        self.objects.pop(storage_path, None)
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
    """Two clans, each with an approved admin; clan A also has an approved viewer."""
    clan_a, clan_b = uuid.uuid4(), uuid.uuid4()
    admin_a, admin_b, viewer_a = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with session_factory() as s:
        for cid, name in ((clan_a, "Clan A"), (clan_b, "Clan B")):
            await s.execute(
                sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, :n, :slug)"),
                {"id": cid, "n": name, "slug": f"upload-{cid.hex[:8]}"},
            )
        for uid, cid, role in (
            (admin_a, clan_a, "admin"),
            (admin_b, clan_b, "admin"),
            (viewer_a, clan_a, "viewer"),
        ):
            await s.execute(
                sa.text(
                    "INSERT INTO user_profiles (id, email, display_name) "
                    "VALUES (:id, :email, :role)"
                ),
                {"id": uid, "email": f"{uid.hex[:8]}@example.com", "role": role},
            )
            await s.execute(
                sa.text(
                    "INSERT INTO user_clan_roles "
                    "(user_id, clan_id, role, is_approved, approved_by, approved_at) "
                    "VALUES (:uid, :cid, :role, true, :uid, now())"
                ),
                {"uid": uid, "cid": cid, "role": role},
            )
        await s.commit()
    return {
        "clan_a": clan_a,
        "clan_b": clan_b,
        "admin_a": admin_a,
        "admin_b": admin_b,
        "viewer_a": viewer_a,
    }


@pytest.fixture()
def store() -> ObjectStore:
    return ObjectStore()


@pytest.fixture()
async def client(
    session_factory: async_sessionmaker[AsyncSession], store: ObjectStore
) -> AsyncGenerator[AsyncClient]:
    from app.application.document.upload import DocumentUploadHandler
    from app.infrastructure.event_dispatcher import create_event_dispatcher
    from app.infrastructure.persistence.document_repository import SqlAlchemyDocumentRepository
    from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork

    app = create_app()
    load_translations()  # no lifespan in this suite; localized messages need the catalogs

    async def _override_db() -> AsyncGenerator[AsyncSession]:
        async with session_factory() as session:
            yield session

    async def _make_upload_handler() -> AsyncGenerator[Any]:
        async with session_factory() as db:
            uow = SqlAlchemyUnitOfWork(db, create_event_dispatcher(db))
            yield DocumentUploadHandler(SqlAlchemyDocumentRepository(uow), store, uow)

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_current_user
    app.dependency_overrides[get_document_upload_handler] = _make_upload_handler

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


def _headers(seeded: dict[str, Any], user: str, clan: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {seeded[user]}",
        "X-Current-Clan-Id": str(seeded[clan]),
    }


async def _sign(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    content_type: str = "image/png",
    size_bytes: int = len(_PNG_BYTES),
) -> Response:
    return await client.post(
        "/api/v1/documents/uploads",
        headers=headers,
        json={"filename": "giapha.png", "content_type": content_type, "size_bytes": size_bytes},
    )


async def _staged(
    client: AsyncClient,
    headers: dict[str, str],
    store: ObjectStore,
    *,
    stored_type: str | None = "image/png",
    size_bytes: int = len(_PNG_BYTES),
) -> str:
    """Sign as image/png, then upload whatever the 'browser' actually sends."""
    signed = await _sign(client, headers, size_bytes=size_bytes)
    assert signed.status_code == 200, signed.text
    path = str(signed.json()["data"]["storage_path"])
    store.put(path, size_bytes, stored_type)
    return path


async def _confirm(client: AsyncClient, headers: dict[str, str], storage_path: str) -> Response:
    return await client.post(
        "/api/v1/documents",
        headers=headers,
        json={"storage_path": storage_path, "title": "Gia phả", "document_type": "photo"},
    )


async def _document_rows(
    session_factory: async_sessionmaker[AsyncSession], seeded: dict[str, Any]
) -> list[Any]:
    """This test's documents: the migrated database is shared by the whole session."""
    async with session_factory() as s:
        result = await s.execute(
            sa.text("SELECT clan_id, storage_path FROM documents WHERE clan_id IN (:a, :b)"),
            {"a": seeded["clan_a"], "b": seeded["clan_b"]},
        )
        return list(result.mappings().all())


# ── The path rule ────────────────────────────────────────────────────────────


async def test_a_staged_upload_becomes_a_document_of_the_signing_clan(
    client: AsyncClient,
    seeded: dict[str, Any],
    store: ObjectStore,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    headers = _headers(seeded, "admin_a", "clan_a")
    staged = await _staged(client, headers, store)

    resp = await _confirm(client, headers, staged)

    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["storage_path"] == staged.replace("/uploads/", "/documents/")
    assert (data["mime_type"], data["file_size_bytes"]) == ("image/png", len(_PNG_BYTES))
    assert set(store.objects) == {data["storage_path"]}
    rows = await _document_rows(session_factory, seeded)
    assert [(r["clan_id"], r["storage_path"]) for r in rows] == [
        (seeded["clan_a"], data["storage_path"])
    ]


async def test_confirming_another_clans_staged_path_is_refused_and_its_file_survives(
    client: AsyncClient,
    seeded: dict[str, Any],
    store: ObjectStore,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    theirs = await _staged(client, _headers(seeded, "admin_b", "clan_b"), store)

    resp = await _confirm(client, _headers(seeded, "admin_a", "clan_a"), theirs)

    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "document.upload_path_invalid"
    assert set(store.objects) == {theirs}  # clan B's file is where clan B left it
    assert await _document_rows(session_factory, seeded) == []


async def test_confirming_an_existing_documents_path_is_refused(
    client: AsyncClient,
    seeded: dict[str, Any],
    store: ObjectStore,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    headers = _headers(seeded, "admin_a", "clan_a")
    first = await _confirm(client, headers, await _staged(client, headers, store))
    assert first.status_code == 201, first.text
    confirmed_path = first.json()["data"]["storage_path"]

    resp = await _confirm(client, headers, confirmed_path)

    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "document.upload_path_invalid"
    assert len(await _document_rows(session_factory, seeded)) == 1
    assert confirmed_path in store.objects


async def test_a_second_confirm_of_one_path_is_refused_and_leaves_one_row(
    client: AsyncClient,
    seeded: dict[str, Any],
    store: ObjectStore,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    headers = _headers(seeded, "admin_a", "clan_a")
    staged = await _staged(client, headers, store)
    assert (await _confirm(client, headers, staged)).status_code == 201

    resp = await _confirm(client, headers, staged)

    assert resp.status_code == 404, resp.text
    assert resp.json()["error"]["code"] == "document.upload_not_found"
    assert len(await _document_rows(session_factory, seeded)) == 1


# ── The re-read of what Storage holds ────────────────────────────────────────


async def test_a_file_signed_as_an_image_but_stored_as_html_is_refused_and_deleted(
    client: AsyncClient,
    seeded: dict[str, Any],
    store: ObjectStore,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    headers = _headers(seeded, "admin_a", "clan_a")
    staged = await _staged(client, headers, store, stored_type="text/html")

    resp = await _confirm(client, headers, staged)

    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "invalid_mime_type"
    assert store.objects == {}
    assert await _document_rows(session_factory, seeded) == []


async def test_a_stored_file_over_the_limit_is_refused_and_deleted(
    client: AsyncClient,
    seeded: dict[str, Any],
    store: ObjectStore,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = _headers(seeded, "admin_a", "clan_a")
    # Signed while the limit was 50 MB, stored at 2 MB, confirmed under a 1 MB limit:
    # the confirm call must read the stored size, not trust the signing.
    staged = await _staged(client, headers, store, size_bytes=2 * _MB)
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_MB", 1)

    resp = await _confirm(client, headers, staged)

    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "file_too_large"
    assert store.objects == {}
    assert await _document_rows(session_factory, seeded) == []


# ── Signing ──────────────────────────────────────────────────────────────────


async def test_signing_refuses_a_declared_file_over_the_limit(
    client: AsyncClient, seeded: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_MB", 1)
    resp = await _sign(client, _headers(seeded, "admin_a", "clan_a"), size_bytes=_MB + 1)
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "file_too_large"


async def test_signing_accepts_a_20_mb_file_under_the_default_limit(
    client: AsyncClient, seeded: dict[str, Any]
) -> None:
    resp = await _sign(client, _headers(seeded, "admin_a", "clan_a"), size_bytes=20 * _MB)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["storage_path"].startswith(f"clans/{seeded['clan_a']}/uploads/")
    assert data["upload_url"] and data["token"] and data["expires_at"]


async def test_a_viewer_cannot_sign_an_upload(client: AsyncClient, seeded: dict[str, Any]) -> None:
    resp = await _sign(client, _headers(seeded, "viewer_a", "clan_a"))
    assert resp.status_code == 403, resp.text
