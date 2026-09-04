"""RLS layer-2 Phase 8 (ADR-042): identity_claims DENIES the request role outright.

Migration 033 gives this table one policy, ``identity_claims_system_session_only``,
``FOR ALL USING (false) WITH CHECK (false)``. **Read that as a tripwire, not as clan
isolation.** The nine clan-isolated tables compare a row's clan to the ``app.clan_id`` GUC.
This table has no ``clan_id`` to compare (``app/models/identity_claim.py`` reaches a clan
only through ``person_id`` at ``:32-36``), every claim path is deliberately privileged
(``app/infrastructure/dependencies.py:144``, ``:149``), and two of the four routes resolve
no clan at all. ADR-042 chose the application layer as the only clan isolation here and
shipped the deny-all policy alongside it to make ONE future defect loud: a claims query
wired to ``get_db`` instead of ``get_system_db``.

So "two-sided" means something different on this table, and the difference is worth stating
rather than glossing. On ``clan_invitations`` two-sided means A sees its row and not B's,
and B the reverse. Here it means **neither clan sees either row**, which is a claim a test
against an empty table would also satisfy. Every denial test below therefore ends with a
privileged read proving the rows were there the whole time. Without that control these tests
would pass over a table the migration had emptied.

What is pinned here:

* the request role reads nothing under clan A, nothing under clan B, and nothing with no
  clan selected — while the privileged session reads both rows;
* the request role's INSERT is REJECTED with an error, not silently dropped;
* its UPDATE and DELETE reach no row, checked privileged, because a policy that hides a row
  also hides the damage;
* the system session still reads and writes the table, and the four claim routes still work
  end to end over HTTP with the real session split (``get_db`` on the RLS request session,
  ``get_system_db`` privileged) — this is the half that would break if someone "fixed" the
  policy by pointing the handlers at the request session;
* the ``ON DELETE CASCADE`` from ``persons`` still reaches this table under the policy.
  ADR-042 § "What migration 033 must build" item 6 asked for that to be measured rather than taken
  from the Postgres manual, because a referential action that RLS could block would strand
  claim rows behind a deleted person.

The cross-clan one-pending-claim invariant lives in
``test_claim_cross_clan_pending_uniqueness.py``, because it is a property of the table that
holds independently of any policy.
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
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.database import RlsSession, get_db, get_system_db
from app.core.rls import set_request_clan_id
from app.core.security import get_current_user
from app.main import create_app

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


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


def _rls(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """A session with the production RLS seam attached (SET LOCAL ROLE + app.clan_id)."""
    return async_sessionmaker(
        engine, sync_session_class=RlsSession, expire_on_commit=False, class_=AsyncSession
    )


def _system(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """The privileged session class, exactly what ``get_system_db`` hands the claim
    handlers (``app/core/database.py:86-93``): no seam, so no role drop and no GUC."""
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


# ── seeding (privileged: bypasses the policy) ─────────────────────────────────


async def _clan(conn: AsyncConnection, clan_id: uuid.UUID) -> None:
    await conn.execute(
        sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :s)"),
        {"id": clan_id, "s": f"c{clan_id.hex[:10]}"},
    )


async def _user(conn: AsyncConnection) -> uuid.UUID:
    uid = uuid.uuid4()
    await conn.execute(
        sa.text("INSERT INTO user_profiles (id, email, display_name) VALUES (:id, :e, 'U')"),
        {"id": uid, "e": f"u-{uid.hex[:12]}@example.com"},
    )
    return uid


async def _person(conn: AsyncConnection, clan_id: uuid.UUID, *, member: bool = True) -> uuid.UUID:
    """A person whose ORIGIN clan is *clan_id*. ``member=True`` also records the
    ``clan_memberships`` row, which is what ``persons_sel``/``persons_del`` key on
    (``029_rls_persons.py:45-48``) — provenance alone does not make a person visible."""
    pid = uuid.uuid4()
    await conn.execute(
        sa.text(
            "INSERT INTO persons (id, full_name, gender, created_by_clan_id, created_by) "
            "VALUES (:id, 'P', 'male', :c, :cb)"
        ),
        {"id": pid, "c": clan_id, "cb": uuid.uuid4()},
    )
    if member:
        await conn.execute(
            sa.text(
                "INSERT INTO clan_memberships (id, person_id, clan_id, role) "
                "VALUES (:id, :p, :c, 'blood')"
            ),
            {"id": uuid.uuid4(), "p": pid, "c": clan_id},
        )
    return pid


async def _claim(
    conn: AsyncConnection, user_id: uuid.UUID, person_id: uuid.UUID, status: str = "PENDING"
) -> uuid.UUID:
    cid = uuid.uuid4()
    await conn.execute(
        sa.text(
            "INSERT INTO identity_claims (id, user_id, person_id, status, requester_note) "
            "VALUES (:id, :u, :p, :st, 'I am this person')"
        ),
        {"id": cid, "u": user_id, "p": person_id, "st": status},
    )
    return cid


class _Seed:
    """Two clans, one person and one pending claim in each."""

    def __init__(
        self,
        clan_a: uuid.UUID,
        clan_b: uuid.UUID,
        person_a: uuid.UUID,
        person_b: uuid.UUID,
        claim_a: uuid.UUID,
        claim_b: uuid.UUID,
    ) -> None:
        self.clan_a = clan_a
        self.clan_b = clan_b
        self.person_a = person_a
        self.person_b = person_b
        self.claim_a = claim_a
        self.claim_b = claim_b


async def _seed_two(engine: AsyncEngine) -> _Seed:
    clan_a, clan_b = uuid.uuid4(), uuid.uuid4()
    async with engine.begin() as conn:  # privileged connection — RLS-bypassing
        await _clan(conn, clan_a)
        await _clan(conn, clan_b)
        user_a, user_b = await _user(conn), await _user(conn)
        person_a = await _person(conn, clan_a)
        person_b = await _person(conn, clan_b)
        # Two DIFFERENT users: uq_identity_claim_user_pending allows one pending claim per
        # user GLOBALLY, so one user could not hold both of these at once. That index is
        # the subject of test_claim_cross_clan_pending_uniqueness.py.
        claim_a = await _claim(conn, user_a, person_a)
        claim_b = await _claim(conn, user_b, person_b)
    return _Seed(clan_a, clan_b, person_a, person_b, claim_a, claim_b)


async def _privileged_claim_ids(engine: AsyncEngine, seed: _Seed) -> set[uuid.UUID]:
    """The control every denial test needs: prove the rows exist, from a session the
    policy does not apply to. ``count(*) == 0`` under the request role means nothing
    unless the table demonstrably had rows in it."""
    async with engine.connect() as conn:
        return set(
            (
                await conn.execute(
                    sa.text("SELECT id FROM identity_claims WHERE id IN (:a, :b)"),
                    {"a": seed.claim_a, "b": seed.claim_b},
                )
            ).scalars()
        )


# ── the request role is denied, whichever clan is selected ────────────────────


async def test_request_role_reads_nothing_under_either_clan(engine: AsyncEngine) -> None:
    """Under clan A the request role sees neither A's claim nor B's, and under clan B the
    same. The clan that OWNS a claim gets no more access than the clan that does not, which
    is what makes this a lockout rather than isolation.

    The privileged read at the end is load-bearing: without it this test would pass on an
    empty table, and a migration that dropped the rows would look like a working policy.
    """
    seed = await _seed_two(engine)
    assert await _privileged_claim_ids(engine, seed) == {seed.claim_a, seed.claim_b}

    rls = _rls(engine)
    for clan in (seed.clan_a, seed.clan_b):
        set_request_clan_id(clan)
        async with rls() as s:
            assert await s.scalar(sa.text("SELECT current_user")) == "familyroots_app"
            visible = set((await s.execute(sa.text("SELECT id FROM identity_claims"))).scalars())
        assert visible == set(), f"clan {clan} saw claim rows under a deny-all policy: {visible}"

    # ...and they were there all along.
    assert await _privileged_claim_ids(engine, seed) == {seed.claim_a, seed.claim_b}


async def test_request_role_is_denied_with_no_clan_selected(engine: AsyncEngine) -> None:
    """``GET /m/claims`` and ``DELETE /m/claims/{id}`` resolve no clan at all
    (``app/api/v1/claims.py:35-43``, ``:51-57``). If either were ever wired to ``get_db``
    this is the shape of the failure: an empty GUC, zero rows, and no error — a 200 with
    missing data. Pinned so the silent version cannot come back.
    """
    seed = await _seed_two(engine)
    rls = _rls(engine)
    set_request_clan_id(None)
    async with rls() as s:
        assert await s.scalar(sa.text("SELECT current_setting('app.clan_id', true)")) == ""
        assert await s.scalar(sa.text("SELECT count(*) FROM identity_claims")) == 0
    assert await _privileged_claim_ids(engine, seed) == {seed.claim_a, seed.claim_b}


async def test_request_role_insert_is_rejected(engine: AsyncEngine) -> None:
    """``WITH CHECK (false)`` RAISES. A submit wired to the request session fails loudly in
    the engineer's own test run instead of writing a claim nobody can read back."""
    seed = await _seed_two(engine)
    async with engine.begin() as conn:
        user_c = await _user(conn)

    rls = _rls(engine)
    set_request_clan_id(seed.clan_a)  # the claimed person's OWN origin clan
    async with rls() as s:
        with pytest.raises(sa.exc.DBAPIError) as ei:
            await s.execute(
                sa.text(
                    "INSERT INTO identity_claims (id, user_id, person_id, status) "
                    "VALUES (:id, :u, :p, 'PENDING')"
                ),
                {"id": uuid.uuid4(), "u": user_c, "p": seed.person_a},
            )
            await s.flush()
        assert "row-level security" in str(ei.value).lower()


