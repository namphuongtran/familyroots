"""GEDCOM 5.5.1 clan export integration test — real Postgres, real RBAC.

Closes the `fmt="gedcom"` stub (previously `NotImplementedError` -> 500):
GET `?format=gedcom` must return 200 with a `.ged` attachment.

This is a self-contained copy of `test_clan_export_json.py`'s rich-clan
fixture (per repo convention: integration test files are self-contained,
not import-sharing fixtures across files). Cháu A is display-only —
`birth_date IS NULL`, `birth_date_precision="circa"`,
`birth_date_display="khoảng 1975"` — matching the JSON archive's rich-clan
fixture exactly. This exercises the approximate-only-date NOTE fallback
(task 5 review, FIX 2): a `birth_date`-less person with a display string
must still emit `1 BIRT` + `2 NOTE <display>` rather than being silently
dropped from the export. (An earlier revision of this fixture instead gave
Cháu A a real `birth_date` to exercise the `circa -> ABT <year>` mapping;
that mapping is already covered directly by
`app.services.gedcom_export`'s unit tests, so restoring the display-only
shape here lets this test cover the NOTE fallback end-to-end instead.)

Two-sided clan isolation is already covered for the export use case by
`test_clan_export_json.py::test_export_isolation_two_sided` (same port/query
layer underneath both formats) — not repeated here.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, date, datetime
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi import Header
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.core.security import get_current_user
from app.infrastructure.dependencies import (
    get_document_command_handler,
    get_export_query_handler,
)
from app.main import create_app

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


async def _override_current_user(
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    assert authorization is not None, "test client must send an Authorization header"
    return {"sub": authorization.removeprefix("Bearer ")}


class FakeStorage:
    """In-memory StoragePort double — mirrors test_clan_export_json.FakeStorage
    so the upload path never touches real Supabase Storage. GEDCOM export
    itself doesn't presign documents, but DocumentCommandHandler still needs
    a StoragePort for the seeded upload."""

    def __init__(self) -> None:
        self.uploaded: list[str] = []

    async def upload(self, path: str, content: bytes, content_type: str | None) -> str:
        self.uploaded.append(path)
        return path

    async def delete(self, storage_path: str) -> bool:
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
def fake_storage() -> FakeStorage:
    return FakeStorage()


@pytest.fixture()
async def client(
    session_factory: async_sessionmaker[AsyncSession],
    fake_storage: FakeStorage,
) -> AsyncGenerator[AsyncClient]:
    from app.application.document.handlers import DocumentCommandHandler
    from app.application.export.handlers import ExportQueryHandler
    from app.infrastructure.event_dispatcher import create_event_dispatcher
    from app.infrastructure.persistence.document_repository import SqlAlchemyDocumentRepository
    from app.infrastructure.persistence.export_query_port import SqlAlchemyExportQueryPort
    from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
    from app.services.clan_export import build_clan_export, to_json_bytes
    from app.services.gedcom_export import build_gedcom

    app = create_app()

    async def _override_db() -> AsyncGenerator[AsyncSession]:
        async with session_factory() as session:
            yield session

    async def _make_cmd_handler() -> AsyncGenerator[Any]:
        async with session_factory() as db:
            uow = SqlAlchemyUnitOfWork(db, create_event_dispatcher(db))
            yield DocumentCommandHandler(SqlAlchemyDocumentRepository(uow), fake_storage, uow)

    async def _make_export_handler() -> AsyncGenerator[Any]:
        async with session_factory() as db:
            yield ExportQueryHandler(
                SqlAlchemyExportQueryPort(db),
                fake_storage,
                build_clan_export,
                to_json_bytes,
                build_gedcom,
            )

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_current_user
    app.dependency_overrides[get_document_command_handler] = _make_cmd_handler
    app.dependency_overrides[get_export_query_handler] = _make_export_handler

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest.fixture()
async def rich_clan(
    session_factory: async_sessionmaker[AsyncSession],
    client: AsyncClient,
) -> dict[str, Any]:
    """ "clan đủ gia vị": thủy tổ + polygamous con trưởng + 2 cháu (1 adopted) +
    1 soft-deleted person, 1 soft-deleted marriage, 1 branch, plus a real
    uploaded document. Also seeds a second (minimal) clan for the DI wiring
    sanity of the fixture (isolation itself is asserted in the JSON test)."""
    clan_a = uuid.uuid4()
    clan_b = uuid.uuid4()
    admin_a = uuid.uuid4()
    editor_a = uuid.uuid4()
    admin_b = uuid.uuid4()

    founder = uuid.uuid4()
    con_truong = uuid.uuid4()
    vo_ca = uuid.uuid4()
    vo_hai = uuid.uuid4()
    chau_a = uuid.uuid4()
    chau_b = uuid.uuid4()
    deleted_person = uuid.uuid4()
    branch_id = uuid.uuid4()

    async with session_factory() as s:
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'Họ Nguyễn', :slug)"),
            {"id": clan_a, "slug": f"ho-nguyen-{clan_a.hex[:8]}"},
        )
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'Họ Trần', :slug)"),
            {"id": clan_b, "slug": f"ho-tran-{clan_b.hex[:8]}"},
        )

        for uid, role, cid in (
            (admin_a, "admin", clan_a),
            (editor_a, "editor", clan_a),
            (admin_b, "admin", clan_b),
        ):
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
                {"uid": uid, "cid": cid, "role": role},
            )

        await s.execute(
            sa.text("INSERT INTO branches (id, clan_id, name) VALUES (:id, :cid, 'Chi Hai')"),
            {"id": branch_id, "cid": clan_a},
        )

        persons = [
            {
                "id": founder,
                "full_name": "Cụ Thủy Tổ",
                "gender": "male",
                "birth_date": date(1920, 1, 1),
                "birth_date_precision": "year",
                "birth_date_display": None,
                "lunar_birth_date": "15/08 Canh Thân",
                "is_deleted": False,
            },
            {
                "id": con_truong,
                "full_name": "Con Trưởng",
                "gender": "male",
                "birth_date": None,
                "birth_date_precision": "unknown",
                "birth_date_display": None,
                "lunar_birth_date": None,
                "is_deleted": False,
            },
            {
                "id": vo_ca,
                "full_name": "Vợ Cả",
                "gender": "female",
                "birth_date": None,
                "birth_date_precision": "unknown",
                "birth_date_display": None,
                "lunar_birth_date": None,
                "is_deleted": False,
            },
            {
                "id": vo_hai,
                "full_name": "Vợ Hai",
                "gender": "female",
                "birth_date": None,
                "birth_date_precision": "unknown",
                "birth_date_display": None,
                "lunar_birth_date": None,
                "is_deleted": False,
            },
            {
                "id": chau_a,
                "full_name": "Cháu A",
                "gender": "female",
                # Display-only approximate date (see module docstring):
                # `birth_date` is NULL, matching the JSON fixture exactly —
                # exercises FIX 2's NOTE fallback end-to-end.
                "birth_date": None,
                "birth_date_precision": "circa",
                "birth_date_display": "khoảng 1975",
                "lunar_birth_date": None,
                "is_deleted": False,
            },
            {
                "id": chau_b,
                "full_name": "Cháu B",
                "gender": "male",
                "birth_date": None,
                "birth_date_precision": "unknown",
                "birth_date_display": None,
                "lunar_birth_date": None,
                "is_deleted": False,
            },
            {
                "id": deleted_person,
                "full_name": "Người Đã Xóa",
                "gender": "unknown",
                "birth_date": None,
                "birth_date_precision": "unknown",
                "birth_date_display": None,
                "lunar_birth_date": None,
                "is_deleted": True,
            },
        ]
        for p in persons:
            await s.execute(
                sa.text(
                    "INSERT INTO persons "
                    "(id, full_name, gender, birth_date, birth_date_precision, "
                    "birth_date_display, lunar_birth_date, is_deleted, "
                    "created_by_clan_id, created_by) "
                    "VALUES (:id, :full_name, :gender, :birth_date, :birth_date_precision, "
                    ":birth_date_display, :lunar_birth_date, :is_deleted, :cid, :cid_actor)"
                ),
                {**p, "cid": clan_a, "cid_actor": admin_a},
            )

        joined_at = datetime(2024, 1, 1, tzinfo=UTC)
        memberships = [
            {"person_id": founder, "is_founder": True, "branch_id": None},
            {"person_id": con_truong, "is_founder": False, "branch_id": None},
            {"person_id": vo_ca, "is_founder": False, "branch_id": None},
            {"person_id": vo_hai, "is_founder": False, "branch_id": None},
            {"person_id": chau_a, "is_founder": False, "branch_id": branch_id},
            {"person_id": chau_b, "is_founder": False, "branch_id": branch_id},
            {"person_id": deleted_person, "is_founder": False, "branch_id": None},
        ]
        for m in memberships:
            await s.execute(
                sa.text(
                    "INSERT INTO clan_memberships "
                    "(person_id, clan_id, is_founder, branch_id, joined_at) "
                    "VALUES (:person_id, :cid, :is_founder, :branch_id, :joined_at)"
                ),
                {**m, "cid": clan_a, "joined_at": joined_at},
            )

        marriages = [
            {
                "id": uuid.uuid4(),
                "person1_id": con_truong,
                "person2_id": vo_ca,
                "status": "married",
                "spouse_order": 1,
                "is_deleted": False,
            },
            {
                "id": uuid.uuid4(),
                "person1_id": con_truong,
                "person2_id": vo_hai,
                "status": "married",
                "spouse_order": 2,
                "is_deleted": False,
            },
            {
                "id": uuid.uuid4(),
                "person1_id": chau_a,
                "person2_id": chau_b,
                "status": "divorced",
                "spouse_order": None,
                "is_deleted": True,
            },
        ]
        for mm in marriages:
            await s.execute(
                sa.text(
                    "INSERT INTO marriages "
                    "(id, person1_id, person2_id, created_by_clan_id, status, "
                    "spouse_order, is_deleted, created_by) "
                    "VALUES (:id, :person1_id, :person2_id, :cid, :status, "
                    ":spouse_order, :is_deleted, :cid_actor)"
                ),
                {**mm, "cid": clan_a, "cid_actor": admin_a},
            )

        parent_child_edges = [
            {"parent_id": founder, "child_id": con_truong, "relationship_type": "biological"},
            {"parent_id": con_truong, "child_id": chau_a, "relationship_type": "biological"},
            {"parent_id": vo_ca, "child_id": chau_a, "relationship_type": "biological"},
            {"parent_id": con_truong, "child_id": chau_b, "relationship_type": "adopted"},
        ]
        for pc in parent_child_edges:
            await s.execute(
                sa.text(
                    "INSERT INTO parent_child "
                    "(id, parent_id, child_id, created_by_clan_id, relationship_type, created_by) "
                    "VALUES (:id, :parent_id, :child_id, :cid, :relationship_type, :cid_actor)"
                ),
                {**pc, "id": uuid.uuid4(), "cid": clan_a, "cid_actor": admin_a},
            )

        await s.commit()

    admin_headers = {
        "Authorization": f"Bearer {admin_a}",
        "X-Current-Clan-Id": str(clan_a),
    }

    resp = await client.post(
        "/api/v1/documents",
        headers=admin_headers,
        data={"title": "Gia phả", "document_type": "certificate"},
        files={"file": ("giapha.png", _PNG_BYTES, "image/png")},
    )
    assert resp.status_code == 201, resp.text

    return {
        "clan_a": clan_a,
        "clan_b": clan_b,
        "admin_a": admin_a,
        "editor_a": editor_a,
        "admin_b": admin_b,
    }


@pytest.fixture()
def admin_headers(rich_clan: dict[str, Any]) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {rich_clan['admin_a']}",
        "X-Current-Clan-Id": str(rich_clan["clan_a"]),
    }


async def test_gedcom_export_closes_the_501_stub(client, admin_headers, rich_clan):
    """The core regression test: `fmt="gedcom"` used to raise
    `NotImplementedError` (500). It must now return 200."""
    resp = await client.get("/api/v1/exports/clan?format=gedcom", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/x-gedcom")
    content_disposition = resp.headers["content-disposition"]
    assert 'attachment; filename="' in content_disposition
    assert content_disposition.rstrip('"').endswith(".ged")


async def test_gedcom_export_body_shape(client, admin_headers, rich_clan):
    resp = await client.get("/api/v1/exports/clan?format=gedcom", headers=admin_headers)
    assert resp.status_code == 200
    text = resp.text
    assert text.startswith("0 HEAD")
    assert text.rstrip().endswith("0 TRLR")

    # Exactly 6 live persons (thủy tổ, con trưởng, vợ cả, vợ hai, cháu A,
    # cháu B) — the soft-deleted person is excluded from GEDCOM entirely.
    assert len(re.findall(r"^0 @I\d+@ INDI$", text, flags=re.MULTILINE)) == 6
    assert "Người Đã Xóa" not in text

    # Cháu A's `birth_date` is NULL with only a display string set (FIX 2):
    # the export must still emit BIRT with a NOTE fallback, not drop it.
    assert "1 BIRT\n2 NOTE khoảng 1975" in text

    # Cháu A carries `doi=` (generation) in her Vietnamese metadata NOTE.
    assert re.search(r"1 NOTE FamilyRoots:.*doi=3", text)
