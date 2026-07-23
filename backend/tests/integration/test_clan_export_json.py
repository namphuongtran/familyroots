"""Lossless JSON archive: everything a clan needs to survive outside the SaaS.

Real Postgres (migrated_db_url), real RBAC. Only JWT *verification* is stubbed
(mirrors tests/integration/test_document_soft_delete.py) — the Authorization
header carries the user id directly instead of a signed token. The storage
adapter is swapped for the same in-memory FakeStorage used by the document
soft-delete tests (via dependency_overrides), both for the real multipart
document upload and for the export's presigning, so these tests never hit real
Supabase Storage and the manifest's `download_url` is deterministic.
"""

from __future__ import annotations

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
    """In-memory StoragePort double — mirrors test_document_soft_delete.FakeStorage
    so both the upload path and the export's presigning are deterministic and
    never touch real Supabase Storage."""

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
    1 soft-deleted person, 1 soft-deleted marriage, 1 branch, 1 lunar recurring
    event, plus a real uploaded document. Also seeds a second clan (minimal)
    for the isolation test."""
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

        # joined_at set explicitly (not left NULL) — the export's
        # clan_memberships archive must be lossless, and generation_map's
        # founder-ordering tiebreak depends on it being populated.
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

        # Marriages: đa thê (con_truong + vợ cả spouse_order=1, + vợ hai
        # spouse_order=2), plus one soft-deleted marriage.
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

        # Parent-child: founder -> con_truong -> {cháu A (bio, mẹ = vợ cả), cháu
        # B (adopted)}.
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

        # Event: giỗ (lunar, recurring).
        await s.execute(
            sa.text(
                "INSERT INTO events "
                "(id, clan_id, person_id, event_type, title, event_date, "
                "is_lunar_calendar, is_recurring, created_by) "
                "VALUES (:id, :cid, :pid, 'death_anniversary', 'Giỗ Cụ Thủy Tổ', "
                ":event_date, true, true, :cid_actor)"
            ),
            {
                "id": uuid.uuid4(),
                "cid": clan_a,
                "pid": founder,
                "event_date": date(1990, 6, 1),
                "cid_actor": admin_a,
            },
        )

        await s.commit()

    admin_headers = {
        "Authorization": f"Bearer {admin_a}",
        "X-Current-Clan-Id": str(clan_a),
    }

    # A real document, uploaded via the API multipart endpoint (so the export's
    # manifest presigns a real storage_path).
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


@pytest.fixture()
def editor_headers(rich_clan: dict[str, Any]) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {rich_clan['editor_a']}",
        "X-Current-Clan-Id": str(rich_clan["clan_a"]),
    }


@pytest.fixture()
def clan_b_admin_headers(rich_clan: dict[str, Any]) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {rich_clan['admin_b']}",
        "X-Current-Clan-Id": str(rich_clan["clan_b"]),
    }


# ── Tests (verbatim per the task-4 brief) ────────────────────────────────────


async def test_json_export_contains_everything(client, admin_headers, rich_clan):
    resp = await client.get("/api/v1/exports/clan?format=json", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    assert 'attachment; filename="' in resp.headers["content-disposition"]
    data = resp.json()  # the archive itself, NOT {"data": ...} — envelope-exempt
    assert data["format"] == "familyroots-clan-export" and data["format_version"] == 1
    persons = {p["full_name"]: p for p in data["persons"]}
    assert persons["Cụ Thủy Tổ"]["generation"] == 1
    assert persons["Cháu A"]["generation"] == 3
    assert persons["Cháu A"]["birth_date_precision"] == "circa"
    assert persons["Cháu A"]["birth_date_display"] == "khoảng 1975"
    assert persons["Cụ Thủy Tổ"]["lunar_birth_date"] == "15/08 Canh Thân"
    deleted = [p for p in data["persons"] if p["is_deleted"]]
    assert len(deleted) == 1  # archive keeps history, flagged
    orders = sorted(
        m["spouse_order"] for m in data["marriages"] if m["spouse_order"] and not m["is_deleted"]
    )
    assert orders == [1, 2]
    assert any(pc["relationship_type"] == "adopted" for pc in data["parent_child"])
    assert any(m["is_deleted"] for m in data["marriages"])
    assert any(e["is_lunar_calendar"] for e in data["events"])
    assert data["branches"][0]["name"] == "Chi Hai"
    manifest = data["documents_manifest"]
    assert len(manifest) == 1 and manifest[0]["download_url"].startswith("http")


async def test_export_isolation_two_sided(client, admin_headers, clan_b_admin_headers, rich_clan):
    a = (await client.get("/api/v1/exports/clan?format=json", headers=admin_headers)).json()
    b = (await client.get("/api/v1/exports/clan?format=json", headers=clan_b_admin_headers)).json()
    a_ids = {p["id"] for p in a["persons"]}
    b_ids = {p["id"] for p in b["persons"]}
    assert a_ids and not (a_ids & b_ids)


async def test_export_requires_admin(client, editor_headers, rich_clan):
    resp = await client.get("/api/v1/exports/clan?format=json", headers=editor_headers)
    assert resp.status_code == 403


async def test_export_invalid_format_422(client, admin_headers, rich_clan):
    resp = await client.get("/api/v1/exports/clan?format=xml", headers=admin_headers)
    assert resp.status_code == 422


# ── Task-4 review fixes ──────────────────────────────────────────────────────


async def test_json_export_clan_memberships_lossless_and_complete(client, admin_headers, rich_clan):
    """FIX 2/3 (task-4 review): clan_memberships must be lossless (carry
    membership_id/joined_at/created_at/updated_at, not just role/generation/
    founder/branch) and every archived person must have exactly one
    membership row, with the thủy tổ correctly flagged as founder."""
    resp = await client.get("/api/v1/exports/clan?format=json", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()

    persons_by_name = {p["full_name"]: p for p in data["persons"]}
    memberships_by_person = {m["person_id"]: m for m in data["clan_memberships"]}

    # Every person id appears in memberships exactly once.
    person_ids = [p["id"] for p in data["persons"]]
    assert len(person_ids) == len(set(person_ids))
    assert set(person_ids) == set(memberships_by_person.keys())
    assert len(data["clan_memberships"]) == len(data["persons"])

    founder_membership = memberships_by_person[persons_by_name["Cụ Thủy Tổ"]["id"]]
    assert founder_membership["is_founder"] is True
    assert founder_membership["role"] == "blood"

    for membership in data["clan_memberships"]:
        assert set(membership.keys()) == {
            "membership_id",
            "person_id",
            "role",
            "stored_generation",
            "is_founder",
            "branch_id",
            "joined_at",
            "created_at",
            "updated_at",
        }
        assert membership["membership_id"] is not None
        # Seeded explicitly in the rich_clan fixture — must survive the export.
        assert membership["joined_at"] is not None
        assert membership["created_at"] is not None
        assert membership["updated_at"] is not None


async def test_generation_map_deterministic_with_single_founder(
    session_factory,
):
    """Pins generation_map's founder-anchored walk with a SINGLE live founder.

    Multi-founder states are structurally impossible since migration 023
    (ADR-026): `uq_clan_memberships_one_founder` is an immediate partial
    unique index enforcing at most one `is_founder = true` row per clan. The
    export's ordered multi-founder walk (`ORDER BY joined_at, person_id` over
    `is_founder = true` rows, first founder processed wins a shared
    descendant) is retained in `SqlAlchemyExportQueryPort.generation_map` as
    tolerance for pre-023 archives/robustness, but that scenario can no
    longer be exercised against a live schema — a raw-SQL seed of a second
    `is_founder = true` row now itself raises `IntegrityError` on the unique
    index (sabotage-verified in Task 2). This test pins the single-founder
    behavior instead: the founder's own generation anchors at 1 (thủy tổ),
    and each descendant's generation is `depth + 1` along the founder's walk,
    reproducibly across independent computations of the same live schema.

    founder -> mid -> shared_descendant (depth 1, depth 2).
    """
    import sqlalchemy as sa

    from app.infrastructure.persistence.export_query_port import SqlAlchemyExportQueryPort

    clan_id = uuid.uuid4()
    admin_id = uuid.uuid4()
    founder = uuid.uuid4()
    mid = uuid.uuid4()
    shared_descendant = uuid.uuid4()

    async with session_factory() as s:
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'Họ Một Tổ', :slug)"),
            {"id": clan_id, "slug": f"ho-mot-to-{clan_id.hex[:8]}"},
        )
        await s.execute(
            sa.text(
                "INSERT INTO user_profiles (id, email, display_name) VALUES (:id, :email, 'admin')"
            ),
            {"id": admin_id, "email": f"{admin_id.hex[:8]}@example.com"},
        )
        for pid, name in (
            (founder, "Thủy Tổ"),
            (mid, "Đời Giữa"),
            (shared_descendant, "Hậu Duệ"),
        ):
            await s.execute(
                sa.text(
                    "INSERT INTO persons "
                    "(id, full_name, gender, birth_date, birth_date_precision, "
                    "birth_date_display, lunar_birth_date, is_deleted, "
                    "created_by_clan_id, created_by) "
                    "VALUES (:id, :full_name, 'unknown', NULL, 'unknown', "
                    "NULL, NULL, false, :cid, :cid_actor)"
                ),
                {"id": pid, "full_name": name, "cid": clan_id, "cid_actor": admin_id},
            )

        await s.execute(
            sa.text(
                "INSERT INTO clan_memberships (person_id, clan_id, is_founder, joined_at) "
                "VALUES (:pid, :cid, true, :joined_at)"
            ),
            {
                "pid": founder,
                "cid": clan_id,
                "joined_at": datetime(2000, 1, 1, tzinfo=UTC),
            },
        )
        for pid in (mid, shared_descendant):
            await s.execute(
                sa.text(
                    "INSERT INTO clan_memberships (person_id, clan_id, is_founder) "
                    "VALUES (:pid, :cid, false)"
                ),
                {"pid": pid, "cid": clan_id},
            )

        for parent_id, child_id in (
            (founder, mid),
            (mid, shared_descendant),
        ):
            await s.execute(
                sa.text(
                    "INSERT INTO parent_child "
                    "(id, parent_id, child_id, created_by_clan_id, relationship_type, created_by) "
                    "VALUES (:id, :parent_id, :child_id, :cid, 'biological', :cid_actor)"
                ),
                {
                    "id": uuid.uuid4(),
                    "parent_id": parent_id,
                    "child_id": child_id,
                    "cid": clan_id,
                    "cid_actor": admin_id,
                },
            )
        await s.commit()

    async with session_factory() as s:
        port = SqlAlchemyExportQueryPort(s)
        first_run = await port.generation_map(clan_id)
    async with session_factory() as s:
        port = SqlAlchemyExportQueryPort(s)
        second_run = await port.generation_map(clan_id)

    assert first_run == second_run
    # Founder anchors at generation 1 (thủy tổ); descendants are depth + 1
    # along the founder's own walk.
    assert first_run[founder] == 1
    assert first_run[mid] == 2
    assert first_run[shared_descendant] == 3