async def test_request_role_update_touches_no_row(engine: AsyncEngine) -> None:
    """An UPDATE under the request role matches nothing, and the row is unchanged — checked
    privileged, because the policy that hid the row would also hide the damage."""
    seed = await _seed_two(engine)
    rls = _rls(engine)
    set_request_clan_id(seed.clan_a)
    async with rls() as s:
        updated = (
            (
                await s.execute(
                    sa.text(
                        "UPDATE identity_claims SET status = 'CANCELLED' "
                        "WHERE id = :id RETURNING id"
                    ),
                    {"id": seed.claim_a},
                )
            )
            .scalars()
            .all()
        )
        assert list(updated) == []
        await s.commit()

    async with engine.connect() as conn:
        status = await conn.scalar(
            sa.text("SELECT status FROM identity_claims WHERE id = :id"), {"id": seed.claim_a}
        )
    assert status == "PENDING"


async def test_request_role_delete_touches_no_row(engine: AsyncEngine) -> None:
    """The blunt version. Under any clan a DELETE reaches no claim."""
    seed = await _seed_two(engine)
    rls = _rls(engine)
    set_request_clan_id(seed.clan_a)
    async with rls() as s:
        await s.execute(
            sa.text("DELETE FROM identity_claims WHERE id IN (:a, :b)"),
            {"a": seed.claim_a, "b": seed.claim_b},
        )
        await s.commit()

    assert await _privileged_claim_ids(engine, seed) == {seed.claim_a, seed.claim_b}


