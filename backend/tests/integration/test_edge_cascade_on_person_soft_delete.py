"""What a client sees when a person is soft-deleted but their edges are not.

**This file establishes a consequence. It fixes nothing.** Seed S-020 asked one
question that needed a test rather than an opinion: with a person soft-deleted,
what does a relationship read and an edge count return? ADR-006's update of
2026-07-02 already decided the answer the product wants ("soft-deleting a person
will also soft-delete its edges"), and that decision has never been implemented:
``Person.soft_delete`` (``app/domain/person/entity.py:267-280``) sets the
person's own three flags and emits ``PersonDeleted``, and measured 2026-08-22
nothing outside ``app/domain/person`` consumes that event.

**These tests assert today's behaviour, not the wanted behaviour.** Each one is
named for the reading it takes. When the cascade is implemented, every test here
that says ``surfaces`` or ``counts`` must fail, and that failure is the signal to
delete this file and replace it with the wanted-behaviour tests. Do not "repair"
an assertion here to make a cascade land green.

**What was measured on 2026-08-22, and it is not one answer but two.** The reads
disagree with each other over the same edge row:

* ``GET /persons/{id}/marriages`` and ``GET /persons/{id}/parent-child`` filter
  the **edge**'s ``is_deleted`` and never look at the counterpart person
  (``app/infrastructure/persistence/person_query_port.py:56,81``), so the
  survivor's read hands a client an edge pointing at a person the same API
  answers ``404`` for.
* ``POST /persons/batch`` with ``include=stats`` counts the same edges
  (``app/infrastructure/persistence/person_repository.py:260-270``), so
  ``spouse_count`` and ``child_count`` include the soft-deleted counterpart.
* ``GET /persons/{id}/timeline`` **does** filter the counterpart
  (``person_query_port.py:207-216``, and the tree builder likewise, pinned by
  ``test_soft_deleted_spouse_filtering.py``).

So this is a client-visible defect, not a dormant one, and the two consumers of
"who is this person married to" give different answers on the same data.

**What leaks is the edge and the id, not the name.** ``MarriageResponse``
(``app/schemas/marriage.py:61-85``) and ``ParentChildResponse``
(``app/schemas/parent_child.py:40-59``) carry ``person1_id``/``person2_id`` and
``parent_id``/``child_id`` and no name field, so a client learns that a person
exists and is related, plus their uuid, and nothing else about them. Say that
much and no more.

**One document is wrong about this, and it is not fixed here.**
``docs/architecture/domain-rules.md:122`` reads "A soft-deleted person is
invisible everywhere, including every write guard", and its next clause is "It's
not just reads", which tells a reader the read side was already closed. The four
readings below say it was not. That file was fenced to another agent on
2026-08-22, so S-020 recorded the correction rather than making it.

**The negative control, run 2026-08-22.** The three ``surfaces``/``counts``
tests plus ``test_timeline_disagrees...`` were re-run against a fixture that
seeds both edges already soft-deleted, which is the state ADR-006's cascade
would produce. Five of the seven tests failed, each on the assertion naming the
edge: ``assert '2976...' in {'f199...'}`` for the marriages read, the same shape
for parent-child, and ``{'spouse_count': 1, 'child_count': 1} != {'spouse_count':
2, 'child_count': 2}`` for the counts. The fixture was then restored and all
seven passed. That is question 2 of ".claude/rules/seeds.md", "A test pins an
outcome, not a setting": the failing reading and the passing reading are
different values, so these assertions are about the edge and not about whether
the endpoint answers at all.

Real Postgres (``migrated_db_url``), JWT verification stubbed the same way as
``tests/integration/test_person_documents_soft_delete.py``. Every read is taken
over HTTP so the answer is about a response body rather than about a repository
call, and one test reads the rows back with raw SQL so the database-layer claim
does not rest on an application-layer join.
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
    returned nothing at all would pass the "the deleted one is present" test by
    accident in reverse, and a count of zero would look like a working cascade.
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


async def test_the_deleted_person_is_gone_from_their_own_reads(
    client: AsyncClient, seeded: dict[str, Any], viewer_headers: dict[str, str]
) -> None:
    """The premise the rest of the file rests on: the person really is deleted.

    Without this, "the survivor still sees the edge" would be unremarkable.
    """
    gone = await client.get(f"/api/v1/persons/{seeded['deleted_spouse']}", headers=viewer_headers)
    assert gone.status_code == 404, gone.text

    alive = await client.get(f"/api/v1/persons/{seeded['live_spouse']}", headers=viewer_headers)
    assert alive.status_code == 200, alive.text


async def test_both_edges_to_a_soft_deleted_person_stay_live_in_the_database(
    session_factory: async_sessionmaker[AsyncSession], seeded: dict[str, Any]
) -> None:
    """Read the rows back with raw SQL, so this claim does not rest on a join.

    Nothing consumes ``PersonDeleted``, so no cascade runs and both edge rows
    keep ``is_deleted = false`` while the person they point at does not.
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


