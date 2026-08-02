"""Person creation under the real non-bypass RLS session (ADR-008, migration 029).

``POST /api/v1/persons`` writes two rows in one flush: the ``persons`` row first, then
its ``clan_memberships`` row (the FK forces that order). Migration 029's ``persons_sel``
policy is membership-based, and Postgres evaluates a ``RETURNING`` row against the
**SELECT** policy — so any ``INSERT INTO persons … RETURNING`` inside that window is
rejected even though ``persons_ins``' ``WITH CHECK`` accepted the row.

029's docstring anticipated the ordering trap for ``WITH CHECK`` only; the ``RETURNING``
half went unnoticed because the app connects as a bypass role in every other test.

The fix keeps the policy exactly as 029 wrote it and removes the read instead: ``Person``
sets ``eager_defaults=False`` so SQLAlchemy does not read server defaults back. See
``app/models/person.py`` and ADR-038.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, Generator
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi import Header
from httpx2 import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import RlsSession, get_db
from app.core.rls import set_request_clan_id
from app.core.security import get_current_user
from app.main import create_app

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

PERSONS = "/api/v1/persons"


async def _override_current_user(
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Test-only stub: the bearer token IS the user id (no signature verification)."""
    assert authorization is not None, "test client must send an Authorization header"
    return {"sub": authorization.removeprefix("Bearer ")}


@pytest.fixture(autouse=True)
def _reset_clan_context() -> Generator[None]:
    set_request_clan_id(None)
    yield
    set_request_clan_id(None)


@pytest.fixture()
async def engine(migrated_db_url: str) -> AsyncGenerator[Any]:
    eng = create_async_engine(migrated_db_url)
    yield eng
    await eng.dispose()


@pytest.fixture()
def system_factory(engine: Any) -> async_sessionmaker[AsyncSession]:
    """Privileged (bypass) sessions — seeding only, never the code under test."""
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@pytest.fixture()
def rls_factory(engine: Any) -> async_sessionmaker[AsyncSession]:
    """The production request session: non-bypass role + ``app.clan_id`` GUC."""
    return async_sessionmaker(engine, sync_session_class=RlsSession, expire_on_commit=False)


async def _seed_clan(
    system_factory: async_sessionmaker[AsyncSession], label: str
) -> dict[str, Any]:
    """A clan with one approved editor (enough to create persons)."""
    clan_id, editor_id = uuid.uuid4(), uuid.uuid4()
    async with system_factory() as s:
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, :name, :slug)"),
            {"id": clan_id, "name": f"RLS Clan {label}", "slug": f"rls-{clan_id.hex[:8]}"},
        )
        await s.execute(
            sa.text("INSERT INTO user_profiles (id, email, display_name) VALUES (:id, :e, :n)"),
            {"id": editor_id, "e": f"{editor_id.hex[:8]}@example.com", "n": f"{label}-editor"},
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
async def clan_a(system_factory: async_sessionmaker[AsyncSession]) -> dict[str, Any]:
    return await _seed_clan(system_factory, "A")


@pytest.fixture()
async def clan_b(system_factory: async_sessionmaker[AsyncSession]) -> dict[str, Any]:
    return await _seed_clan(system_factory, "B")


@pytest.fixture()
async def rls_client(
    rls_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncClient]:
    """The API wired to the real ``RlsSession`` — as production runs it."""
    app = create_app()

    async def _override_db() -> AsyncGenerator[AsyncSession]:
        async with rls_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_current_user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


def _headers(seed: dict[str, Any]) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {seed['editor_id']}",
        "X-Current-Clan-Id": str(seed["clan_id"]),
    }


async def _create(client: AsyncClient, seed: dict[str, Any], **overrides: Any) -> Any:
    body: dict[str, Any] = {"full_name": "Cụ Nguyễn Văn Tổ", "gender": "male"}
    body.update(overrides)
    return await client.post(PERSONS, headers=_headers(seed), json=body)


# ── The bug ──────────────────────────────────────────────────────────────────