# ── the system session, which is where the workflow actually runs ─────────────


async def test_system_session_still_reads_and_writes(engine: AsyncEngine) -> None:
    """``ENABLE``, not ``FORCE``: the privileged session bypasses the policy, so the claim
    handlers keep full CRUD. If this ever fails, the workflow is down, not merely locked."""
    seed = await _seed_two(engine)
    system = _system(engine)
    async with engine.begin() as conn:
        user_c = await _user(conn)
        person_c = await _person(conn, seed.clan_a)

    async with system() as s:
        assert await s.scalar(sa.text("SELECT current_user")) != "familyroots_app"
        assert set(
            (
                await s.execute(
                    sa.text("SELECT id FROM identity_claims WHERE id IN (:a, :b)"),
                    {"a": seed.claim_a, "b": seed.claim_b},
                )
            ).scalars()
        ) == {seed.claim_a, seed.claim_b}

        new_id = uuid.uuid4()
        await s.execute(
            sa.text(
                "INSERT INTO identity_claims (id, user_id, person_id, status) "
                "VALUES (:id, :u, :p, 'PENDING')"
            ),
            {"id": new_id, "u": user_c, "p": person_c},
        )
        await s.execute(
            sa.text("UPDATE identity_claims SET status = 'APPROVED' WHERE id = :id"),
            {"id": new_id},
        )
        await s.commit()
        assert (
            await s.scalar(
                sa.text("SELECT status FROM identity_claims WHERE id = :id"), {"id": new_id}
            )
            == "APPROVED"
        )


# ── the cascade ADR-042 asked to be measured rather than assumed ──────────────


