"""H2: PATCH must not bypass create-time rules. M3: spouse_order 409.

Real Postgres (migrated_db_url), real RBAC, real Relationship aggregates +
repositories. Only JWT *verification* is stubbed (mirrors
tests/integration/test_occ_relationships.py) — the Authorization header carries
the user id directly instead of a signed token, so these tests focus on
re-validation of create-time business rules on PATCH, not auth.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import date
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi import Header
from httpx import ASGITransport, AsyncClient
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
    """A clan plus an approved editor membership."""
    clan_id = uuid.uuid4()
    editor_id = uuid.uuid4()
    async with session_factory() as s:
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'Update Val Clan', :slug)"),
            {"id": clan_id, "slug": f"updval-{clan_id.hex[:8]}"},
        )
        await s.execute(
            sa.text(
                "INSERT INTO user_profiles (id, email, display_name) VALUES (:id, :email, :name)"
            ),
            {"id": editor_id, "email": f"{editor_id.hex[:8]}@example.com", "name": "editor"},
        )
        await s.execute(
            sa.text(
                "INSERT INTO user_clan_roles "
                "(user_id, clan_id, role, is_approved, approved_by, approved_at) "
                "VALUES (:uid, :cid, 'editor', true, :uid, now())"
            ),
            {"uid": editor_id, "cid": clan_id},
        )
        await s.commit()
    return {"clan_id": clan_id, "editor_id": editor_id}


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
def editor_headers(seeded: dict[str, Any]) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {seeded['editor_id']}",
        "X-Current-Clan-Id": str(seeded["clan_id"]),
    }


async def _make_person(
    client: AsyncClient,
    headers: dict[str, str],
    name: str,
    gender: str,
    birth_date: date | None = None,
) -> str:
    body: dict[str, Any] = {"full_name": name, "gender": gender}
    if birth_date is not None:
        body["birth_date"] = birth_date.isoformat()
    resp = await client.post("/api/v1/persons", headers=headers, json=body)
    assert resp.status_code == 201, resp.text
    return str(resp.json()["data"]["id"])


# ── Fixtures: parent-child re-validation scenarios ───────────────────────────


@pytest.fixture()
async def child_with_two_bio_parents_and_one_adopted(
    client: AsyncClient, editor_headers: dict[str, str]
) -> tuple[str, int]:
    """Child already has 2 biological parents + 1 adopted parent. Returns the
    adopted link's (id, version) — flipping it to biological must be blocked by
    the bio-parent limit."""
    child_bd = date(2000, 1, 1)
    parent_bd = date(1970, 1, 1)  # 30y gap — comfortably clears the bio floor
    child = await _make_person(client, editor_headers, "Child A", "female", child_bd)
    bio1 = await _make_person(client, editor_headers, "Bio Parent A1", "male", parent_bd)
    bio2 = await _make_person(client, editor_headers, "Bio Parent A2", "female", parent_bd)
    adoptive = await _make_person(client, editor_headers, "Adoptive Parent A3", "male", parent_bd)

    for parent in (bio1, bio2):
        resp = await client.post(
            "/api/v1/relationships/parent-child",
            headers=editor_headers,
            json={"parent_id": parent, "child_id": child, "relationship_type": "biological"},
        )
        assert resp.status_code == 201, resp.text

    resp = await client.post(
        "/api/v1/relationships/parent-child",
        headers=editor_headers,
        json={"parent_id": adoptive, "child_id": child, "relationship_type": "adopted"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    return data["id"], data["version"]


@pytest.fixture()
async def adopted_link_age_gap_5y(
    client: AsyncClient, editor_headers: dict[str, str]
) -> tuple[str, int]:
    """An adopted link with only a 5y parent/child age gap — fine for 'adopted',
    but flipping it to 'biological' must be blocked by the min age-gap rule."""
    child_bd = date(2000, 1, 1)
    parent_bd = date(1995, 1, 1)  # 5y gap
    child = await _make_person(client, editor_headers, "Child B", "male", child_bd)
    parent = await _make_person(client, editor_headers, "Parent B", "female", parent_bd)

    resp = await client.post(
        "/api/v1/relationships/parent-child",
        headers=editor_headers,
        json={"parent_id": parent, "child_id": child, "relationship_type": "adopted"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    return data["id"], data["version"]


@pytest.fixture()
async def bio_link_valid(client: AsyncClient, editor_headers: dict[str, str]) -> tuple[str, int]:
    """A single biological parent, 30y age gap — a legitimate bio->adopted type
    correction must still succeed (relaxing to 'adopted' has no bio-limit/age
    constraints, and excludes itself from any self-count)."""
    child_bd = date(2000, 1, 1)
    parent_bd = date(1970, 1, 1)  # 30y gap
    child = await _make_person(client, editor_headers, "Child C", "female", child_bd)
    parent = await _make_person(client, editor_headers, "Parent C", "male", parent_bd)

    resp = await client.post(
        "/api/v1/relationships/parent-child",
        headers=editor_headers,
        json={"parent_id": parent, "child_id": child, "relationship_type": "biological"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    return data["id"], data["version"]


# ── Fixtures: marriage re-validation scenarios ───────────────────────────────


@pytest.fixture()
async def divorced_marriage_with_active_duplicate(
    client: AsyncClient, editor_headers: dict[str, str]
) -> tuple[str, int]:
    """A divorced marriage between (p1, p2), plus a SEPARATE active marriage for
    the same pair. Flipping the divorced one back to 'married' must be blocked —
    the pair already has an active marriage."""
    p1 = await _make_person(client, editor_headers, "Husband D", "male")
    p2 = await _make_person(client, editor_headers, "Wife D", "female")

    # Create the divorced one FIRST: check_duplicate_marriage only looks at
    # non-divorced rows, so this insert sees no conflict.
    divorced = await client.post(
        "/api/v1/relationships/marriages",
        headers=editor_headers,
        json={"person1_id": p1, "person2_id": p2, "status": "divorced"},
    )
    assert divorced.status_code == 201, divorced.text

    # Now the active marriage for the SAME pair — also passes create-time
    # validation because the existing row is divorced (excluded).
    active = await client.post(
        "/api/v1/relationships/marriages",
        headers=editor_headers,
        json={"person1_id": p1, "person2_id": p2, "status": "married"},
    )
    assert active.status_code == 201, active.text

    data = divorced.json()["data"]
    return data["id"], data["version"]


@pytest.fixture()
async def father_with_wife_order_1(
    client: AsyncClient, editor_headers: dict[str, str]
) -> tuple[str, str]:
    """A father with an active marriage at spouse_order=1, plus a spare wife id
    for a create-time duplicate-spouse-order attempt."""
    father = await _make_person(client, editor_headers, "Father E", "male")
    wife1 = await _make_person(client, editor_headers, "Wife E1", "female")
    other_wife = await _make_person(client, editor_headers, "Wife E2", "female")

    resp = await client.post(
        "/api/v1/relationships/marriages",
        headers=editor_headers,
        json={"person1_id": father, "person2_id": wife1, "status": "married", "spouse_order": 1},
    )
    assert resp.status_code == 201, resp.text
    return father, other_wife


@pytest.fixture()
async def father_two_wives_orders_1_2(
    client: AsyncClient, editor_headers: dict[str, str]
) -> tuple[str, int]:
    """A father with two active marriages at spouse_order 1 and 2. Returns the
    (id, version) of the spouse_order=2 marriage — updating it to spouse_order=1
    must collide with the spouse_order=1 marriage."""
    father = await _make_person(client, editor_headers, "Father F", "male")
    wife1 = await _make_person(client, editor_headers, "Wife F1", "female")
    wife2 = await _make_person(client, editor_headers, "Wife F2", "female")

    r1 = await client.post(
        "/api/v1/relationships/marriages",
        headers=editor_headers,
        json={"person1_id": father, "person2_id": wife1, "status": "married", "spouse_order": 1},
    )
    assert r1.status_code == 201, r1.text

    r2 = await client.post(
        "/api/v1/relationships/marriages",
        headers=editor_headers,
        json={"person1_id": father, "person2_id": wife2, "status": "married", "spouse_order": 2},
    )
    assert r2.status_code == 201, r2.text
    data2 = r2.json()["data"]
    return data2["id"], data2["version"]


# ── Tests ─────────────────────────────────────────────────────────────────


async def test_patch_adopted_to_biological_blocked_by_bio_limit(
    client: AsyncClient,
    editor_headers: dict[str, str],
    child_with_two_bio_parents_and_one_adopted: tuple[str, int],
) -> None:
    link_id, v = child_with_two_bio_parents_and_one_adopted
    resp = await client.patch(
        f"/api/v1/relationships/parent-child/{link_id}",
        json={"relationship_type": "biological", "expected_version": v},
        headers=editor_headers,
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "relationship.too_many_biological_parents"


async def test_patch_adopted_to_biological_blocked_by_age_gap(
    client: AsyncClient,
    editor_headers: dict[str, str],
    adopted_link_age_gap_5y: tuple[str, int],
) -> None:
    link_id, v = adopted_link_age_gap_5y
    resp = await client.patch(
        f"/api/v1/relationships/parent-child/{link_id}",
        json={"relationship_type": "biological", "expected_version": v},
        headers=editor_headers,
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "relationship.parent_too_young"


async def test_legitimate_type_correction_still_succeeds(
    client: AsyncClient,
    editor_headers: dict[str, str],
    bio_link_valid: tuple[str, int],
) -> None:
    link_id, v = bio_link_valid  # single bio parent, 30y gap
    resp = await client.patch(
        f"/api/v1/relationships/parent-child/{link_id}",
        json={"relationship_type": "adopted", "expected_version": v},
        headers=editor_headers,
    )
    assert resp.status_code == 200  # bio->adopted relaxes rules; and self-exclusion
    # means flipping back later doesn't count itself


async def test_divorced_to_married_blocked_when_duplicate_active(
    client: AsyncClient,
    editor_headers: dict[str, str],
    divorced_marriage_with_active_duplicate: tuple[str, int],
) -> None:
    marriage_id, v = divorced_marriage_with_active_duplicate
    resp = await client.patch(
        f"/api/v1/relationships/marriages/{marriage_id}",
        json={"status": "married", "expected_version": v},
        headers=editor_headers,
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "relationship.duplicate_marriage"


async def test_duplicate_spouse_order_create_is_409(
    client: AsyncClient,
    editor_headers: dict[str, str],
    father_with_wife_order_1: tuple[str, str],
) -> None:
    father_id, other_wife_id = father_with_wife_order_1
    resp = await client.post(
        "/api/v1/relationships/marriages",
        json={"person1_id": father_id, "person2_id": other_wife_id, "spouse_order": 1},
        headers=editor_headers,
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "relationship.duplicate_spouse_order"


async def test_spouse_order_update_collision_is_409(
    client: AsyncClient,
    editor_headers: dict[str, str],
    father_two_wives_orders_1_2: tuple[str, int],
) -> None:
    marriage2_id, v2 = father_two_wives_orders_1_2
    resp = await client.patch(
        f"/api/v1/relationships/marriages/{marriage2_id}",
        json={"spouse_order": 1, "expected_version": v2},
        headers=editor_headers,
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "relationship.duplicate_spouse_order"