class TestPersonCreateUnderRls:
    async def test_create_person_succeeds_on_a_non_bypass_session(
        self, rls_client: AsyncClient, clan_a: dict[str, Any]
    ) -> None:
        """The headline. Before the fix this is a 500: the ORM's
        ``INSERT INTO persons … RETURNING created_at, updated_at, version`` is checked
        against ``persons_sel``, whose membership predicate cannot hold yet."""
        resp = await _create(rls_client, clan_a)
        assert resp.status_code == 201, resp.text
        data = resp.json()["data"]
        assert data["full_name"] == "Cụ Nguyễn Văn Tổ"
        assert data["version"] == 1

    async def test_created_person_is_readable_and_the_membership_row_exists(
        self,
        rls_client: AsyncClient,
        clan_a: dict[str, Any],
        system_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """The create must be complete, not merely unrejected: both rows land, and the
        person is visible on a fresh RLS transaction (so the membership really committed)."""
        person_id = (await _create(rls_client, clan_a)).json()["data"]["id"]

        got = await rls_client.get(f"{PERSONS}/{person_id}", headers=_headers(clan_a))
        assert got.status_code == 200, got.text

        async with system_factory() as s:
            memberships = await s.scalar(
                sa.text("SELECT count(*) FROM clan_memberships WHERE person_id = :p"),
                {"p": uuid.UUID(person_id)},
            )
        assert memberships == 1

    async def test_database_remains_the_timestamp_authority(
        self,
        rls_client: AsyncClient,
        clan_a: dict[str, Any],
        system_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """The fix must not move ``created_at``/``updated_at``/``version`` authority into
        Python: the columns keep their server defaults and the DB still fills them. Only
        the read-back was removed."""
        person_id = (await _create(rls_client, clan_a)).json()["data"]["id"]
        async with system_factory() as s:
            row = (
                await s.execute(
                    sa.text("SELECT created_at, updated_at, version FROM persons WHERE id = :p"),
                    {"p": uuid.UUID(person_id)},
                )
            ).one()
        assert row.created_at is not None and row.updated_at is not None
        assert row.version == 1

    async def test_update_after_create_still_works_under_rls(
        self, rls_client: AsyncClient, clan_a: dict[str, Any]
    ) -> None:
        """PATCH goes down the ``persons_upd`` path and bumps the optimistic-concurrency
        version by reading it back — the create fix must not strand ``version``."""
        created = (await _create(rls_client, clan_a)).json()["data"]
        resp = await rls_client.patch(
            f"{PERSONS}/{created['id']}",
            headers=_headers(clan_a),
            json={"birth_place": "Nam Định", "expected_version": created["version"]},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["version"] == created["version"] + 1


# ── Two-sided clan isolation, on read and on write ───────────────────────────


class TestTwoSidedIsolation:
    async def test_neither_clan_can_read_the_other_s_created_person(
        self, rls_client: AsyncClient, clan_a: dict[str, Any], clan_b: dict[str, Any]
    ) -> None:
        a_id = (await _create(rls_client, clan_a, full_name="A's person")).json()["data"]["id"]
        b_id = (await _create(rls_client, clan_b, full_name="B's person")).json()["data"]["id"]

        async def _get(seed: dict[str, Any], person_id: str) -> int:
            resp = await rls_client.get(f"{PERSONS}/{person_id}", headers=_headers(seed))
            return resp.status_code

        assert await _get(clan_a, a_id) == 200
        assert await _get(clan_b, b_id) == 200
        assert await _get(clan_a, b_id) == 404
        assert await _get(clan_b, a_id) == 404

    async def test_neither_clan_can_write_the_other_s_created_person(
        self, rls_client: AsyncClient, clan_a: dict[str, Any], clan_b: dict[str, Any]
    ) -> None:
        a_id = (await _create(rls_client, clan_a, full_name="A's person")).json()["data"]["id"]
        b_id = (await _create(rls_client, clan_b, full_name="B's person")).json()["data"]["id"]

        for attacker, target in ((clan_a, b_id), (clan_b, a_id)):
            resp = await rls_client.patch(
                f"{PERSONS}/{target}",
                headers=_headers(attacker),
                json={"birth_place": "Stolen", "expected_version": 1},
            )
            assert resp.status_code == 404, resp.text

    async def test_the_list_endpoint_never_shows_the_other_clan_s_person(
        self, rls_client: AsyncClient, clan_a: dict[str, Any], clan_b: dict[str, Any]
    ) -> None:
        a_id = (await _create(rls_client, clan_a, full_name="A's person")).json()["data"]["id"]
        b_id = (await _create(rls_client, clan_b, full_name="B's person")).json()["data"]["id"]

        for seed, mine, theirs in ((clan_a, a_id, b_id), (clan_b, b_id, a_id)):
            listed = await rls_client.get(PERSONS, headers=_headers(seed))
            ids = {row["id"] for row in listed.json()["data"]}
            assert ids == {mine}, (seed["clan_id"], ids, theirs)


# ── The property the fix must NOT break ──────────────────────────────────────


class TestMembershipRemovalStillHidesThePerson:
    """The isolation property a widened ``persons_sel`` would silently destroy.

    The tempting fix for this bug is ``persons_sel USING (_MEMBER OR
    created_by_clan_id = GUC)``. It makes the error go away and permanently grants the
    ORIGIN clan visibility, membership or not — so removing someone's membership would
    no longer hide them. These tests fail under that fix and under the narrower
    "visible while memberless" variant of it.
    """

    async def test_removing_the_membership_hides_the_person_from_its_origin_clan(
        self,
        rls_client: AsyncClient,
        clan_a: dict[str, Any],
        system_factory: async_sessionmaker[AsyncSession],
        rls_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        person_id = uuid.UUID((await _create(rls_client, clan_a)).json()["data"]["id"])
        assert (
            await rls_client.get(f"{PERSONS}/{person_id}", headers=_headers(clan_a))
        ).status_code == 200

        async with system_factory() as s:
            await s.execute(
                sa.text("DELETE FROM clan_memberships WHERE person_id = :p"), {"p": person_id}
            )
            await s.commit()

        # HTTP: gone. (The application-layer join alone would also do this…)
        assert (
            await rls_client.get(f"{PERSONS}/{person_id}", headers=_headers(clan_a))
        ).status_code == 404

        # …so assert it at the DB layer too, where only the RLS policy can hide it.
        set_request_clan_id(clan_a["clan_id"])
        async with rls_factory() as s:
            visible = (await s.execute(sa.text("SELECT id FROM persons"))).scalars().all()
        assert person_id not in set(visible), (
            "persons_sel let the origin clan keep reading a person with no membership — "
            "the isolation property migration 029 established has been weakened"
        )

    async def test_a_memberless_person_created_by_the_clan_is_invisible_at_the_db(
        self,
        clan_a: dict[str, Any],
        system_factory: async_sessionmaker[AsyncSession],
        rls_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """``created_by_clan_id`` is provenance, never visibility — not even for a person
        that has no memberships at all (the window the "transient escape hatch" variant
        would have opened)."""
        person_id = uuid.uuid4()
        async with system_factory() as s:
            await s.execute(
                sa.text(
                    "INSERT INTO persons (id, full_name, created_by_clan_id, created_by) "
                    "VALUES (:i, 'Memberless', :c, :a)"
                ),
                {"i": person_id, "c": clan_a["clan_id"], "a": clan_a["editor_id"]},
            )
            await s.commit()

        set_request_clan_id(clan_a["clan_id"])
        async with rls_factory() as s:
            visible = (await s.execute(sa.text("SELECT id FROM persons"))).scalars().all()
        assert person_id not in set(visible)


# ── Why the policy could not simply be left to handle RETURNING ───────────────


class TestReturningIsStillRejectedByThePolicy:
    async def test_raw_insert_returning_before_the_membership_row_is_still_denied(
        self, clan_a: dict[str, Any], rls_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """Pins the constraint the fix works *within*, and documents it for the next
        author: ``persons_sel`` is deliberately unchanged, so reading a ``persons`` row
        back before its membership exists is still rejected. Any new write path against
        ``persons`` must either insert the membership first or avoid ``RETURNING``
        (see ``Person.__mapper_args__``)."""
        set_request_clan_id(clan_a["clan_id"])
        async with rls_factory() as s:
            # Plain INSERT: accepted by persons_ins (created_by_clan_id = GUC).
            await s.execute(
                sa.text(
                    "INSERT INTO persons (id, full_name, created_by_clan_id, created_by) "
                    "VALUES (:i, 'Plain', :c, :a)"
                ),
                {"i": uuid.uuid4(), "c": clan_a["clan_id"], "a": clan_a["editor_id"]},
            )
            # The same INSERT plus RETURNING: rejected, because the returned row is
            # matched against persons_sel and no membership row exists yet.
            with pytest.raises(Exception, match="row-level security"):
                await s.execute(
                    sa.text(
                        "INSERT INTO persons (id, full_name, created_by_clan_id, created_by) "
                        "VALUES (:i, 'Returning', :c, :a) RETURNING created_at"
                    ),
                    {"i": uuid.uuid4(), "c": clan_a["clan_id"], "a": clan_a["editor_id"]},
                )
            await s.rollback()

    async def test_the_orm_insert_emits_no_returning_for_persons(
        self, clan_a: dict[str, Any], rls_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """The mechanical assertion behind the fix: whatever else changes, the compiled
        ``persons`` INSERT must not carry a RETURNING clause."""
        from sqlalchemy import event

        from app.models.person import Person as PersonModel

        statements: list[str] = []

        async with rls_factory() as s:
            sync_session = await s.run_sync(lambda sess: sess)

            @event.listens_for(sync_session.get_bind(), "before_cursor_execute")
            def _capture(  # type: ignore[no-untyped-def]
                conn, cursor, statement, parameters, context, executemany
            ) -> None:
                statements.append(statement)

            set_request_clan_id(clan_a["clan_id"])
            s.add(
                PersonModel(
                    id=uuid.uuid4(),
                    full_name="No returning",
                    created_by_clan_id=clan_a["clan_id"],
                    created_by=clan_a["editor_id"],
                )
            )
            await s.flush()
            await s.rollback()

        inserts = [q for q in statements if "INSERT INTO persons" in q]
        assert inserts, statements
        assert not any("RETURNING" in q.upper() for q in inserts), inserts