async def test_person_delete_still_cascades_into_claims_under_the_policy(
    engine: AsyncEngine,
) -> None:
    """ADR-042 § "What the deny-all migration must build" item 6.

    ``identity_claims.person_id`` is ``ON DELETE CASCADE``
    (``app/models/identity_claim.py:32-36``). Postgres runs referential actions outside row
    security, so the cascade should still fire even though the request role can neither read
    nor write the claim it is deleting. The ADR took that from the manual and asked for it to
    be run. It is run here: the person is deleted UNDER THE REQUEST ROLE (which needs the
    ``persons_del`` membership predicate to admit it), and the claim goes with it.

    If this ever fails, the deny-all policy is stranding claim rows behind deleted persons
    and ADR-042 is wrong on that point.
    """
    clan = uuid.uuid4()
    async with engine.begin() as conn:
        await _clan(conn, clan)
        user = await _user(conn)
        person = await _person(conn, clan, member=True)
        claim = await _claim(conn, user, person)

    rls = _rls(engine)
    set_request_clan_id(clan)
    async with rls() as s:
        deleted = (
            (
                await s.execute(
                    sa.text("DELETE FROM persons WHERE id = :id RETURNING id"), {"id": person}
                )
            )
            .scalars()
            .all()
        )
        # Guard against a vacuous pass: if the person delete itself were blocked, the claim
        # would survive for a reason that has nothing to do with the cascade.
        assert list(deleted) == [person], "persons_del did not admit the row; test proves nothing"
        await s.commit()

    async with engine.connect() as conn:
        assert (
            await conn.scalar(
                sa.text("SELECT count(*) FROM identity_claims WHERE id = :id"), {"id": claim}
            )
            == 0
        ), "the ON DELETE CASCADE did not reach identity_claims under the deny-all policy"


# ── the routes, end to end, on the real session split ─────────────────────────


async def _override_current_user(
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    assert authorization is not None, "test client must send an Authorization header"
    return {"sub": authorization.removeprefix("Bearer ")}


@pytest.fixture()
async def http(engine: AsyncEngine) -> AsyncGenerator[AsyncClient]:
    """A client wired the way production is: ``get_db`` on the RLS request session (seam
    attached, role dropped, GUC set) and ``get_system_db`` privileged.

    ``test_claims_audit.py:73-76`` points BOTH at the privileged session, which is fine for
    what that file measures and useless here — it would pass with or without migration 033.
    Keeping the split is the whole point: these routes must work while the request role is
    locked out of the table.
    """
    rls_factory = _rls(engine)
    system_factory = _system(engine)
    app = create_app()

    async def _override_db() -> AsyncGenerator[AsyncSession]:
        async with rls_factory() as session:
            yield session

    async def _override_system_db() -> AsyncGenerator[AsyncSession]:
        async with system_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_system_db] = _override_system_db
    app.dependency_overrides[get_current_user] = _override_current_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


async def test_claim_routes_still_work_with_the_request_role_locked_out(
    engine: AsyncEngine, http: AsyncClient
) -> None:
    """Submit, list-mine, list-for-clan, approve — over real HTTP, with ``get_db`` on the
    RLS request session that migration 033 denies.

    This is ADR-042 § "What migration 033 must build" item 3, and it is the test that would catch
    the mistake of "fixing" the lockout by re-pointing the claim handlers at ``get_db``.
    ``GET /api/v1/claims`` is the sharpest of the four: it resolves NO clan, so on the
    request session it would answer ``200`` with an empty list and no error at all.
    """
    clan = uuid.uuid4()
    async with engine.begin() as conn:
        await _clan(conn, clan)
        admin = await _user(conn)
        claimant = await _user(conn)
        person = await _person(conn, clan, member=True)
        for uid, role in ((admin, "admin"), (claimant, "viewer")):
            await conn.execute(
                sa.text(
                    "INSERT INTO user_clan_roles "
                    "(user_id, clan_id, role, is_approved, approved_by, approved_at) "
                    "VALUES (:u, :c, :r, true, :u, now())"
                ),
                {"u": uid, "c": clan, "r": role},
            )

    claimant_headers = {
        "Authorization": f"Bearer {claimant}",
        "X-Current-Clan-Id": str(clan),
    }
    admin_headers = {"Authorization": f"Bearer {admin}", "X-Current-Clan-Id": str(clan)}

    submitted = await http.post(
        f"/api/v1/persons/{person}/claim",
        json={"requester_note": "I am this person"},
        headers=claimant_headers,
    )
    assert submitted.status_code == 201, submitted.text
    claim_id = submitted.json()["data"]["id"]

    mine = await http.get("/api/v1/claims", headers=claimant_headers)
    assert mine.status_code == 200, mine.text
    assert [c["id"] for c in mine.json()["data"]] == [claim_id], (
        "GET /claims resolves no clan; an empty list here means the query ran on the "
        "request session and migration 033 hid the row"
    )

    queue = await http.get(f"/api/v1/clans/{clan}/claims", headers=admin_headers)
    assert queue.status_code == 200, queue.text
    assert claim_id in [c["id"] for c in queue.json()["data"]]

    approved = await http.post(
        f"/api/v1/clans/{clan}/claims/{claim_id}/approve",
        json={"reviewer_note": "confirmed"},
        headers=admin_headers,
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["data"]["status"] == "APPROVED"
