"""A clan admin anonymises a person: the identity goes, the node and its edges stay (#333).

Read over HTTP against the real app and a real Postgres. Each assertion reads the
**outcome**: the response body, the row as stored, the tree a client is served, and
the audit trail. None of them asks whether a method ran (``.claude/rules/testing.md``).

The đời reading is the one the issue names as its negative control. Before the
anonymisation the grandchild sits at đời 3 under the founder; after it, still at đời 3
under the same chain. Planting an edge soft-delete in the anonymise path (an
"anonymise by deleting relationships" implementation) detaches the grandchild from the
founder, and ``test_the_tree_keeps_its_shape_and_doi`` fails on its đời reading.

Only JWT verification is stubbed, the same way ``test_person_pii_over_http.py`` does
it. ``get_db`` points at a plain privileged session, so this file is not evidence about
RLS; the route is clan-scoped through ``get_current_clan_id`` like every other person
write.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator
from datetime import date
from typing import Any, ClassVar

import pytest
import sqlalchemy as sa
from fastapi import Header
from httpx2 import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.core.security import get_current_user
from app.main import create_app

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

ANONYMISED_NAME = "Đã ẩn danh"

# Every value below is a secret the anonymisation must remove from the stored row.
SECRET_VALUES = {
    "full_name": "Nguyễn Văn Bímật",
    "birth_name": "Tên Khaisinh Bímật",
    "courtesy_name": "Tự Bímật",
    "posthumous_name": "Húy Bímật",
    "alias_name": "Biệtdanh Bímật",
    "birth_place": "Làng Bímật",
    "death_place": "Phủ Bímật",
    "burial_place": "Nghĩa trang Bímật",
    "tomb_location": "Lô Bímật",
    "residence_place": "Phố Bímật",
    "biography": "Tiểu sử Bímật",
    "notes": "Ghi chú Bímật",
    "occupation": "Nghề Bímật",
    "phone": "0900333333",
    "email": "bimat-333@example.com",
    "lunar_birth_date": "15/08 Bímật",
    "lunar_death_date": "01/01 Bímật",
    "birth_date_display": "khoảng Bímật",
}
SECRET_MARKERS = ("Bímật", "0900333333", "bimat-333")
AVATAR = "https://cdn.example.com/avatars/bimat-333.jpg"


async def _override_current_user(
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    assert authorization is not None, "test client must send an Authorization header"
    return {"sub": authorization.removeprefix("Bearer ")}


class _RecordingStorage:
    """Stands in for the Supabase storage adapter: records the public objects the
    anonymisation takes down, and nothing else."""

    deleted_public: ClassVar[list[str]] = []

    async def delete_public(self, path: str) -> None:
        type(self).deleted_public.append(path)


@pytest.fixture()
async def session_factory(
    migrated_db_url: str,
) -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(migrated_db_url)
    yield async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    await engine.dispose()


async def _person(s: AsyncSession, clan_id: uuid.UUID, creator: uuid.UUID, name: str) -> uuid.UUID:
    pid = uuid.uuid4()
    await s.execute(
        sa.text(
            "INSERT INTO persons (id, full_name, gender, created_by_clan_id, created_by) "
            "VALUES (:id, :n, 'male', :c, :cb)"
        ),
        {"id": pid, "n": name, "c": clan_id, "cb": creator},
    )
    return pid


@pytest.fixture()
async def seeded(session_factory: async_sessionmaker[AsyncSession]) -> dict[str, Any]:
    """Founder → father (the person to anonymise) → grandchild, plus the father's wife.

    The father carries a value in every field the anonymisation must clear, and an
    avatar. Two callers: an admin and an editor of the same clan. A second clan holds
    a person the first clan's admin must not reach."""
    clan_id, other_clan = uuid.uuid4(), uuid.uuid4()
    admin_id, editor_id = uuid.uuid4(), uuid.uuid4()

    async with session_factory() as s:
        for cid in (clan_id, other_clan):
            await s.execute(
                sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'Họ A333', :slug)"),
                {"id": cid, "slug": f"a333-{cid.hex[:10]}"},
            )
        founder = await _person(s, clan_id, admin_id, "Thủy Tổ")
        father = await _person(s, clan_id, admin_id, SECRET_VALUES["full_name"])
        wife = await _person(s, clan_id, admin_id, "Vợ")
        grandchild = await _person(s, clan_id, admin_id, "Cháu")
        outsider = await _person(s, other_clan, admin_id, "Người họ khác")

        sets = ", ".join(f"{k} = :{k}" for k in SECRET_VALUES)
        await s.execute(
            sa.text(
                f"UPDATE persons SET {sets}, birth_date = :bd, death_date = :dd, "
                "birth_date_precision = 'circa', avatar_url = :av WHERE id = :id"
            ),
            {
                **SECRET_VALUES,
                "bd": date(1901, 2, 3),
                "dd": date(1970, 4, 5),
                "av": AVATAR,
                "id": father,
            },
        )
        for pid, cid, is_founder in (
            (founder, clan_id, True),
            (father, clan_id, False),
            (wife, clan_id, False),
            (grandchild, clan_id, False),
            (outsider, other_clan, False),
        ):
            await s.execute(
                sa.text(
                    "INSERT INTO clan_memberships (person_id, clan_id, is_founder) "
                    "VALUES (:p, :c, :f)"
                ),
                {"p": pid, "c": cid, "f": is_founder},
            )
        for parent, child in ((founder, father), (father, grandchild)):
            await s.execute(
                sa.text(
                    "INSERT INTO parent_child "
                    "(id, parent_id, child_id, created_by_clan_id, relationship_type, created_by)"
                    " VALUES (:id, :p, :c, :cl, 'biological', :cb)"
                ),
                {"id": uuid.uuid4(), "p": parent, "c": child, "cl": clan_id, "cb": admin_id},
            )
        await s.execute(
            sa.text(
                "INSERT INTO marriages "
                "(id, person1_id, person2_id, created_by_clan_id, status, spouse_order, "
                "created_by) VALUES (:id, :p1, :p2, :c, 'married', 1, :cb)"
            ),
            {"id": uuid.uuid4(), "p1": father, "p2": wife, "c": clan_id, "cb": admin_id},
        )
        for uid, role in ((admin_id, "admin"), (editor_id, "editor")):
            await s.execute(
                sa.text("INSERT INTO user_profiles (id, email, display_name) VALUES (:id, :e, :d)"),
                {"id": uid, "e": f"{uid.hex[:10]}@example.com", "d": role},
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

    return {
        "clan_id": clan_id,
        "admin_id": admin_id,
        "editor_id": editor_id,
        "founder": founder,
        "father": father,
        "wife": wife,
        "grandchild": grandchild,
        "outsider": outsider,
    }


@pytest.fixture()
async def client(
    session_factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> AsyncGenerator[AsyncClient]:
    _RecordingStorage.deleted_public = []
    monkeypatch.setattr("app.infrastructure.dependencies.SupabaseStorageAdapter", _RecordingStorage)
    app = create_app()

    async def _override_db() -> AsyncGenerator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_current_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


def _headers(seeded: dict[str, Any], caller: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {seeded[caller]}",
        "X-Current-Clan-Id": str(seeded["clan_id"]),
    }


def _find(node: dict[str, Any], person_id: uuid.UUID) -> dict[str, Any] | None:
    if node.get("id") == str(person_id):
        return node
    for child in node.get("children", []):
        found = _find(child, person_id)
        if found is not None:
            return found
    return None


def _doi_chain(tree: dict[str, Any], seeded: dict[str, Any]) -> list[tuple[str, int | None]]:
    """(name, đời) for founder → father → grandchild, each found UNDER the previous one."""
    chain: list[tuple[str, int | None]] = []
    node: dict[str, Any] | None = tree
    for key in ("founder", "father", "grandchild"):
        assert node is not None, f"{key} is not reachable from the founder"
        node = _find(node, seeded[key])
        assert node is not None, f"{key} is not reachable from the founder"
        chain.append((node["full_name"], node["generation"]))
    return chain


async def _anonymise(client: AsyncClient, seeded: dict[str, Any], who: str, target: str) -> Any:
    return await client.post(
        f"/api/v1/persons/{seeded[target]}/anonymise", headers=_headers(seeded, who)
    )


async def test_admin_anonymise_clears_every_identifying_field(
    client: AsyncClient,
    seeded: dict[str, Any],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    resp = await _anonymise(client, seeded, "admin_id", "father")
    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert body["id"] == str(seeded["father"])
    assert body["full_name"] == ANONYMISED_NAME
    for name_field in ("birth_name", "courtesy_name", "posthumous_name", "alias_name"):
        assert body[name_field] is None, name_field
    assert body["birth_date"]["date"] is None
    assert body["birth_date"]["precision"] == "unknown"
    assert body["birth_date"]["display"] is None
    assert body["birth_date"]["lunar"] is None
    assert body["death_date"]["date"] is None
    assert body["death_date"]["lunar"] is None
    assert body["avatar_url"] is None
    assert body["gender"] == "male"  # kept: con theo đời cha reads it

    # The stored row, read back raw: no secret survives anywhere in it.
    async with session_factory() as s:
        row = (
            await s.execute(
                sa.text("SELECT row_to_json(p)::text FROM persons p WHERE id = :id"),
                {"id": seeded["father"]},
            )
        ).scalar_one()
    assert not [m for m in SECRET_MARKERS if m in row], row
    assert AVATAR not in row
    stored = json.loads(row)
    assert stored["full_name"] == ANONYMISED_NAME
    assert stored["birth_date"] is None and stored["death_date"] is None
    assert stored["is_deleted"] is False  # anonymised, not deleted

    # The public avatar object was taken down, at the clan's avatar path.
    assert _RecordingStorage.deleted_public == [
        f"clans/{seeded['clan_id']}/avatars/{seeded['father']}"
    ]


async def test_the_tree_keeps_its_shape_and_doi(
    client: AsyncClient, seeded: dict[str, Any]
) -> None:
    before = await client.get("/api/v1/tree", headers=_headers(seeded, "admin_id"))
    assert before.status_code == 200, before.text
    assert [g for _, g in _doi_chain(before.json()["data"]["tree"], seeded)] == [1, 2, 3]

    resp = await _anonymise(client, seeded, "admin_id", "father")
    assert resp.status_code == 200, resp.text

    after = await client.get("/api/v1/tree", headers=_headers(seeded, "admin_id"))
    assert after.status_code == 200, after.text
    assert _doi_chain(after.json()["data"]["tree"], seeded) == [
        ("Thủy Tổ", 1),
        (ANONYMISED_NAME, 2),
        ("Cháu", 3),
    ]

    # The edges themselves are still served for the anonymised node.
    links = await client.get(
        f"/api/v1/persons/{seeded['father']}/parent-child", headers=_headers(seeded, "admin_id")
    )
    assert links.status_code == 200, links.text
    pairs = {(link["parent_id"], link["child_id"]) for link in links.json()["data"]}
    assert pairs == {
        (str(seeded["founder"]), str(seeded["father"])),
        (str(seeded["father"]), str(seeded["grandchild"])),
    }
    marriages = await client.get(
        f"/api/v1/persons/{seeded['father']}/marriages", headers=_headers(seeded, "admin_id")
    )
    assert marriages.status_code == 200, marriages.text
    assert len(marriages.json()["data"]) == 1


async def test_the_audit_row_names_the_action_but_not_the_old_values(
    client: AsyncClient,
    seeded: dict[str, Any],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    resp = await _anonymise(client, seeded, "admin_id", "father")
    assert resp.status_code == 200, resp.text

    async with session_factory() as s:
        rows = (
            await s.execute(
                sa.text(
                    "SELECT action, clan_id, actor_id, old_value::text, new_value::text "
                    "FROM audit_logs WHERE resource_id = :id"
                ),
                {"id": seeded["father"]},
            )
        ).all()
    assert [r.action for r in rows] == ["person.anonymise"]
    (row,) = rows
    assert row.clan_id == seeded["clan_id"]
    assert row.actor_id == seeded["admin_id"]
    dumped = f"{row.old_value} {row.new_value}"
    assert not [m for m in SECRET_MARKERS if m in dumped], dumped
    assert "courtesy_name" in (row.new_value or "")  # it lists what was cleared


async def test_an_editor_cannot_anonymise(
    client: AsyncClient,
    seeded: dict[str, Any],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    resp = await _anonymise(client, seeded, "editor_id", "father")
    assert resp.status_code == 403, resp.text
    async with session_factory() as s:
        name = await s.scalar(
            sa.text("SELECT full_name FROM persons WHERE id = :id"), {"id": seeded["father"]}
        )
    assert name == SECRET_VALUES["full_name"]


async def test_a_person_of_another_clan_is_not_found(
    client: AsyncClient,
    seeded: dict[str, Any],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    resp = await _anonymise(client, seeded, "admin_id", "outsider")
    assert resp.status_code == 404, resp.text
    async with session_factory() as s:
        name = await s.scalar(
            sa.text("SELECT full_name FROM persons WHERE id = :id"), {"id": seeded["outsider"]}
        )
    assert name == "Người họ khác"
