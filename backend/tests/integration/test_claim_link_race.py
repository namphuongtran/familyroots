"""M1 regression — concurrent identity-claim approvals for the same person.

`user_profiles.person_id` is UNIQUE. Two admins approving two different users'
claims for the SAME person both passed the plain `is_person_linked` SELECT guard,
then raced to the unique index — the loser hit a raw IntegrityError (HTTP 500) after
its side-effects (auto-reject of sibling claims) had already run.

Fix: `lock_person()` takes a row lock so the approvals serialize; the loser observes
`is_person_linked() is True` under the lock and fails as a clean `ConflictError`,
before any mutation. (A global IntegrityError→409 handler is the backstop for any
unguarded path — unit-tested separately.)
"""

import asyncio
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.application.person.claim_handlers import ClaimCommandHandler
from app.domain.shared.exceptions import ConflictError  # mapped to 409 by the domain handler
from app.infrastructure.event_dispatcher import create_event_dispatcher
from app.infrastructure.persistence.claim_repository import SqlAlchemyClaimRepository
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork


@pytest.fixture()
async def engine(migrated_db_url: str) -> AsyncGenerator[AsyncEngine]:
    eng = create_async_engine(migrated_db_url)
    yield eng
    await eng.dispose()


def _maker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


def _handler(db: AsyncSession) -> ClaimCommandHandler:
    uow = SqlAlchemyUnitOfWork(db, create_event_dispatcher(db))
    return ClaimCommandHandler(SqlAlchemyClaimRepository(db), uow)


async def _seed(maker: async_sessionmaker[AsyncSession]) -> dict[str, Any]:
    """A clan admin, a person in that clan, and two users each with a PENDING
    claim for that same person."""
    clan_id, admin_id, person_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    user1, user2 = uuid.uuid4(), uuid.uuid4()
    claim1, claim2 = uuid.uuid4(), uuid.uuid4()
    async with maker() as s:
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :sg)"),
            {"id": clan_id, "sg": f"c{clan_id.hex[:6]}"},
        )
        for uid in (admin_id, user1, user2):
            await s.execute(
                sa.text(
                    "INSERT INTO user_profiles (id, email, display_name) VALUES (:id, :em, 'U')"
                ),
                {"id": uid, "em": f"u-{uid.hex[:8]}@ex.com"},
            )
        await s.execute(
            sa.text(
                "INSERT INTO user_clan_roles "
                "(user_id, clan_id, role, is_approved, approved_by, approved_at) "
                "VALUES (:u, :c, 'admin', true, :u, :t)"
            ),
            {"u": admin_id, "c": clan_id, "t": datetime.now(UTC)},
        )
        await s.execute(
            sa.text(
                "INSERT INTO persons (id, full_name, gender, created_by_clan_id, created_by) "
                "VALUES (:id, 'P', 'unknown', :c, :by)"
            ),
            {"id": person_id, "c": clan_id, "by": admin_id},
        )
        for cid, uid in ((claim1, user1), (claim2, user2)):
            await s.execute(
                sa.text(
                    "INSERT INTO identity_claims (id, user_id, person_id, status) "
                    "VALUES (:id, :u, :p, 'PENDING')"
                ),
                {"id": cid, "u": uid, "p": person_id},
            )
        await s.commit()
    return {
        "clan_id": clan_id,
        "admin_id": admin_id,
        "person_id": person_id,
        "user1": user1,
        "user2": user2,
        "claim1": claim1,
        "claim2": claim2,
    }


@pytest.mark.asyncio
async def test_lock_person_blocks_second_session(engine: AsyncEngine) -> None:
    """Repo level: a second session's lock_person blocks until the first commits."""
    maker = _maker(engine)
    seeded = await _seed(maker)
    person_id = seeded["person_id"]

    async with maker() as s1, maker() as s2:
        await SqlAlchemyClaimRepository(s1).lock_person(person_id)  # holds the lock

        task = asyncio.create_task(SqlAlchemyClaimRepository(s2).lock_person(person_id))
        done, _ = await asyncio.wait({task}, timeout=0.3)
        assert not done, "second lock_person must block on the row lock"

        await s1.commit()  # releases
        await asyncio.wait_for(task, timeout=5)
        await s2.rollback()


