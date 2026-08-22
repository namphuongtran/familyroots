"""One pending identity claim per user GLOBALLY — across clans (S-012, ADR-042 § 5).

``uq_identity_claim_user_pending`` (``app/models/identity_claim.py:17-23``, created in
``migrations/versions/001_initial.py:770``) is unique on ``user_id`` where
``status = 'PENDING'``. It carries no clan, and ADR-007 calls it the spam guard: **at most
one pending claim per user, across every clan on the platform.** That makes this table the
one place in the schema where a clan-keyed policy would have broken an invariant instead of
protecting one, and it is why seed S-011 had to decide the policy shape before S-012 could
build anything.

The invariant is enforced in two places and this file pins both, because they fail
differently:

1. **The application guard.** ``ClaimCommandHandler.submit_claim`` calls
   ``has_pending_claims`` (``claim_handlers.py:44-46`` → ``claim_repository.py:66-72``,
   ``WHERE user_id = … AND status = 'PENDING'``, no clan) and raises a clean
   ``409 user_already_has_pending_claim``. This is where the product checks it, so this is
   where it must stay checkable.
2. **The unique index.** Even with the handler bypassed entirely, a second pending row for
   the same user is refused by Postgres.

**Why this is the test that this table can fail in a way no other table can.** ADR-042 § 5
worked out what a clan-keyed policy would actually have cost here, and it is not the index:
Postgres runs unique and foreign-key checks outside row security, so the index would have
survived. What would not have survived is guard 1. Under a policy keyed on the person's
origin clan, the ``has_pending_claims`` SELECT goes blind to a pending claim held in another
clan, the handler sails past its own guard, and the documented 409 becomes an integrity error
raised from the flush. The invariant would still hold and would stop being **checkable where
the product checks it** — a green suite and a broken contract.

Migration 033's deny-all policy leaves both guards untouched, because the claim handlers stay
on the privileged session. So these tests must read identically before and after that
migration. That is the point of them, and it is also why they carry no ``RlsSession``: a test
that had to know about the seam would be evidence that the seam had reached this table.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
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

from app.core.database import get_db, get_system_db
from app.core.security import get_current_user
from app.main import create_app

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture()
async def engine(migrated_db_url: str) -> AsyncGenerator[AsyncEngine]:
    eng = create_async_engine(migrated_db_url)
    yield eng
    await eng.dispose()


async def _override_current_user(
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    assert authorization is not None, "test client must send an Authorization header"
    return {"sub": authorization.removeprefix("Bearer ")}


@pytest.fixture()
async def http(engine: AsyncEngine) -> AsyncGenerator[AsyncClient]:
    """Production's session split: ``get_db`` privileged is NOT used here — both the
    request session and the system session point at the test engine, with the claim
    handlers on the system one exactly as ``dependencies.py:144`` wires them."""
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    app = create_app()

    async def _override_db() -> AsyncGenerator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_system_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_current_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


async def _clan(conn: AsyncConnection) -> uuid.UUID:
    cid = uuid.uuid4()
    await conn.execute(
        sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :s)"),
        {"id": cid, "s": f"c{cid.hex[:10]}"},
    )
    return cid


async def _user(conn: AsyncConnection) -> uuid.UUID:
    uid = uuid.uuid4()
    await conn.execute(
        sa.text("INSERT INTO user_profiles (id, email, display_name) VALUES (:id, :e, 'U')"),
        {"id": uid, "e": f"u-{uid.hex[:12]}@example.com"},
    )
    return uid


async def _person(conn: AsyncConnection, clan_id: uuid.UUID) -> uuid.UUID:
    pid = uuid.uuid4()
    await conn.execute(
        sa.text(
            "INSERT INTO persons (id, full_name, gender, created_by_clan_id, created_by) "
            "VALUES (:id, 'P', 'male', :c, :cb)"
        ),
        {"id": pid, "c": clan_id, "cb": uuid.uuid4()},
    )
    await conn.execute(
        sa.text(
            "INSERT INTO clan_memberships (id, person_id, clan_id, role) "
            "VALUES (:id, :p, :c, 'blood')"
        ),
        {"id": uuid.uuid4(), "p": pid, "c": clan_id},
    )
    return pid


async def _approve_role(conn: AsyncConnection, user_id: uuid.UUID, clan_id: uuid.UUID) -> None:
    await conn.execute(
        sa.text(
            "INSERT INTO user_clan_roles "
            "(user_id, clan_id, role, is_approved, approved_by, approved_at) "
            "VALUES (:u, :c, 'viewer', true, :u, now())"
        ),
        {"u": user_id, "c": clan_id},
    )


class _TwoClans:
    def __init__(
        self,
        clan_a: uuid.UUID,
        clan_b: uuid.UUID,
        person_a: uuid.UUID,
        person_b: uuid.UUID,
        user: uuid.UUID,
    ) -> None:
        self.clan_a = clan_a
        self.clan_b = clan_b
        self.person_a = person_a
        self.person_b = person_b
        self.user = user


async def _seed(engine: AsyncEngine) -> _TwoClans:
    """One user who is an approved viewer of BOTH clans, and one claimable person in each.

    The dual membership is what lets the same caller drive the second request with a
    different ``X-Current-Clan-Id``, which is the cross-clan half of this test. Without it
    the second request would be refused by ``get_current_clan_id`` for the wrong reason.
    """
    async with engine.begin() as conn:
        clan_a, clan_b = await _clan(conn), await _clan(conn)
        user = await _user(conn)
        await _approve_role(conn, user, clan_a)
        await _approve_role(conn, user, clan_b)
        person_a = await _person(conn, clan_a)
        person_b = await _person(conn, clan_b)
    return _TwoClans(clan_a, clan_b, person_a, person_b, user)


async def test_second_pending_claim_from_another_clan_is_rejected(
    engine: AsyncEngine, http: AsyncClient
) -> None:
    """The named test. A user with a pending claim on a clan-A person switches to clan B and
    claims a clan-B person. The second request is a clean ``409
    user_already_has_pending_claim``, and no second row is written.

    The switch is real, not simulated: the same caller sends a different
    ``X-Current-Clan-Id``, so ``POST /persons/{id}/claim`` runs under clan B's context
    (``app/api/v1/persons.py:417-424`` resolves ``RequireViewer`` against the CLAIMANT's
    active clan). Nothing in the request mentions clan A. Only the global index and the
    clan-free ``has_pending_claims`` query connect the two.
    """
    seed = await _seed(engine)

    first = await http.post(
        f"/api/v1/persons/{seed.person_a}/claim",
        json={"requester_note": "clan A"},
        headers={"Authorization": f"Bearer {seed.user}", "X-Current-Clan-Id": str(seed.clan_a)},
    )
    assert first.status_code == 201, first.text
    first_id = first.json()["data"]["id"]

    second = await http.post(
        f"/api/v1/persons/{seed.person_b}/claim",
        json={"requester_note": "clan B"},
        headers={"Authorization": f"Bearer {seed.user}", "X-Current-Clan-Id": str(seed.clan_b)},
    )
    assert second.status_code == 409, second.text
    assert second.json()["error"]["code"] == "user_already_has_pending_claim", second.text

    async with engine.connect() as conn:
        rows = (
            (
                await conn.execute(
                    sa.text(
                        "SELECT id FROM identity_claims WHERE user_id = :u AND status = 'PENDING'"
                    ),
                    {"u": seed.user},
                )
            )
            .scalars()
            .all()
        )
    assert [str(r) for r in rows] == [first_id], (
        "the clan-B submit must not have created a second pending claim"
    )


async def test_the_first_claim_still_succeeds_from_the_other_clan_once_it_is_free(
    engine: AsyncEngine, http: AsyncClient
) -> None:
    """The other side of the guard, so the test above cannot pass by refusing everything.

    Cancel the clan-A claim, then the clan-B submit succeeds. A guard that always said 409
    would look identical to a working one without this.
    """
    seed = await _seed(engine)

    first = await http.post(
        f"/api/v1/persons/{seed.person_a}/claim",
        json={"requester_note": "clan A"},
        headers={"Authorization": f"Bearer {seed.user}", "X-Current-Clan-Id": str(seed.clan_a)},
    )
    assert first.status_code == 201, first.text

    cancelled = await http.delete(
        f"/api/v1/claims/{first.json()['data']['id']}",
        headers={"Authorization": f"Bearer {seed.user}", "X-Current-Clan-Id": str(seed.clan_a)},
    )
    assert cancelled.status_code == 204, cancelled.text

    second = await http.post(
        f"/api/v1/persons/{seed.person_b}/claim",
        json={"requester_note": "clan B"},
        headers={"Authorization": f"Bearer {seed.user}", "X-Current-Clan-Id": str(seed.clan_b)},
    )
    assert second.status_code == 201, second.text


async def test_the_index_itself_is_global_with_the_handler_bypassed(
    engine: AsyncEngine,
) -> None:
    """Guard 2, measured with no application code in the path at all.

    Two raw INSERTs on the privileged connection, for the same user and two persons whose
    origin clans differ. The second violates ``uq_identity_claim_user_pending``. This is the
    half ADR-042 § 5 says a clan-keyed policy would NOT have broken, and it is worth pinning
    anyway: it is what turns a broken application guard into an integrity error rather than a
    duplicate row.
    """
    seed = await _seed(engine)

    async with engine.begin() as conn:
        await conn.execute(
            sa.text(
                "INSERT INTO identity_claims (id, user_id, person_id, status) "
                "VALUES (:id, :u, :p, 'PENDING')"
            ),
            {"id": uuid.uuid4(), "u": seed.user, "p": seed.person_a},
        )

    with pytest.raises(sa.exc.IntegrityError) as ei:
        async with engine.begin() as conn:
            await conn.execute(
                sa.text(
                    "INSERT INTO identity_claims (id, user_id, person_id, status) "
                    "VALUES (:id, :u, :p, 'PENDING')"
                ),
                {"id": uuid.uuid4(), "u": seed.user, "p": seed.person_b},
            )
    assert "uq_identity_claim_user_pending" in str(ei.value)