async def test_person_marriages_surfaces_the_edge_to_a_soft_deleted_spouse(
    client: AsyncClient, seeded: dict[str, Any], viewer_headers: dict[str, str]
) -> None:
    """A client asking who the survivor is married to is told about a 404 person."""
    resp = await client.get(
        f"/api/v1/persons/{seeded['survivor']}/marriages", headers=viewer_headers
    )
    assert resp.status_code == 200, resp.text
    edge_ids = {m["id"] for m in resp.json()["data"]}
    assert str(seeded["live_marriage_id"]) in edge_ids  # control: the read works at all
    assert str(seeded["deleted_spouse_marriage_id"]) in edge_ids

    partner_ids = {m["person1_id"] for m in resp.json()["data"]} | {
        m["person2_id"] for m in resp.json()["data"]
    }
    assert str(seeded["deleted_spouse"]) in partner_ids


async def test_person_parent_child_surfaces_the_edge_to_a_soft_deleted_child(
    client: AsyncClient, seeded: dict[str, Any], viewer_headers: dict[str, str]
) -> None:
    """The same hole on the lineage edge, which is the one ADR-006 calls irreplaceable."""
    resp = await client.get(
        f"/api/v1/persons/{seeded['survivor']}/parent-child", headers=viewer_headers
    )
    assert resp.status_code == 200, resp.text
    edge_ids = {link["id"] for link in resp.json()["data"]}
    assert str(seeded["live_link_id"]) in edge_ids  # control: the read works at all
    assert str(seeded["deleted_child_link_id"]) in edge_ids

    child_ids = {link["child_id"] for link in resp.json()["data"]}
    assert str(seeded["deleted_child"]) in child_ids


async def test_batch_stats_counts_edges_that_point_at_soft_deleted_persons(
    client: AsyncClient, seeded: dict[str, Any], viewer_headers: dict[str, str]
) -> None:
    """The edge count answers two, not one, for a survivor with one live spouse.

    ``spouse_count`` and ``child_count`` are what a card in the UI renders, so
    this is the number a reader sees before any list is opened.
    """
    resp = await client.post(
        "/api/v1/persons/batch",
        headers=viewer_headers,
        json={"ids": [str(seeded["survivor"])], "include": "stats"},
    )
    assert resp.status_code == 200, resp.text
    stats = resp.json()["data"][0]["stats"]
    assert stats == {"spouse_count": 2, "child_count": 2}


async def test_the_same_readings_flip_once_the_edges_are_soft_deleted(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    seeded: dict[str, Any],
    viewer_headers: dict[str, str],
) -> None:
    """The negative control for the three tests above, and it needs explaining.

    Those three are characterization tests: they assert what the code does today,
    so "delete the fix and watch them fail" has nothing to delete. What must be
    shown instead is that each assertion reads the **edge** and not something
    that is true either way. So this test applies by hand exactly what ADR-006's
    2026-07-02 update decided the cascade would do -- soft-delete the edges that
    the person's own delete should have taken with it -- and takes the same three
    readings again. All three flip.

    Nothing in ``app/`` is modified. The wanted behaviour is reached through the
    data, which is why this control can live entirely in the test tree.
    """
    async with session_factory() as s:
        await s.execute(
            sa.text(
                "UPDATE marriages SET is_deleted = true, deleted_at = now(), deleted_by = :uid "
                "WHERE id = :id"
            ),
            {"id": seeded["deleted_spouse_marriage_id"], "uid": seeded["viewer_id"]},
        )
        await s.execute(
            sa.text(
                "UPDATE parent_child SET is_deleted = true, deleted_at = now(), deleted_by = :uid "
                "WHERE id = :id"
            ),
            {"id": seeded["deleted_child_link_id"], "uid": seeded["viewer_id"]},
        )
        await s.commit()

    marriages = await client.get(
        f"/api/v1/persons/{seeded['survivor']}/marriages", headers=viewer_headers
    )
    assert marriages.status_code == 200, marriages.text
    marriage_ids = {m["id"] for m in marriages.json()["data"]}
    assert str(seeded["live_marriage_id"]) in marriage_ids
    assert str(seeded["deleted_spouse_marriage_id"]) not in marriage_ids

    links = await client.get(
        f"/api/v1/persons/{seeded['survivor']}/parent-child", headers=viewer_headers
    )
    assert links.status_code == 200, links.text
    link_ids = {link["id"] for link in links.json()["data"]}
    assert str(seeded["live_link_id"]) in link_ids
    assert str(seeded["deleted_child_link_id"]) not in link_ids

    stats = await client.post(
        "/api/v1/persons/batch",
        headers=viewer_headers,
        json={"ids": [str(seeded["survivor"])], "include": "stats"},
    )
    assert stats.status_code == 200, stats.text
    assert stats.json()["data"][0]["stats"] == {"spouse_count": 1, "child_count": 1}


async def test_timeline_disagrees_with_the_marriages_read_on_the_same_edge(
    client: AsyncClient, seeded: dict[str, Any], viewer_headers: dict[str, str]
) -> None:
    """Two reads over one marriage row give a client two different answers.

    The timeline join filters the counterpart person; the marriages read does
    not. This test exists so the disagreement is one reading rather than an
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
    assert str(seeded["deleted_spouse"]) in partner_ids
