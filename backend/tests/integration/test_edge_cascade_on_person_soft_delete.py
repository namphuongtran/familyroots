"""An edge pointing at a soft-deleted person does not surface, on any read.

**This file replaces the characterization tests the earlier characterization tests wrote here on
2026-08-22.** Those asserted the opposite, because that was what the code did:
``GET /persons/{survivor}/marriages`` returned the edge to a soft-deleted
spouse, ``GET /persons/{survivor}/parent-child`` returned the edge to a
soft-deleted child, and ``POST /persons/batch`` with ``include=stats`` answered
``spouse_count: 2, child_count: 2`` for a survivor with one live spouse and one
live child. The same API answered ``404`` for the deleted person in the same
run. The edge read filter closed that, and the old assertions are its negative control —
all four flipped, each on a different value (recorded in the edge read filter commit
message). The file was **replaced**, not repaired assertion by assertion.

**What changed, and what deliberately did not.** the edge read filter is a read filter only.
``get_marriages_batch`` and ``get_parent_child_links_batch``
(``app/infrastructure/persistence/person_query_port.py``) now drop an edge with a
soft-deleted person on either end, reaching the same answer
``get_timelines_batch`` and the tree builder already reached;
``get_stats_for_persons`` (``app/infrastructure/persistence/person_repository.py``)
does the same in its two counting sub-queries. Both use ``NOT EXISTS`` rather
than the timeline's join, for a measured reason recorded in the query port's
module docstring — these are batch reads, and the join made the planner scan the
whole ``persons`` table. **No cascade was added.** ``Person.soft_delete``
(``app/domain/person/entity.py:267-280``) still sets only the person's own
flags, ``PersonDeleted`` still has no consumer outside ``app/domain/person``,
and the edge rows still read ``is_deleted = false`` — which
``test_the_edge_rows_are_untouched...`` below proves with raw SQL, so this
file's claim rests on the read and not on a data change. Whether the cascade
should exist at all is ADR-051's decision and the by-id read fix's build. **This
filter stays correct either way**, because rows written before any cascade
ships would not carry its flag.

**What was leaking is the edge and the uuid, not the name.**
``MarriageResponse`` (``app/schemas/marriage.py:61-85``) and
``ParentChildResponse`` (``app/schemas/parent_child.py:40-59``) carry
``person1_id``/``person2_id`` and ``parent_id``/``child_id`` and no name field.
A client learned that a person existed and was related, plus their uuid, and
nothing else. Say that much and no more.

**The two-sided shape is the point and it is inherited from the earlier tests.** Every
fixture carries a live spouse and a live child beside the deleted ones. Without
them, a read that returned nothing at all would pass every "the deleted one is
absent" assertion. And ``test_the_same_readings_flip_back_when_the_person_is
_restored`` clears the person's ``is_deleted`` flag and takes the same four
readings again, so the failing reading and the passing reading are different
values rather than one reading either way — question 2 of
``.claude/rules/testing.md``, "A test pins an outcome, not a setting".

Real Postgres (``migrated_db_url``), JWT verification stubbed the same way as
``tests/integration/test_person_documents_soft_delete.py``. Every read is taken
over HTTP so the answer is about a response body rather than about a repository
call.
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
    """One survivor with four edges: a live spouse, a soft-deleted spouse, a live
    child, and a soft-deleted child.

    The live pair is the control on every assertion below. Without it a read that
    returned nothing at all would pass "the deleted one is absent" by accident,
    and a count of zero would look like a working filter.
    """
    clan_id = uuid.uuid4()
    viewer_id = uuid.uuid4()
    ids: dict[str, Any] = {"clan_id": clan_id, "viewer_id": viewer_id}
    async with session_factory() as s:
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'Họ Cạnh Mồ Côi', :slug)"),
            {"id": clan_id, "slug": f"orphan-edge-{clan_id.hex[:8]}"},
        )
        await s.execute(
            sa.text(
                "INSERT INTO user_profiles (id, email, display_name) VALUES (:id, :email, 'v')"
            ),
            {"id": viewer_id, "email": f"{viewer_id.hex[:8]}@example.com"},
        )
        await s.execute(
            sa.text(
                "INSERT INTO user_clan_roles "
                "(user_id, clan_id, role, is_approved, approved_by, approved_at) "
                "VALUES (:uid, :cid, 'viewer', true, :uid, now())"
            ),
            {"uid": viewer_id, "cid": clan_id},
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
                {"id": pid, "n": name, "g": gender, "cid": clan_id, "uid": viewer_id, "d": deleted},
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
                    "uid": viewer_id,
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
                    "uid": viewer_id,
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
def viewer_headers(seeded: dict[str, Any]) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {seeded['viewer_id']}",
        "X-Current-Clan-Id": str(seeded["clan_id"]),
    }


async def _marriage_edge_ids(
    client: AsyncClient, seeded: dict[str, Any], headers: dict[str, str]
) -> set[str]:
    resp = await client.get(f"/api/v1/persons/{seeded['survivor']}/marriages", headers=headers)
    assert resp.status_code == 200, resp.text
    return {m["id"] for m in resp.json()["data"]}


async def _parent_child_edge_ids(
    client: AsyncClient, seeded: dict[str, Any], headers: dict[str, str]
) -> set[str]:
    resp = await client.get(f"/api/v1/persons/{seeded['survivor']}/parent-child", headers=headers)
    assert resp.status_code == 200, resp.text
    return {link["id"] for link in resp.json()["data"]}


async def _survivor_stats(
    client: AsyncClient, seeded: dict[str, Any], headers: dict[str, str]
) -> dict[str, int]:
    resp = await client.post(
        "/api/v1/persons/batch",
        headers=headers,
        json={"ids": [str(seeded["survivor"])], "include": "stats"},
    )
    assert resp.status_code == 200, resp.text
    stats: dict[str, int] = resp.json()["data"][0]["stats"]
    return stats


async def test_the_deleted_person_is_gone_from_their_own_reads(
    client: AsyncClient, seeded: dict[str, Any], viewer_headers: dict[str, str]
) -> None:
    """The premise the rest of the file rests on: the person really is deleted.

    Without this, "the survivor's edge list omits them" would be unremarkable.
    """
    gone = await client.get(f"/api/v1/persons/{seeded['deleted_spouse']}", headers=viewer_headers)
    assert gone.status_code == 404, gone.text

    alive = await client.get(f"/api/v1/persons/{seeded['live_spouse']}", headers=viewer_headers)
    assert alive.status_code == 200, alive.text


async def test_the_edge_rows_are_untouched_so_the_read_filter_is_what_hides_them(
    session_factory: async_sessionmaker[AsyncSession], seeded: dict[str, Any]
) -> None:
    """Read the rows back with raw SQL, so this claim does not rest on a join.

    The edge read filter added no cascade: nothing consumes ``PersonDeleted``, so both edge rows
    keep ``is_deleted = false`` while the person they point at does not. This is
    the fact that makes the rest of the file about the **read**. It is also the
    boundary ADR-051 and the by-id read fix own — when a cascade ships, this test is the one
    that changes, and the reads below must keep passing unchanged.
    """
    async with session_factory() as s:
        marriage = await s.execute(
            sa.text("SELECT is_deleted FROM marriages WHERE id = :id"),
            {"id": seeded["deleted_spouse_marriage_id"]},
        )
        link = await s.execute(
            sa.text("SELECT is_deleted FROM parent_child WHERE id = :id"),
            {"id": seeded["deleted_child_link_id"]},
        )
        person = await s.execute(
            sa.text("SELECT is_deleted FROM persons WHERE id = :id"),
            {"id": seeded["deleted_spouse"]},
        )
    assert person.scalar_one() is True
    assert marriage.scalar_one() is False
    assert link.scalar_one() is False


async def test_person_marriages_omits_the_edge_to_a_soft_deleted_spouse(
    client: AsyncClient, seeded: dict[str, Any], viewer_headers: dict[str, str]
) -> None:
    """A client asking who the survivor is married to is told about live spouses only."""
    resp = await client.get(
        f"/api/v1/persons/{seeded['survivor']}/marriages", headers=viewer_headers
    )
    assert resp.status_code == 200, resp.text
    edge_ids = {m["id"] for m in resp.json()["data"]}
    assert str(seeded["live_marriage_id"]) in edge_ids  # control: the read works at all
    assert str(seeded["deleted_spouse_marriage_id"]) not in edge_ids

    partner_ids = {m["person1_id"] for m in resp.json()["data"]} | {
        m["person2_id"] for m in resp.json()["data"]
    }
    assert str(seeded["live_spouse"]) in partner_ids
    assert str(seeded["deleted_spouse"]) not in partner_ids


async def test_person_parent_child_omits_the_edge_to_a_soft_deleted_child(
    client: AsyncClient, seeded: dict[str, Any], viewer_headers: dict[str, str]
) -> None:
    """The same rule on the lineage edge, which is the one ADR-006 calls irreplaceable."""
    resp = await client.get(
        f"/api/v1/persons/{seeded['survivor']}/parent-child", headers=viewer_headers
    )
    assert resp.status_code == 200, resp.text
    edge_ids = {link["id"] for link in resp.json()["data"]}
    assert str(seeded["live_link_id"]) in edge_ids  # control: the read works at all
    assert str(seeded["deleted_child_link_id"]) not in edge_ids

    child_ids = {link["child_id"] for link in resp.json()["data"]}
    assert str(seeded["live_child"]) in child_ids
    assert str(seeded["deleted_child"]) not in child_ids


async def test_batch_stats_counts_only_edges_whose_other_end_is_live(
    client: AsyncClient, seeded: dict[str, Any], viewer_headers: dict[str, str]
) -> None:
    """The edge count answers one, matching the one live spouse and one live child.

    ``spouse_count`` and ``child_count`` are what a card in the UI renders, so
    this is the number a reader sees before any list is opened. It counted two.
    """
    assert await _survivor_stats(client, seeded, viewer_headers) == {
        "spouse_count": 1,
        "child_count": 1,
    }


async def test_the_batch_include_fan_out_omits_the_same_two_edges(
    client: AsyncClient, seeded: dict[str, Any], viewer_headers: dict[str, str]
) -> None:
    """``POST /persons/batch`` reaches the edge reads through a different path.

    The two sub-resource routes call the single-person delegates; the batch route
    calls ``get_included_data_batch``, one query per include token for the whole
    batch. Same SQL underneath, but the fan-out is what a list screen uses, so it
    is read here rather than inferred.
    """
    resp = await client.post(
        "/api/v1/persons/batch",
        headers=viewer_headers,
        json={"ids": [str(seeded["survivor"])], "include": "marriages,parent_child"},
    )
    assert resp.status_code == 200, resp.text
    person = resp.json()["data"][0]

    marriage_ids = {m["id"] for m in person["marriages"]}
    assert str(seeded["live_marriage_id"]) in marriage_ids
    assert str(seeded["deleted_spouse_marriage_id"]) not in marriage_ids

    link_ids = {link["id"] for link in person["parent_child"]}
    assert str(seeded["live_link_id"]) in link_ids
    assert str(seeded["deleted_child_link_id"]) not in link_ids


async def test_the_marriages_read_and_the_timeline_agree_on_the_same_edge(
    client: AsyncClient, seeded: dict[str, Any], viewer_headers: dict[str, str]
) -> None:
    """Two reads over one marriage row now give a client the same answer.

    The timeline join always filtered the counterpart person; the marriages read
    did not. This test exists so the agreement is one reading rather than an
    inference across two files.
    """
    timeline = await client.get(
        f"/api/v1/persons/{seeded['survivor']}/timeline", headers=viewer_headers
    )
    assert timeline.status_code == 200, timeline.text
    partners = {
        e["related_person_id"] for e in timeline.json()["data"] if e["event_type"] == "marriage"
    }
    assert str(seeded["live_spouse"]) in partners  # control: the read works at all
    assert str(seeded["deleted_spouse"]) not in partners

    marriages = await client.get(
        f"/api/v1/persons/{seeded['survivor']}/marriages", headers=viewer_headers
    )
    assert marriages.status_code == 200, marriages.text
    partner_ids = {m["person1_id"] for m in marriages.json()["data"]} | {
        m["person2_id"] for m in marriages.json()["data"]
    }
    assert str(seeded["live_spouse"]) in partner_ids
    assert str(seeded["deleted_spouse"]) not in partner_ids


async def test_the_subtree_read_agrees_with_the_edge_reads_about_the_same_child(
    client: AsyncClient, seeded: dict[str, Any], viewer_headers: dict[str, str]
) -> None:
    """The tree was already right; check the edge read filter did not push the reads past it.

    The tree functions filter soft-deleted persons — the Alembic chain installs
    them, from ``backend/migrations/versions/003_tree_functions.py`` onward — so
    the survivor's subtree already showed one child and one spouse. The edge
    reads now say the same. A filter that hid the live pair as well would agree
    with nothing.
    """
    resp = await client.get(f"/api/v1/tree/subtree/{seeded['survivor']}", headers=viewer_headers)
    assert resp.status_code == 200, resp.text
    root = resp.json()["data"]["tree"]

    child_ids = {child["id"] for child in root["children"]}
    assert child_ids == {str(seeded["live_child"])}

    spouse_ids = {spouse["id"] for spouse in root["spouses"]}
    assert spouse_ids == {str(seeded["live_spouse"])}

    assert child_ids == {
        link["child_id"]
        for link in (
            await client.get(
                f"/api/v1/persons/{seeded['survivor']}/parent-child", headers=viewer_headers
            )
        ).json()["data"]
    }


async def test_the_same_readings_flip_back_when_the_person_is_restored(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    seeded: dict[str, Any],
    viewer_headers: dict[str, str],
) -> None:
    """The control: the four readings above are about the counterpart person.

    Clearing ``persons.is_deleted`` on the spouse and the child — and nothing
    else, the edge rows are never touched — makes every reading take its other
    value: both edges come back and both counts go to two. So the failing
    reading and the passing reading are different values, not one reading either
    way (question 2 of ``.claude/rules/testing.md``, "A test pins an outcome, not
    a setting"). It also pins the behaviour ADR-051 has to preserve: a restored
    person's edges must reappear.
    """
    before_marriages = await _marriage_edge_ids(client, seeded, viewer_headers)
    before_links = await _parent_child_edge_ids(client, seeded, viewer_headers)
    before_stats = await _survivor_stats(client, seeded, viewer_headers)
    assert str(seeded["deleted_spouse_marriage_id"]) not in before_marriages
    assert str(seeded["deleted_child_link_id"]) not in before_links
    assert before_stats == {"spouse_count": 1, "child_count": 1}

    async with session_factory() as s:
        await s.execute(
            sa.text(
                "UPDATE persons SET is_deleted = false, deleted_at = NULL, deleted_by = NULL "
                "WHERE id = ANY(:ids)"
            ),
            {"ids": [seeded["deleted_spouse"], seeded["deleted_child"]]},
        )
        await s.commit()

    after_marriages = await _marriage_edge_ids(client, seeded, viewer_headers)
    after_links = await _parent_child_edge_ids(client, seeded, viewer_headers)
    after_stats = await _survivor_stats(client, seeded, viewer_headers)
    assert str(seeded["deleted_spouse_marriage_id"]) in after_marriages
    assert str(seeded["live_marriage_id"]) in after_marriages
    assert str(seeded["deleted_child_link_id"]) in after_links
    assert str(seeded["live_link_id"]) in after_links
    assert after_stats == {"spouse_count": 2, "child_count": 2}