@pytest.mark.asyncio
async def test_approve_blocks_on_person_lock_then_conflicts(engine: AsyncEngine) -> None:
    """Handler level (the M1 bug): while a first, uncommitted approval holds the
    person lock and has linked its user, a second approval for the same person must
    BLOCK on the lock (proving approve_claim takes it), then — once the winner
    commits — fail with a clean ConflictError, never a raw IntegrityError 500.

    (Deterministic stand-in for true concurrency: session ``winner`` plays the role
    of the first approval — it holds the lock and links user1; the ``approve_claim``
    task is the second approval racing for the same person.)
    """
    maker = _maker(engine)
    seeded = await _seed(maker)

    async with maker() as winner, maker() as loser_db:
        # Winner: hold the person lock and link user1 (uncommitted → lock still held).
        await SqlAlchemyClaimRepository(winner).lock_person(seeded["person_id"])
        await winner.execute(
            sa.text("UPDATE user_profiles SET person_id = :p WHERE id = :u"),
            {"p": seeded["person_id"], "u": seeded["user1"]},
        )

        # Loser: approving claim2 for the same person must block on the lock.
        task = asyncio.create_task(
            _handler(loser_db).approve_claim(
                claim_id=seeded["claim2"], admin_id=seeded["admin_id"], reviewer_note=None
            )
        )
        done, _ = await asyncio.wait({task}, timeout=0.3)
        assert not done, "approve_claim must block on the person row lock (proves it locks)"

        await winner.commit()  # winner wins → releases the lock, link is durable

        # Loser unblocks, sees the person already linked, and conflicts cleanly.
        with pytest.raises(ConflictError, match="person_already_linked"):
            await asyncio.wait_for(task, timeout=5)

    async with maker() as s:
        linked = await s.scalar(
            sa.text("SELECT COUNT(*) FROM user_profiles WHERE person_id = :p AND id IN (:u1, :u2)"),
            {"p": seeded["person_id"], "u1": seeded["user1"], "u2": seeded["user2"]},
        )
    assert linked == 1, "exactly one user may be linked to the person"


@pytest.mark.asyncio
async def test_prelink_blocks_on_person_lock_then_conflicts(engine: AsyncEngine) -> None:
    """The admin pre-link path takes the same person lock: while a winner holds it and
    has linked user1, a concurrent prelink of user2 to the same person blocks, then
    conflicts cleanly once the winner commits."""
    maker = _maker(engine)
    seeded = await _seed(maker)

    # prelink requires the target user to already be a clan member.
    async with maker() as s:
        await s.execute(
            sa.text(
                "INSERT INTO user_clan_roles "
                "(user_id, clan_id, role, is_approved, approved_by, approved_at) "
                "VALUES (:u, :c, 'viewer', true, :a, :t)"
            ),
            {
                "u": seeded["user2"],
                "c": seeded["clan_id"],
                "a": seeded["admin_id"],
                "t": datetime.now(UTC),
            },
        )
        await s.commit()

    async with maker() as winner, maker() as loser_db:
        await SqlAlchemyClaimRepository(winner).lock_person(seeded["person_id"])
        await winner.execute(
            sa.text("UPDATE user_profiles SET person_id = :p WHERE id = :u"),
            {"p": seeded["person_id"], "u": seeded["user1"]},
        )

        task = asyncio.create_task(
            _handler(loser_db).prelink_identity(
                clan_id=seeded["clan_id"],
                user_id_to_link=seeded["user2"],
                person_id=seeded["person_id"],
                admin_id=seeded["admin_id"],
            )
        )
        done, _ = await asyncio.wait({task}, timeout=0.3)
        assert not done, "prelink_identity must block on the person row lock"

        await winner.commit()
        with pytest.raises(ConflictError, match="person_already_linked"):
            await asyncio.wait_for(task, timeout=5)
