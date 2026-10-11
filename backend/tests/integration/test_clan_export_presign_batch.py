"""The clan export presigns its documents in one batch (#271).

Real Postgres (migrated_db_url), real RBAC, JWT verification stubbed as in
test_clan_export_json.py. Two seams:

- **A counting `StoragePort`.** It records every batch and single presign, so a
  250-document export can be read for how many Storage calls the presign step made.
- **The real `SupabaseStorageAdapter` over a faked storage3 client.** The fake
  answers the way local storage-api v1.77.5 answered on 2026-10-11: the single
  sign of a missing object raises a 404 `not_found`, the batch sign reports it per
  item inside a 200. That lets one test read the export's failure beside the
  failure `GET /documents/{id}`'s single presign produces for the same Storage state.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, Sequence
from typing import Any
from unittest.mock import MagicMock

import pytest
import sqlalchemy as sa
from fastapi import Header
from httpx2 import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from storage3.exceptions import StorageApiError

from app.core.database import get_db
from app.core.security import get_current_user
from app.infrastructure.dependencies import get_export_query_handler
from app.main import create_app

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_DOCUMENT_COUNT = 250
_MISSING = "Either the object does not exist or you do not have access to it"


async def _override_current_user(
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    assert authorization is not None, "test client must send an Authorization header"
    return {"sub": authorization.removeprefix("Bearer ")}


class CountingStorage:
    """A StoragePort that counts presign calls and signs each path to its own URL."""

    def __init__(self) -> None:
        self.batch_calls: list[list[str]] = []
        self.single_calls: list[str] = []

    async def get_presigned_urls(
        self, storage_paths: Sequence[str], expires_in: int = 3600
    ) -> dict[str, str]:
        self.batch_calls.append(list(storage_paths))
        # Reversed, so a caller that pairs URLs with documents by position, not by
        # path, hands a document another document's URL.
        return {p: f"https://signed.example/{p}" for p in reversed(storage_paths)}

    async def get_presigned_url(self, storage_path: str, expires_in: int = 3600) -> str:
        self.single_calls.append(storage_path)
        return f"https://signed.example/{storage_path}"

    async def delete(self, storage_path: str) -> bool:
        raise AssertionError("delete called unexpectedly")

    async def publish_public(
        self, *, source_path: str, destination_path: str, content_type: str | None
    ) -> str:
        raise AssertionError("publish_public called unexpectedly")


class FakeFilesApi:
    """``client.storage.from_(bucket)`` for one Storage state: some objects missing,
    or the provider unreachable."""

    def __init__(self, *, missing: frozenset[str] = frozenset(), down: bool = False) -> None:
        self.missing = missing
        self.down = down

    def create_signed_url(self, path: str, expires_in: int) -> dict[str, Any]:
        if self.down:
            raise ConnectionError("connection refused")
        if path in self.missing:
            raise StorageApiError("Object not found", "not_found", "404")
        return {"signedURL": f"https://storage.example/{path}"}

    def create_signed_urls(self, paths: list[str], expires_in: int) -> list[dict[str, Any]]:
        if self.down:
            raise ConnectionError("connection refused")
        return [
            {"error": _MISSING, "path": p, "signedURL": None}
            if p in self.missing
            else {"error": None, "path": p, "signedURL": f"https://storage.example/{p}"}
            for p in paths
        ]


@pytest.fixture()
async def session_factory(
    migrated_db_url: str,
) -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(migrated_db_url)
    yield async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    await engine.dispose()


async def _seed_clan(
    maker: async_sessionmaker[AsyncSession], document_count: int
) -> tuple[dict[str, str], dict[uuid.UUID, str]]:
    """A clan with an approved admin and ``document_count`` live documents.

    Returns the admin's headers and each document's storage_path by id.
    """
    clan_id, admin_id = uuid.uuid4(), uuid.uuid4()
    documents = {
        doc_id: f"clans/{clan_id}/documents/{doc_id}.png"
        for doc_id in (uuid.uuid4() for _ in range(document_count))
    }
    async with maker() as s:
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'Họ Lê', :slug)"),
            {"id": clan_id, "slug": f"ho-le-{clan_id.hex[:8]}"},
        )
        await s.execute(
            sa.text(
                "INSERT INTO user_profiles (id, email, display_name) VALUES (:id, :email, 'admin')"
            ),
            {"id": admin_id, "email": f"{admin_id.hex[:8]}@example.com"},
        )
        await s.execute(
            sa.text(
                "INSERT INTO user_clan_roles "
                "(user_id, clan_id, role, is_approved, approved_by, approved_at) "
                "VALUES (:uid, :cid, 'admin', true, :uid, now())"
            ),
            {"uid": admin_id, "cid": clan_id},
        )
        if documents:
            await s.execute(
                sa.text(
                    "INSERT INTO documents "
                    "(id, clan_id, title, document_type, storage_path, created_by) "
                    "VALUES (:id, :cid, :title, 'photo', :sp, :cb)"
                ),
                [
                    {"id": d, "cid": clan_id, "title": f"doc {i}", "sp": sp, "cb": admin_id}
                    for i, (d, sp) in enumerate(documents.items())
                ],
            )
        await s.commit()
    headers = {"Authorization": f"Bearer {admin_id}", "X-Current-Clan-Id": str(clan_id)}
    return headers, documents


def _app(maker: async_sessionmaker[AsyncSession]) -> Any:
    app = create_app()

    async def _override_db() -> AsyncGenerator[AsyncSession]:
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_current_user
    return app


async def test_250_documents_are_presigned_in_one_batch_each_url_its_own_path(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    from app.application.export.handlers import ExportQueryHandler
    from app.infrastructure.persistence.export_query_port import SqlAlchemyExportQueryPort
    from app.services.clan_export import build_clan_export, to_json_bytes
    from app.services.gedcom_export import build_gedcom

    headers, documents = await _seed_clan(session_factory, _DOCUMENT_COUNT)
    _, other_clan_documents = await _seed_clan(session_factory, 1)
    storage = CountingStorage()
    app = _app(session_factory)

    async def _make_export_handler() -> AsyncGenerator[ExportQueryHandler]:
        async with session_factory() as db:
            yield ExportQueryHandler(
                SqlAlchemyExportQueryPort(db),
                storage,
                build_clan_export,
                to_json_bytes,
                build_gedcom,
            )

    app.dependency_overrides[get_export_query_handler] = _make_export_handler
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/exports/clan?format=json", headers=headers)

    assert resp.status_code == 200, resp.text
    manifest = resp.json()["documents_manifest"]
    assert storage.single_calls == []
    assert len(storage.batch_calls) == 1
    assert sorted(storage.batch_calls[0]) == sorted(documents.values())
    assert not set(storage.batch_calls[0]) & set(other_clan_documents.values())
    assert {uuid.UUID(entry["id"]): entry["storage_path"] for entry in manifest} == documents
    for entry in manifest:
        assert entry["download_url"] == f"https://signed.example/{entry['storage_path']}"
    assert len({entry["download_url_expires_at"] for entry in manifest}) == 1


@pytest.mark.parametrize(
    "state, expected",
    [
        pytest.param("one-missing", (404, "storage_not_found"), id="one-object-missing"),
        pytest.param("down", (503, "storage_unavailable"), id="provider-down"),
    ],
)
async def test_the_export_fails_as_a_single_presign_fails_for_the_same_storage(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    state: str,
    expected: tuple[int, str],
) -> None:
    from app.infrastructure.storage import supabase_adapter

    headers, documents = await _seed_clan(session_factory, 3)
    doc_id, path = next(iter(documents.items()))
    files_api = (
        FakeFilesApi(missing=frozenset({path}))
        if state == "one-missing"
        else FakeFilesApi(down=True)
    )
    client_stub = MagicMock()
    client_stub.storage.from_.return_value = files_api
    monkeypatch.setattr(supabase_adapter, "get_service_client", lambda: client_stub)

    app = _app(session_factory)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        single = await client.get(f"/api/v1/documents/{doc_id}", headers=headers)
        export = await client.get("/api/v1/exports/clan?format=json", headers=headers)

    single_reading = (single.status_code, single.json()["error"]["code"])
    export_reading = (export.status_code, export.json()["error"]["code"])
    assert single_reading == expected
    assert export_reading == single_reading
