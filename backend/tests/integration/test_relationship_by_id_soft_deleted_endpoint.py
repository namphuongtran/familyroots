"""The two by-id relationship reads hide an edge whose endpoint person is deleted.

**Seed S-056, and it is the half seed S-054 did not reach.** S-054 gave the three
batch reads a second soft-delete predicate: the edge row's own ``is_deleted`` says
whether someone deleted *the edge*, and says nothing about the persons it points
at. ``GET /relationships/marriages/{id}`` and
``GET /relationships/parent-child/{id}`` reach the same rows by edge id instead of
by person, and they still carried only the first half. So the same API answered
``404`` for a soft-deleted person and, one request later, handed a client an edge
naming that person's uuid.

**The write path must not move, and that is the whole reason this file is worth
reading.** ``SqlAlchemyMarriageRepository.get_by_id`` loads the row for the update
and the delete as well as for the read
(``app/application/relationship/handlers.py:69,114,158,184``). Putting the
predicate there would take an admin's ability to repair or remove an edge that
touches a soft-deleted person, and would leave that row unreachable through the
API entirely. So the read got its own accessor — ``get_visible_by_id`` on
``MarriageReadPort`` / ``ParentChildReadPort`` — and the command handlers stayed on
the unfiltered ``get_by_id``.

**Every test below takes both readings in one run**, because that is the outcome
the change has to produce and a ``404``-only test would pass over a change that
broke the admin's repair path. ``.claude/rules/seeds.md``, "A test pins an outcome,
not a setting": the negative control for this file deletes the predicate and
watches the ``404`` assertions fail while the ``DELETE`` and ``PATCH`` assertions
keep passing both ways, which is what proves the two halves are separate.

**No cascade, and ``test_the_edge_row_is_untouched...`` proves it with raw SQL.**
The edge rows keep ``is_deleted = false`` while the person they point at does not
(ADR-051 § 2). Nothing consumes ``PersonDeleted``. That is what makes this file
about the read.

**The seeded clan carries a live spouse and a live child beside the deleted
ones.** Without them a read that returned nothing at all would pass every "the
deleted one is absent" assertion.

One actor, with role ``admin``: ``require_role`` is hierarchy-based
(``app/core/permissions.py:26``), so the same caller satisfies ``RequireViewer`` on
the ``GET`` and ``RequireAdmin`` on the ``DELETE``. Real Postgres
(``migrated_db_url``), real RBAC; only JWT *verification* is stubbed, the same way
``tests/integration/test_occ_relationships.py`` does it.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi import Header
from httpx2 import ASGITransport, AsyncClient
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
    """Clan A holds one survivor with four edges, and clan B holds nothing.

    The live spouse and the live child are the control on every assertion. Clan B
    exists so the by-id read's clan predicate is proven two-sided rather than
    assumed: it has an approved admin and no rows of its own.
    """
    clan_id, other_clan_id = uuid.uuid4(), uuid.uuid4()
    admin_id, other_admin_id = uuid.uuid4(), uuid.uuid4()
    ids: dict[str, Any] = {
        "clan_id": clan_id,
        "other_clan_id": other_clan_id,
        "admin_id": admin_id,
        "other_admin_id": other_admin_id,
    }
    async with session_factory() as s:
        for cid, name in ((clan_id, "Họ Cạnh Đã Xoá"), (other_clan_id, "Họ Bên Kia")):
            await s.execute(
                sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, :n, :slug)"),
                {"id": cid, "n": name, "slug": f"byid-{cid.hex[:10]}"},
            )
        for uid, cid in ((admin_id, clan_id), (other_admin_id, other_clan_id)):
            await s.execute(
                sa.text(
                    "INSERT INTO user_profiles (id, email, display_name) VALUES (:id, :email, 'a')"
                ),
                {"id": uid, "email": f"{uid.hex[:10]}@example.com"},
            )
            await s.execute(
                sa.text(
                    "INSERT INTO user_clan_roles "
                    "(user_id, clan_id, role, is_approved, approved_by, approved_at) "
                    "VALUES (:uid, :cid, 'admin', true, :uid, now())"
                ),
                {"uid": uid, "cid": cid},
            )

        for key, name, gender, deleted in (
            ("survivor", "Người Còn Lại", "male", False),
            ("live_spouse", "Vợ Cả", "female", False),
            ("deleted_spouse", "Vợ Đã Xoá", "female", True),
            ("live_child", "Con Cả", "male", False),
            ("deleted_child", "Con Đã Xoá", "male", True),
        ):
            pid = uuid.uuid4()
            await s.execute(
                sa.text(
                    "INSERT INTO persons "
                    "(id, full_name, gender, created_by_clan_id, created_by, "
                    " is_deleted, deleted_at, deleted_by) "
                    "VALUES (:id, :n, :g, :cid, :uid, :d, "
                    "        CASE WHEN :d THEN now() END, CASE WHEN :d THEN :uid END)"
                ),
                {"id": pid, "n": name, "g": gender, "cid": clan_id, "uid": admin_id, "d": deleted},
            )
            await s.execute(
                sa.text(
                    "INSERT INTO clan_memberships (person_id, clan_id, joined_at) "
                    "VALUES (:pid, :cid, now())"
                ),
                {"pid": pid, "cid": clan_id},
            )
            ids[key] = pid

        for key, spouse, order in (
            ("live_marriage_id", "live_spouse", 1),
            ("deleted_spouse_marriage_id", "deleted_spouse", 2),
        ):
            edge_id = uuid.uuid4()
            await s.execute(
                sa.text(
                    "INSERT INTO marriages "
                    "(id, person1_id, person2_id, status, spouse_order, marriage_date, "
                    " created_by_clan_id, created_by) "
                    "VALUES (:id, :p1, :p2, 'married', :o, '1980-01-01', :cid, :uid)"
                ),
                {
                    "id": edge_id,
                    "p1": ids["survivor"],
                    "p2": ids[spouse],
                    "o": order,
                    "cid": clan_id,
                    "uid": admin_id,
                },
            )
            ids[key] = edge_id

        for key, child in (
            ("live_link_id", "live_child"),
            ("deleted_child_link_id", "deleted_child"),
        ):
            edge_id = uuid.uuid4()
            await s.execute(
                sa.text(
                    "INSERT INTO parent_child "
                    "(id, parent_id, child_id, created_by_clan_id, relationship_type, created_by) "
                    "VALUES (:id, :p, :c, :cid, 'biological', :uid)"
                ),
                {
                    "id": edge_id,
                    "p": ids["survivor"],
                    "c": ids[child],
                    "cid": clan_id,
                    "uid": admin_id,
                },
            )
            ids[key] = edge_id

        await s.commit()
    return ids


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
def admin_headers(seeded: dict[str, Any]) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {seeded['admin_id']}",
        "X-Current-Clan-Id": str(seeded["clan_id"]),
    }


@pytest.fixture()
def other_clan_headers(seeded: dict[str, Any]) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {seeded['other_admin_id']}",
        "X-Current-Clan-Id": str(seeded["other_clan_id"]),
    }


async def _edge_is_deleted(
    session_factory: async_sessionmaker[AsyncSession], table: str, edge_id: uuid.UUID
) -> bool:
    async with session_factory() as s:
        result = await s.execute(
            sa.text(f"SELECT is_deleted FROM {table} WHERE id = :id"),
            {"id": edge_id},
        )
    return bool(result.scalar_one())


async def test_the_deleted_person_is_gone_from_their_own_read(
    client: AsyncClient, seeded: dict[str, Any], admin_headers: dict[str, str]
) -> None:
    """The premise the file rests on: the same API answers 404 for that person."""
    gone = await client.get(f"/api/v1/persons/{seeded['deleted_spouse']}", headers=admin_headers)
    assert gone.status_code == 404, gone.text

    alive = await client.get(f"/api/v1/persons/{seeded['live_spouse']}", headers=admin_headers)
    assert alive.status_code == 200, alive.text


async def test_the_edge_row_is_untouched_so_the_read_is_what_hides_it(
    session_factory: async_sessionmaker[AsyncSession], seeded: dict[str, Any]
) -> None:
    """Raw SQL, so the rest of the file is a claim about the read and not the data.

    ADR-051 decided against a cascade. Nothing consumes ``PersonDeleted``, so both
    edge rows keep ``is_deleted = false`` while the person they point at does not.
    """
    assert await _edge_is_deleted(session_factory, "marriages", seeded["live_marriage_id"]) is False
    assert (
        await _edge_is_deleted(session_factory, "marriages", seeded["deleted_spouse_marriage_id"])
        is False
    )
    assert (
        await _edge_is_deleted(session_factory, "parent_child", seeded["deleted_child_link_id"])
        is False
    )
    async with session_factory() as s:
        person = await s.execute(
            sa.text("SELECT is_deleted FROM persons WHERE id = :id"),
            {"id": seeded["deleted_spouse"]},
        )
    assert person.scalar_one() is True


async def test_get_marriage_by_id_hides_a_deleted_spouse_while_delete_still_reaches_it(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    seeded: dict[str, Any],
    admin_headers: dict[str, str],
) -> None:
    """Both readings in one run — the 404 and the admin's delete on the same id.

    A test that only checked the ``404`` would pass over a predicate added to the
    shared loader, which would answer ``404`` on the ``DELETE`` too and leave the
    row unreachable through the API entirely.
    """
    url = f"/api/v1/relationships/marriages/{seeded['deleted_spouse_marriage_id']}"

    live = await client.get(
        f"/api/v1/relationships/marriages/{seeded['live_marriage_id']}", headers=admin_headers
    )
    assert live.status_code == 200, live.text  # control: the read works at all

    # Both readings are taken before either is asserted, so the negative control
    # shows the two halves in one message instead of stopping at the first.
    hidden = await client.get(url, headers=admin_headers)
    removed = await client.delete(url, headers=admin_headers)
    row_is_deleted = await _edge_is_deleted(
        session_factory, "marriages", seeded["deleted_spouse_marriage_id"]
    )

    assert (hidden.status_code, removed.status_code, row_is_deleted) == (404, 200, True), (
        f"read={hidden.text} delete={removed.text}"
    )


async def test_get_parent_child_by_id_hides_a_deleted_child_while_delete_still_reaches_it(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    seeded: dict[str, Any],
    admin_headers: dict[str, str],
) -> None:
    """The same pair of readings on the lineage edge."""
    url = f"/api/v1/relationships/parent-child/{seeded['deleted_child_link_id']}"

    live = await client.get(
        f"/api/v1/relationships/parent-child/{seeded['live_link_id']}", headers=admin_headers
    )
    assert live.status_code == 200, live.text  # control: the read works at all

    hidden = await client.get(url, headers=admin_headers)
    removed = await client.delete(url, headers=admin_headers)
    row_is_deleted = await _edge_is_deleted(
        session_factory, "parent_child", seeded["deleted_child_link_id"]
    )

    assert (hidden.status_code, removed.status_code, row_is_deleted) == (404, 200, True), (
        f"read={hidden.text} delete={removed.text}"
    )


async def test_the_repair_path_still_reaches_an_edge_whose_endpoint_is_deleted(
    client: AsyncClient, seeded: dict[str, Any], admin_headers: dict[str, str]
) -> None:
    """``PATCH`` is the other caller of the shared loader (``handlers.py:69,158``).

    An admin correcting a marriage date on an edge to a soft-deleted spouse must
    still succeed, and the ``PATCH`` response is the one place that edge's data is
    still legitimately visible.
    """
    marriage = await client.patch(
        f"/api/v1/relationships/marriages/{seeded['deleted_spouse_marriage_id']}",
        headers=admin_headers,
        json={"expected_version": 1, "notes": "sửa lại"},
    )
    assert marriage.status_code == 200, marriage.text
    assert marriage.json()["data"]["notes"] == "sửa lại"

    link = await client.patch(
        f"/api/v1/relationships/parent-child/{seeded['deleted_child_link_id']}",
        headers=admin_headers,
        json={"expected_version": 1, "notes": "sửa lại"},
    )
    assert link.status_code == 200, link.text
    assert link.json()["data"]["notes"] == "sửa lại"


async def test_the_two_readings_flip_back_when_the_person_is_restored(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    seeded: dict[str, Any],
    admin_headers: dict[str, str],
) -> None:
    """The failing reading and the passing reading are different values.

    Clearing ``persons.is_deleted`` — and nothing else, the edge rows are never
    touched — turns both ``404``s into ``200``s. Question 2 of
    ``.claude/rules/seeds.md``: a control that reads the same either way is not a
    control.
    """
    marriage_url = f"/api/v1/relationships/marriages/{seeded['deleted_spouse_marriage_id']}"
    link_url = f"/api/v1/relationships/parent-child/{seeded['deleted_child_link_id']}"

    assert (await client.get(marriage_url, headers=admin_headers)).status_code == 404
    assert (await client.get(link_url, headers=admin_headers)).status_code == 404

    async with session_factory() as s:
        await s.execute(
            sa.text(
                "UPDATE persons SET is_deleted = false, deleted_at = NULL, deleted_by = NULL "
                "WHERE id = ANY(:ids)"
            ),
            {"ids": [seeded["deleted_spouse"], seeded["deleted_child"]]},
        )
        await s.commit()

    assert (await client.get(marriage_url, headers=admin_headers)).status_code == 200
    assert (await client.get(link_url, headers=admin_headers)).status_code == 200


async def test_the_by_id_read_stays_clan_isolated_on_both_sides(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    seeded: dict[str, Any],
    admin_headers: dict[str, str],
    other_clan_headers: dict[str, str],
) -> None:
    """The new accessor keeps the clan predicate, read from both sides.

    Clan A's admin reads its own live edges; clan B's admin, approved in clan B and
    sending clan B's ``X-Current-Clan-Id``, gets ``404`` for the same two ids. The
    database layer is asserted separately, so an application-layer join cannot hide
    a wrong answer: ``created_by_clan_id`` on both rows is clan A.
    """
    for url in (
        f"/api/v1/relationships/marriages/{seeded['live_marriage_id']}",
        f"/api/v1/relationships/parent-child/{seeded['live_link_id']}",
    ):
        mine = await client.get(url, headers=admin_headers)
        assert mine.status_code == 200, mine.text
        theirs = await client.get(url, headers=other_clan_headers)
        assert theirs.status_code == 404, theirs.text

    async with session_factory() as s:
        owners = await s.execute(
            sa.text(
                "SELECT created_by_clan_id FROM marriages WHERE id = :m "
                "UNION ALL "
                "SELECT created_by_clan_id FROM parent_child WHERE id = :l"
            ),
            {"m": seeded["live_marriage_id"], "l": seeded["live_link_id"]},
        )
    assert set(owners.scalars().all()) == {seeded["clan_id"]}
