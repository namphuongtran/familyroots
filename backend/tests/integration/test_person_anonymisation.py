"""``POST /api/v1/persons/{id}/anonymise`` — erase a person, keep the tree (ADR-079, #333).

The family is ADR-027's H4 family, chosen because two different mistakes each move a
descendant's đời in it, so a test on it can fail for either:

    F (male, founder, đời 1)
    ├─ S (male, đời 2)
    │   └─ GS (male, đời 3)   ← the person anonymised
    └─ D (female, đời 2)
    GS + D → C. Con theo đời cha: đời(C) = đời(GS) + 1 = 4.

Through D alone C would be đời 3. So if anonymisation drops GS's edges, C's canonical
parent becomes D and C reads 3; and if it clears GS's gender, GS ranks below the mother
(father > mother > unknown) and C reads 3 again. Gender and edges are both kept on
purpose, and this file is what says so.

Read as outcomes: the ``/tree`` response a client gets, the stored row read on a
privileged connection, and the audit row. Wiring is production's: ``get_db`` is a real
``RlsSession`` and the clan header goes through the real ``get_current_clan_id`` and
``RequireAdmin``; only JWT verification is replaced.

Negative controls run 2026-11-21, each seen to fail and then reverted (the issue's own
control is the first):

- the handler also soft-deleting every ``parent_child`` row of the person, i.e.
  anonymising without keeping relationships: the đời-map assertion fails, C reading
  ``3 != 4`` and GS's node gone from the tree.
- ``Person.anonymise`` also setting ``gender = "unknown"``: the same assertion fails, C
  reading ``3 != 4`` with every edge still in place.
- ``"biography"`` dropped from ``_ANONYMISED_TO_NONE``: the stored-row assertion fails,
  ``{'biography': 'Tiểu sử riêng tư của ông Ẩn'} != {'biography': None}``.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, Generator
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi import Header
from httpx2 import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.database import RlsSession, get_db, get_system_db
from app.core.rls import set_request_clan_id
from app.core.security import get_current_user
from app.domain.person.entity import ANONYMISED_NAME
from app.main import create_app

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

GS_NAME = "Nguyễn Văn Ẩn"
GS_BIRTH_NAME = "Tên Húy Ẩn"
GS_COURTESY = "Tên Tự Ẩn"
GS_POSTHUMOUS = "Tên Thụy Ẩn"
GS_BIO = "Tiểu sử riêng tư của ông Ẩn"
GS_PLACE = "Làng Ẩn Danh, Hà Nam"


@pytest.fixture()
async def engine(migrated_db_url: str) -> AsyncGenerator[AsyncEngine]:
    eng = create_async_engine(migrated_db_url)
    yield eng
    await eng.dispose()


@pytest.fixture(autouse=True)
def _reset_clan_context() -> Generator[None]:
    set_request_clan_id(None)
    yield
    set_request_clan_id(None)


@pytest.fixture()
async def http(engine: AsyncEngine) -> AsyncGenerator[AsyncClient]:
    rls_factory = async_sessionmaker(
        engine, sync_session_class=RlsSession, expire_on_commit=False, class_=AsyncSession
    )
    system_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    app = create_app()

    async def _override_db() -> AsyncGenerator[AsyncSession]:
        async with rls_factory() as session:
            yield session

    async def _override_system_db() -> AsyncGenerator[AsyncSession]:
        async with system_factory() as session:
            yield session

    async def _override_current_user(
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        assert authorization is not None, "test client must send an Authorization header"
        return {"sub": authorization.removeprefix("Bearer ")}

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_system_db] = _override_system_db
    app.dependency_overrides[get_current_user] = _override_current_user

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


async def _seed(engine: AsyncEngine) -> dict[str, uuid.UUID]:
    """The H4 family in one clan, plus an admin and an editor."""
    ids = {k: uuid.uuid4() for k in ("clan", "admin", "editor", "f", "s", "gs", "d", "c")}
    clan = ids["clan"]
    async with engine.begin() as conn:
        await conn.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'Họ Ẩn', :s)"),
            {"id": clan, "s": f"anon-{clan.hex[:10]}"},
        )
        for key, role in (("admin", "admin"), ("editor", "editor")):
            await conn.execute(
                sa.text("INSERT INTO user_profiles (id, email) VALUES (:id, :e)"),
                {"id": ids[key], "e": f"{key}-{ids[key].hex[:10]}@example.com"},
            )
            await conn.execute(
                sa.text(
                    "INSERT INTO user_clan_roles "
                    "(clan_id, user_id, role, is_approved, approved_by, approved_at) "
                    "VALUES (:c, :u, :r, true, :u, now())"
                ),
                {"c": clan, "u": ids[key], "r": role},
            )
        for key, name, gender in (
            ("f", "Thủy Tổ", "male"),
            ("s", "Con Trai", "male"),
            ("d", "Con Gái", "female"),
            ("c", "Chắt", "male"),
        ):
            await conn.execute(
                sa.text(
                    "INSERT INTO persons (id, full_name, gender, created_by_clan_id, created_by) "
                    "VALUES (:id, :n, :g, :c, :cb)"
                ),
                {"id": ids[key], "n": name, "g": gender, "c": clan, "cb": ids["admin"]},
            )
        await conn.execute(
            sa.text(
                "INSERT INTO persons (id, full_name, birth_name, courtesy_name, posthumous_name, "
                "alias_name, gender, birth_date, birth_date_precision, death_date, "
                "death_date_precision, lunar_death_date, birth_place, burial_place, "
                "biography, notes, phone, email, avatar_url, created_by_clan_id, created_by) "
                "VALUES (:id, :n, :bn, :cn, :pn, 'Ông Ẩn', 'male', '1900-01-02', 'exact', "
                "'1970-03-04', 'exact', '15/08 Canh Tuất', :pl, :pl, :bio, 'ghi chú', "
                "'0900000333', 'an@example.com', 'https://cdn.example.com/a.jpg', :c, :cb)"
            ),
            {
                "id": ids["gs"],
                "n": GS_NAME,
                "bn": GS_BIRTH_NAME,
                "cn": GS_COURTESY,
                "pn": GS_POSTHUMOUS,
                "pl": GS_PLACE,
                "bio": GS_BIO,
                "c": clan,
                "cb": ids["admin"],
            },
        )
        for key in ("f", "s", "gs", "d", "c"):
            await conn.execute(
                sa.text(
                    "INSERT INTO clan_memberships (person_id, clan_id, is_founder) "
                    "VALUES (:p, :c, :f)"
                ),
                {"p": ids[key], "c": clan, "f": key == "f"},
            )
        for parent, child in (("f", "s"), ("s", "gs"), ("f", "d"), ("gs", "c"), ("d", "c")):
            await conn.execute(
                sa.text(
                    "INSERT INTO parent_child (id, parent_id, child_id, created_by_clan_id, "
                    "relationship_type, created_by) VALUES (:id, :p, :ch, :c, 'biological', :cb)"
                ),
                {
                    "id": uuid.uuid4(),
                    "p": ids[parent],
                    "ch": ids[child],
                    "c": clan,
                    "cb": ids["admin"],
                },
            )
        await conn.execute(
            sa.text(
                "INSERT INTO marriages (id, person1_id, person2_id, created_by_clan_id, status, "
                "spouse_order, created_by) VALUES (:id, :a, :b, :c, 'married', 1, :cb)"
            ),
            {"id": uuid.uuid4(), "a": ids["gs"], "b": ids["d"], "c": clan, "cb": ids["admin"]},
        )
    return ids


def _headers(user: uuid.UUID, clan: uuid.UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {user}", "X-Current-Clan-Id": str(clan)}


def _generations(tree: dict[str, Any]) -> dict[str, tuple[int | None, str]]:
    """Every full (non-stub) node of a ``/tree`` response: id → (đời, full_name)."""
    out: dict[str, tuple[int | None, str]] = {}

    def walk(node: dict[str, Any]) -> None:
        if not node.get("pedigree_collapse_ref"):
            out[node["id"]] = (node["generation"], node["full_name"])
        for child in node.get("children", []):
            walk(child)

    walk(tree)
    return out


async def _tree(http: AsyncClient, ids: dict[str, uuid.UUID]) -> dict[str, tuple[int | None, str]]:
    resp = await http.get("/api/v1/tree", headers=_headers(ids["admin"], ids["clan"]))
    assert resp.status_code == 200, resp.text
    return _generations(resp.json()["data"]["tree"])


async def test_anonymising_keeps_the_node_its_edges_and_every_doi(
    engine: AsyncEngine, http: AsyncClient
) -> None:
    ids = await _seed(engine)
    before = await _tree(http, ids)
    # The premise, so a later 4 is evidence: C is đời 4 through GS, and GS is named.
    assert before[str(ids["c"])][0] == 4
    assert before[str(ids["gs"])] == (3, GS_NAME)

    resp = await http.post(
        f"/api/v1/persons/{ids['gs']}/anonymise", headers=_headers(ids["admin"], ids["clan"])
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert body["full_name"] == ANONYMISED_NAME
    assert body["birth_date"] == {
        "date": None,
        "precision": "unknown",
        "display": None,
        "lunar": None,
    }
    assert body["death_date"] == {
        "date": None,
        "precision": "unknown",
        "display": None,
        "lunar": None,
    }

    after = await _tree(http, ids)
    # Same node set, same đời for every node, and only GS's name changed.
    assert {k: v[0] for k, v in after.items()} == {k: v[0] for k, v in before.items()}
    assert after[str(ids["c"])][0] == 4
    assert after[str(ids["gs"])] == (3, ANONYMISED_NAME)

    async with engine.connect() as conn:
        row = (
            (await conn.execute(sa.text("SELECT * FROM persons WHERE id = :id"), {"id": ids["gs"]}))
            .mappings()
            .one()
        )
        live_edges = (
            await conn.execute(
                sa.text(
                    "SELECT (SELECT count(*) FROM parent_child WHERE NOT is_deleted "
                    "AND (parent_id = :id OR child_id = :id)) + (SELECT count(*) FROM "
                    "marriages WHERE NOT is_deleted AND (person1_id = :id OR person2_id = :id))"
                ),
                {"id": ids["gs"]},
            )
        ).scalar_one()

    assert row["full_name"] == ANONYMISED_NAME
    assert row["gender"] == "male"
    assert row["is_deleted"] is False
    cleared = (
        "birth_name", "courtesy_name", "posthumous_name", "alias_name", "birth_date",
        "death_date", "birth_date_display", "death_date_display", "lunar_birth_date",
        "lunar_death_date", "birth_place", "death_place", "burial_place", "tomb_location",
        "residence_place", "biography", "notes", "phone", "email", "avatar_url",
    )  # fmt: skip
    assert {f: row[f] for f in cleared} == dict.fromkeys(cleared)
    assert (row["birth_date_precision"], row["death_date_precision"]) == ("unknown", "unknown")
    assert live_edges == 3  # S→GS, GS→C, and the marriage GS+D

    async with engine.connect() as conn:
        audit = (
            await conn.execute(
                sa.text(
                    "SELECT actor_id, clan_id, old_value, new_value::text AS nv FROM audit_logs "
                    "WHERE action = 'person.anonymise' AND resource_id = :id"
                ),
                {"id": ids["gs"]},
            )
        ).one()
    assert (audit.actor_id, audit.clan_id, audit.old_value) == (ids["admin"], ids["clan"], None)
    for erased in (GS_NAME, GS_BIRTH_NAME, GS_COURTESY, GS_POSTHUMOUS, GS_BIO, GS_PLACE):
        assert erased not in audit.nv
    assert '"biography"' in audit.nv


async def test_an_editor_may_not_anonymise(engine: AsyncEngine, http: AsyncClient) -> None:
    ids = await _seed(engine)

    resp = await http.post(
        f"/api/v1/persons/{ids['gs']}/anonymise", headers=_headers(ids["editor"], ids["clan"])
    )

    assert resp.status_code == 403, resp.text
    async with engine.connect() as conn:
        name = (
            await conn.execute(
                sa.text("SELECT full_name FROM persons WHERE id = :id"), {"id": ids["gs"]}
            )
        ).scalar_one()
    assert name == GS_NAME


async def test_a_person_of_another_clan_is_not_found(
    engine: AsyncEngine, http: AsyncClient
) -> None:
    """Clan isolation: an admin of clan B cannot anonymise clan A's person by id."""
    a, b = await _seed(engine), await _seed(engine)

    resp = await http.post(
        f"/api/v1/persons/{a['gs']}/anonymise", headers=_headers(b["admin"], b["clan"])
    )

    assert resp.status_code == 404, resp.text
    async with engine.connect() as conn:
        name = (
            await conn.execute(
                sa.text("SELECT full_name FROM persons WHERE id = :id"), {"id": a["gs"]}
            )
        ).scalar_one()
    assert name == GS_NAME
