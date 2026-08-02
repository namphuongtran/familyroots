"""Every presigned URL the API hands out states its own expiry.

Gap closed here (frontend-integration-guide §8): `POST /documents` set
`presigned_url_expires_at`, but `GET /documents/{id}` and
`POST /documents/{id}/restore` returned a fresh `presigned_url` with
`presigned_url_expires_at: null` — so clients hardcoded a guessed 1-hour TTL.

Harness mirrors tests/integration/test_document_soft_delete.py: real Postgres,
real RBAC and repository, JWT *verification* stubbed (the Authorization header
carries the user id), storage swapped for an in-memory double so no Supabase
call is made.

Negative control: `test_get_expiry_matches_the_ttl_the_url_was_signed_with`
asserts the value is non-null AND lands in the TTL window the URL was actually
signed with — reverting the handler to omit the field (the old behaviour) makes
it fail on `is not None`, and returning an arbitrary constant fails the window.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi import Header
from httpx2 import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.core.security import get_current_user
from app.domain.document.repository import DEFAULT_PRESIGN_TTL
from app.infrastructure.dependencies import get_document_command_handler, get_document_query_handler
from app.main import create_app
from app.services.translator import load_translations

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


async def _override_current_user(
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    assert authorization is not None, "test client must send an Authorization header"
    return {"sub": authorization.removeprefix("Bearer ")}


class FakeStorage:
    """In-memory StoragePort double that records the TTL each URL was signed with."""

    def __init__(self) -> None:
        self.signed_ttls: list[int] = []

    async def upload(self, path: str, content: bytes, content_type: str | None) -> str:
        return path

    async def delete(self, storage_path: str) -> bool:
        return True

    async def get_presigned_url(
        self, storage_path: str, expires_in: int = DEFAULT_PRESIGN_TTL
    ) -> str:
        self.signed_ttls.append(expires_in)
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
    """Two clans, each with its own approved admin — the two-sided isolation setup."""
    clan_a, clan_b = uuid.uuid4(), uuid.uuid4()
    admin_a, admin_b = uuid.uuid4(), uuid.uuid4()
    async with session_factory() as s:
        for cid, name in ((clan_a, "Clan A"), (clan_b, "Clan B")):
            await s.execute(
                sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, :n, :slug)"),
                {"id": cid, "n": name, "slug": f"presign-{cid.hex[:8]}"},
            )
        for uid, cid in ((admin_a, clan_a), (admin_b, clan_b)):
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
    return {"clan_a": clan_a, "clan_b": clan_b, "admin_a": admin_a, "admin_b": admin_b}


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
    load_translations()  # no lifespan in this suite; localized messages need the catalogs

    async def _override_db() -> AsyncGenerator[AsyncSession]:
        async with session_factory() as session:
            yield session

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

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


def _headers(seeded: dict[str, Any], clan: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {seeded['admin_' + clan]}",
        "X-Current-Clan-Id": str(seeded["clan_" + clan]),
    }


@pytest.fixture()
async def doc_in_clan_a(client: AsyncClient, seeded: dict[str, Any]) -> str:
    resp = await client.post(
        "/api/v1/documents",
        headers=_headers(seeded, "a"),
        data={"title": "Ảnh gia phả", "document_type": "photo"},
        files={"file": ("test.png", _PNG_BYTES, "image/png")},
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["data"]["id"])


def _assert_within_ttl_window(raw_expiry: str | None, ttl_seconds: int, sent_at: datetime) -> None:
    """The stated expiry must be `sent_at + ttl` (± a generous request-time slack)."""
    assert raw_expiry is not None, "presigned_url_expires_at must not be null"
    expires_at = datetime.fromisoformat(raw_expiry)
    assert expires_at.tzinfo is not None, "expiry must be timezone-aware (UTC)"
    drift = (expires_at - sent_at).total_seconds() - ttl_seconds
    assert -1 <= drift <= 30, f"expiry drifts {drift:.1f}s from the {ttl_seconds}s TTL"


async def test_get_expiry_matches_the_ttl_the_url_was_signed_with(
    client: AsyncClient,
    seeded: dict[str, Any],
    doc_in_clan_a: str,
    fake_storage: FakeStorage,
) -> None:
    """GET /documents/{id} states the deadline of the URL it just minted."""
    fake_storage.signed_ttls.clear()
    sent_at = datetime.now(UTC)
    resp = await client.get(f"/api/v1/documents/{doc_in_clan_a}", headers=_headers(seeded, "a"))
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    assert data["presigned_url"] is not None
    assert fake_storage.signed_ttls == [DEFAULT_PRESIGN_TTL]  # the TTL actually signed
    _assert_within_ttl_window(data["presigned_url_expires_at"], DEFAULT_PRESIGN_TTL, sent_at)


async def test_upload_and_get_agree_on_the_expiry_contract(
    client: AsyncClient, seeded: dict[str, Any]
) -> None:
    """Upload already set the field; GET must not be the odd one out."""
    sent_at = datetime.now(UTC)
    upload = await client.post(
        "/api/v1/documents",
        headers=_headers(seeded, "a"),
        data={"title": "Giấy khai sinh", "document_type": "photo"},
        files={"file": ("test.png", _PNG_BYTES, "image/png")},
    )
    assert upload.status_code == 201, upload.text
    _assert_within_ttl_window(
        upload.json()["data"]["presigned_url_expires_at"], DEFAULT_PRESIGN_TTL, sent_at
    )

    doc_id = upload.json()["data"]["id"]
    fetched = await client.get(f"/api/v1/documents/{doc_id}", headers=_headers(seeded, "a"))
    _assert_within_ttl_window(
        fetched.json()["data"]["presigned_url_expires_at"], DEFAULT_PRESIGN_TTL, sent_at
    )


async def test_restore_response_also_states_its_expiry(
    client: AsyncClient, seeded: dict[str, Any], doc_in_clan_a: str
) -> None:
    """POST /{id}/restore returns a fresh presigned_url — with its deadline."""
    headers = _headers(seeded, "a")
    assert (await client.delete(f"/api/v1/documents/{doc_in_clan_a}", headers=headers)).status_code
    sent_at = datetime.now(UTC)
    resp = await client.post(f"/api/v1/documents/{doc_in_clan_a}/restore", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["presigned_url"] is not None
    _assert_within_ttl_window(data["presigned_url_expires_at"], DEFAULT_PRESIGN_TTL, sent_at)


async def test_clan_isolation_two_sided(
    client: AsyncClient,
    seeded: dict[str, Any],
    doc_in_clan_a: str,
    fake_storage: FakeStorage,
) -> None:
    """Clan A reads its own document with a signed URL; clan B gets 404 — and no
    URL is signed for the outsider, so the fix leaks nothing across the boundary."""
    own = await client.get(f"/api/v1/documents/{doc_in_clan_a}", headers=_headers(seeded, "a"))
    assert own.status_code == 200
    assert own.json()["data"]["presigned_url_expires_at"] is not None

    fake_storage.signed_ttls.clear()
    other = await client.get(f"/api/v1/documents/{doc_in_clan_a}", headers=_headers(seeded, "b"))
    assert other.status_code == 404, other.text
    assert other.json()["error"]["code"] == "document_not_found"
    assert fake_storage.signed_ttls == []  # nothing presigned for the other clan
