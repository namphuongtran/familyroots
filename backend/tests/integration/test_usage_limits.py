"""Usage limits over HTTP (#332): upload signings per user, exports per clan, storage per clan.

Real Postgres, real RBAC and repository; JWT *verification* is stubbed (the Authorization
header carries the user id), and Storage is an in-memory double, so nothing leaves the
process. The rate limits count in the app's in-memory store, as they do with no
``KV_REST_API_*`` set; ``tests/integration/test_rate_limit_shared_store.py`` is the
evidence about the shared store itself.

The numbers below are the decided defaults of #326, written out rather than read from
settings, so that raising a setting above a test's count fails that test.

Negative controls, run 2026-11-21, each failing the named test with the 31st, 6th or
over-quota request answered 200:
- ``UPLOAD_SIGN_MAX_PER_HOUR`` default raised to 31: ``test_the_31st_upload_signing...``;
- ``CLAN_EXPORT_MAX_PER_DAY`` default raised to 6: ``test_the_6th_export...``;
- ``CLAN_STORAGE_QUOTA_MB`` default raised to 1025: ``test_an_upload_over_the_remaining...``;
- the soft-deleted rows dropped from ``storage_bytes_used`` (``is_deleted = false`` added):
  ``test_an_upload_over_the_remaining...``.
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

from app.core.database import get_db
from app.core.security import get_current_user
from app.domain.document.repository import SignedUpload, StorageNotFoundError, StoredObject
from app.infrastructure.dependencies import get_document_upload_handler, get_export_query_handler
from app.main import create_app
from app.services.translator import load_translations

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_SIGNINGS_PER_HOUR = 30
_EXPORTS_PER_DAY = 5
_QUOTA_BYTES = 1024 * 1024 * 1024  # 1 GB


async def _override_current_user(
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    assert authorization is not None, "test client must send an Authorization header"
    return {"sub": authorization.removeprefix("Bearer ")}


class FakeStorage:
    """Only what signing and a GEDCOM export reach."""

    async def create_signed_upload(self, path: str) -> SignedUpload:
        return SignedUpload(upload_url=f"https://storage.example/sign/{path}", token="t")

    async def stat(self, path: str) -> StoredObject:
        raise StorageNotFoundError(path)

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
    """Clan A with two admins, clan B with one."""
    clan_a, clan_b = uuid.uuid4(), uuid.uuid4()
    admin_a, admin2_a, admin_b = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with session_factory() as s:
        for cid, name in ((clan_a, "Clan A"), (clan_b, "Clan B")):
            await s.execute(
                sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, :n, :slug)"),
                {"id": cid, "n": name, "slug": f"limits-{cid.hex[:8]}"},
            )
        for uid, cid in ((admin_a, clan_a), (admin2_a, clan_a), (admin_b, clan_b)):
            await s.execute(
                sa.text(
                    "INSERT INTO user_profiles (id, email, display_name) "
                    "VALUES (:id, :email, 'admin')"
                ),
                {"id": uid, "email": f"{uid.hex[:8]}@example.com"},
            )
            await s.execute(
                sa.text(
                    "INSERT INTO user_clan_roles "
                    "(user_id, clan_id, role, is_approved, approved_by, approved_at) "
                    "VALUES (:uid, :cid, 'admin', true, :uid, now())"
                ),
                {"uid": uid, "cid": cid},
            )
        await s.commit()
    return {
        "clan_a": clan_a,
        "clan_b": clan_b,
        "admin_a": admin_a,
        "admin2_a": admin2_a,
        "admin_b": admin_b,
    }


@pytest.fixture()
async def client(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncClient]:
    from app.application.document.upload import DocumentUploadHandler
    from app.application.export.handlers import ExportQueryHandler
    from app.infrastructure.event_dispatcher import create_event_dispatcher
    from app.infrastructure.persistence.document_repository import SqlAlchemyDocumentRepository
    from app.infrastructure.persistence.export_query_port import SqlAlchemyExportQueryPort
    from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
    from app.services.clan_export import build_clan_export, to_json_bytes
    from app.services.gedcom_export import build_gedcom

    app = create_app()
    load_translations()  # no lifespan in this suite; localized messages need the catalogs
    storage = FakeStorage()

    async def _override_db() -> AsyncGenerator[AsyncSession]:
        async with session_factory() as session:
            yield session

    async def _make_upload_handler() -> AsyncGenerator[Any]:
        async with session_factory() as db:
            uow = SqlAlchemyUnitOfWork(db, create_event_dispatcher(db))
            yield DocumentUploadHandler(SqlAlchemyDocumentRepository(uow), storage, uow)  # type: ignore[arg-type]

    async def _make_export_handler() -> AsyncGenerator[Any]:
        async with session_factory() as db:
            yield ExportQueryHandler(
                SqlAlchemyExportQueryPort(db),
                storage,  # type: ignore[arg-type]
                build_clan_export,
                to_json_bytes,
                build_gedcom,
            )

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_current_user
    app.dependency_overrides[get_document_upload_handler] = _make_upload_handler
    app.dependency_overrides[get_export_query_handler] = _make_export_handler

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


def _headers(seeded: dict[str, Any], user: str, clan: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {seeded[user]}", "X-Current-Clan-Id": str(seeded[clan])}


async def _sign(client: AsyncClient, headers: dict[str, str], size_bytes: int = 16) -> Response:
    return await client.post(
        "/api/v1/documents/uploads",
        headers=headers,
        json={"filename": "giapha.png", "content_type": "image/png", "size_bytes": size_bytes},
    )


async def _export(client: AsyncClient, headers: dict[str, str]) -> Response:
    return await client.get("/api/v1/exports/clan?format=gedcom", headers=headers)


def _assert_rate_limited(resp: Response, code: str, window_seconds: int) -> None:
    assert resp.status_code == 429, resp.text
    error = resp.json()["error"]
    assert error["code"] == code
    retry_after = error["detail"]["retry_after"]
    assert 0 < retry_after <= window_seconds + 1
    assert resp.headers["Retry-After"] == str(retry_after)


async def test_the_31st_upload_signing_in_an_hour_is_refused(
    client: AsyncClient, seeded: dict[str, Any]
) -> None:
    headers = _headers(seeded, "admin_a", "clan_a")
    statuses = [(await _sign(client, headers)).status_code for _ in range(_SIGNINGS_PER_HOUR)]
    assert statuses == [200] * _SIGNINGS_PER_HOUR

    _assert_rate_limited(await _sign(client, headers), "document.upload_rate_limited", 3600)

    # Per user: another editor of the same clan still signs.
    other = await _sign(client, _headers(seeded, "admin2_a", "clan_a"))
    assert other.status_code == 200, other.text


async def test_the_6th_export_in_a_day_is_refused(
    client: AsyncClient, seeded: dict[str, Any]
) -> None:
    headers = _headers(seeded, "admin_a", "clan_a")
    statuses = [(await _export(client, headers)).status_code for _ in range(_EXPORTS_PER_DAY)]
    assert statuses == [200] * _EXPORTS_PER_DAY

    _assert_rate_limited(await _export(client, headers), "export.rate_limited", 86400)

    # Per clan: the clan's other admin is refused too, and another clan is not.
    _assert_rate_limited(
        await _export(client, _headers(seeded, "admin2_a", "clan_a")), "export.rate_limited", 86400
    )
    other_clan = await _export(client, _headers(seeded, "admin_b", "clan_b"))
    assert other_clan.status_code == 200, other_clan.text


async def test_an_upload_over_the_remaining_quota_is_refused(
    client: AsyncClient,
    seeded: dict[str, Any],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Clan A holds the quota less 1000 bytes: 500 of them in a soft-deleted document
    the purge has not removed yet, which still counts. A row holds at most 50 MB
    (``documents_file_size_limit``), so the live bytes are spread over several rows."""
    remaining = 1000
    soft_deleted = 500
    live = _QUOTA_BYTES - remaining - soft_deleted
    sizes = [(50 * 1024 * 1024, False)] * (live // (50 * 1024 * 1024))
    sizes += [(live % (50 * 1024 * 1024), False), (soft_deleted, True)]
    async with session_factory() as s:
        for size, deleted in sizes:
            await s.execute(
                sa.text(
                    "INSERT INTO documents (id, clan_id, title, document_type, storage_path, "
                    "file_size_bytes, mime_type, created_by, is_deleted, deleted_at) "
                    "VALUES (:id, :clan, 'Gia phả', 'photo', :path, :size, 'image/png', "
                    ":by, :deleted, CASE WHEN :deleted THEN now() END)"
                ),
                {
                    "id": uuid.uuid4(),
                    "clan": seeded["clan_a"],
                    "path": f"clans/{seeded['clan_a']}/documents/{uuid.uuid4()}.png",
                    "size": size,
                    "by": seeded["admin_a"],
                    "deleted": deleted,
                },
            )
        await s.commit()
    headers = _headers(seeded, "admin_a", "clan_a")

    over = await _sign(client, headers, size_bytes=remaining + 1)

    assert over.status_code == 422, over.text
    error = over.json()["error"]
    assert error["code"] == "document.storage_quota_exceeded"
    assert error["detail"] == {
        "quota_bytes": _QUOTA_BYTES,
        "used_bytes": _QUOTA_BYTES - remaining,
        "remaining_bytes": remaining,
    }

    # Exactly the remainder fits, and another clan's quota is its own.
    assert (await _sign(client, headers, size_bytes=remaining)).status_code == 200
    other_clan = await _sign(
        client, _headers(seeded, "admin_b", "clan_b"), size_bytes=remaining + 1
    )
    assert other_clan.status_code == 200, other_clan.text
