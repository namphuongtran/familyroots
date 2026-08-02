"""The clan user lists must let an admin see WHO they are approving — and must
not leak that identity any wider than the guard on each route allows.

J18 (docs/superpowers/specs/2026-08-02-design-system-and-screens.md §9): approving
a join request granted a stranger read access to hundreds of living relatives'
records, and the queue showed the admin nothing but a UUID. ``person_id`` is null
for exactly the fresh registrant who most needs judging.

The fix is asymmetric, and the asymmetry is the whole point (ADR-039):

  * ``GET /clans/me/users/pending`` — ``RequireAdmin`` — ``display_name`` + ``email``
  * ``GET /clans/me/users``          — ``RequireViewer`` — ``display_name`` only

``test_email_is_on_pending_and_never_on_approved`` is the guard against a future
refactor that "tidies" the two handlers into one shared serialiser and thereby
broadcasts every member's login email to the whole clan.

Drives the route functions directly against a real Postgres-backed repository
(ADR-016), as ``test_clan_users_person_id.py`` does — ``list_clan_users`` and
``list_pending_users`` take their dependencies as plain arguments, so no HTTP
layer or JWT stubbing is needed.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.v1.clans import list_clan_users, list_pending_users
from app.application.clan.handlers import ClanQueryHandler
from app.core.permissions import ClanRole
from app.infrastructure.persistence.clan_repository import SqlAlchemyClanRepository

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture()
async def async_session(migrated_db_url: str) -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine(migrated_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as session:
        yield session
    await engine.dispose()


# ── fixtures-as-functions ────────────────────────────────────────────────


async def _clan(s: AsyncSession, cid: uuid.UUID) -> None:
    await s.execute(
        sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :sl)"),
        {"id": cid, "sl": f"c-{cid.hex[:8]}"},
    )


async def _profile(
    s: AsyncSession,
    uid: uuid.UUID,
    *,
    email: str,
    display_name: str | None,
) -> None:
    """``user_profiles.email`` is NOT NULL; ``display_name`` is nullable."""
    await s.execute(
        sa.text("INSERT INTO user_profiles (id, email, display_name) VALUES (:id, :e, :dn)"),
        {"id": uid, "e": email, "dn": display_name},
    )


async def _role(
    s: AsyncSession,
    uid: uuid.UUID,
    cid: uuid.UUID,
    *,
    role: str = "admin",
    approved: bool = True,
) -> None:
    now = datetime.now(UTC) if approved else None
    approved_by = uid if approved else None
    await s.execute(
        sa.text(
            "INSERT INTO user_clan_roles "
            "(user_id, clan_id, role, is_approved, approved_by, approved_at) "
            "VALUES (:u, :c, :r, :appr, :ab, :at)"
        ),
        {"u": uid, "c": cid, "r": role, "appr": approved, "ab": approved_by, "at": now},
    )


def _query_handler(session: AsyncSession) -> ClanQueryHandler:
    return ClanQueryHandler(SqlAlchemyClanRepository(session))  # type: ignore[arg-type]


async def _approved(session: AsyncSession, clan_id: uuid.UUID) -> list[dict[str, Any]]:
    page = await list_clan_users(
        current_user={"sub": str(uuid.uuid4())},
        clan_id=clan_id,
        query_handler=_query_handler(session),
        role=ClanRole.VIEWER,
        cursor=None,
        limit=20,
    )
    return list(page["data"])


async def _pending(session: AsyncSession, clan_id: uuid.UUID) -> list[dict[str, Any]]:
    page = await list_pending_users(
        current_user={"sub": str(uuid.uuid4())},
        clan_id=clan_id,
        query_handler=_query_handler(session),
        role=ClanRole.ADMIN,
        cursor=None,
        limit=20,
    )
    return list(page["data"])


# ── the identity fields are actually served ──────────────────────────────


async def test_pending_row_carries_display_name_and_email(
    async_session: AsyncSession,
) -> None:
    """The admin approving a fresh registrant (person_id null) can now see who."""
    clan_id, user_id = uuid.uuid4(), uuid.uuid4()
    await _clan(async_session, clan_id)
    await _profile(
        async_session, user_id, email="hai.nguyen@example.com", display_name="Nguyễn Văn Hải"
    )
    await _role(async_session, user_id, clan_id, role="viewer", approved=False)
    await async_session.commit()

    rows = await _pending(async_session, clan_id)

    assert len(rows) == 1
    assert rows[0]["display_name"] == "Nguyễn Văn Hải"
    assert rows[0]["email"] == "hai.nguyen@example.com"
    # The case J18 is about: no linked person, so person_id alone identifies nobody.
    assert rows[0]["person_id"] is None


async def test_approved_row_carries_display_name(async_session: AsyncSession) -> None:
    clan_id, user_id = uuid.uuid4(), uuid.uuid4()
    await _clan(async_session, clan_id)
    await _profile(async_session, user_id, email="member@example.com", display_name="Thành Viên")
    await _role(async_session, user_id, clan_id)
    await async_session.commit()

    rows = await _approved(async_session, clan_id)

    assert len(rows) == 1
    assert rows[0]["display_name"] == "Thành Viên"


# ── the asymmetry (this is the guard test) ───────────────────────────────


async def test_email_is_on_pending_and_never_on_approved(
    async_session: AsyncSession,
) -> None:
    """Pin the pending/approved asymmetry so a shared serialiser cannot restore it.

    ``GET /clans/me/users`` is ``RequireViewer``: an ``email`` key there hands every
    approved member of the clan the login address of every other member. The
    pending queue is ``RequireAdmin`` and is an identity decision, so it gets one.
    Merging the two handlers is exactly how this distinction gets lost — ADR-039.
    """
    clan_id = uuid.uuid4()
    approved_user, pending_user = uuid.uuid4(), uuid.uuid4()
    await _clan(async_session, clan_id)
    await _profile(
        async_session, approved_user, email="approved@example.com", display_name="Đã Duyệt"
    )
    await _role(async_session, approved_user, clan_id)
    await _profile(
        async_session, pending_user, email="pending@example.com", display_name="Chờ Duyệt"
    )
    await _role(async_session, pending_user, clan_id, role="viewer", approved=False)
    await async_session.commit()

    pending_rows = await _pending(async_session, clan_id)
    approved_rows = await _approved(async_session, clan_id)

    assert len(pending_rows) == 1
    assert len(approved_rows) == 1

    # Pending (admin-only): the key exists AND carries the real address.
    assert "email" in pending_rows[0]
    assert pending_rows[0]["email"] == "pending@example.com"

    # Approved (viewer-readable): the key must be ABSENT, not merely null — a null
    # would still put `email` in the documented shape and invite someone to fill it.
    assert "email" not in approved_rows[0], (
        "GET /clans/me/users is RequireViewer; an email key here leaks every "
        "member's login address to the whole clan. See ADR-039."
    )
    # The address must not reach the viewer payload under any other key either.
    assert "approved@example.com" not in str(approved_rows[0])

    # Both lists do carry display_name — that half is symmetric on purpose.
    assert pending_rows[0]["display_name"] == "Chờ Duyệt"
    assert approved_rows[0]["display_name"] == "Đã Duyệt"


# ── null paths ───────────────────────────────────────────────────────────


async def test_null_display_name_serialises_as_none_on_both_lists(
    async_session: AsyncSession,
) -> None:
    """``user_profiles.display_name`` is nullable — a profile can exist with none."""
    clan_id = uuid.uuid4()
    approved_user, pending_user = uuid.uuid4(), uuid.uuid4()
    await _clan(async_session, clan_id)
    await _profile(async_session, approved_user, email="a@example.com", display_name=None)
    await _role(async_session, approved_user, clan_id)
    await _profile(async_session, pending_user, email="p@example.com", display_name=None)
    await _role(async_session, pending_user, clan_id, role="viewer", approved=False)
    await async_session.commit()

    approved_rows = await _approved(async_session, clan_id)
    pending_rows = await _pending(async_session, clan_id)

    assert approved_rows[0]["display_name"] is None
    assert pending_rows[0]["display_name"] is None
    # A nameless pending request still shows the admin an email to judge by.
    assert pending_rows[0]["email"] == "p@example.com"


@dataclass
class _ProfilelessRole:
    """A ``UserClanRole``-shaped row whose LEFT JOIN found no ``user_profiles`` row."""

    id: uuid.UUID
    user_id: uuid.UUID
    role: str
    created_at: datetime
    user_profile: None = None


class _ProfilelessQueryHandler:
    """Returns one profile-less row, whatever the clan or approval filter.

    ``user_clan_roles.user_id`` is a NOT NULL FK to ``user_profiles.id``
    (migration 001), so this state is unreachable through the database today and
    cannot be built with SQL. The handlers still None-guard it, because
    ``list_users`` LEFT JOINs and the guard is what keeps a future FK/relationship
    change from turning a missing profile into an ``AttributeError`` -> 500 — the
    exact regression ``test_clan_users_person_id.py`` was written for. This fake
    is the only way to execute that branch, so it exists.
    """

    def __init__(self, row: _ProfilelessRole) -> None:
        self._row = row

    async def list_users(
        self, clan_id: uuid.UUID, approved: bool, cursor: str | None, limit: int
    ) -> dict[str, Any]:
        return {
            "data": [self._row],
            "meta": {"cursor": None, "has_more": False, "limit": limit},
        }


@pytest.mark.parametrize("route", [list_clan_users, list_pending_users])
async def test_missing_user_profile_row_yields_nulls_not_an_attribute_error(
    route: Any,
) -> None:
    row = _ProfilelessRole(
        id=uuid.uuid4(), user_id=uuid.uuid4(), role="viewer", created_at=datetime.now(UTC)
    )
    page = await route(
        current_user={"sub": str(uuid.uuid4())},
        clan_id=uuid.uuid4(),
        query_handler=_ProfilelessQueryHandler(row),
        role=ClanRole.ADMIN,
        cursor=None,
        limit=20,
    )

    (out,) = page["data"]
    assert out["person_id"] is None
    assert out["display_name"] is None
    if route is list_pending_users:
        assert out["email"] is None
    else:
        assert "email" not in out


# ── two-sided clan isolation ─────────────────────────────────────────────


async def test_clan_b_cannot_see_clan_a_identity_fields_and_vice_versa(
    async_session: AsyncSession,
) -> None:
    """Two-sided: neither clan's lists expose the other clan's names or emails.

    Runs both directions because a one-sided check passes trivially against a
    filter that happens to hardcode the first clan. Also covers a user who holds
    a role in BOTH clans: scoping is per ``user_clan_roles`` row, not per profile,
    so the shared profile's email must surface only in the clan whose pending
    queue the request is for.
    """
    clan_a, clan_b = uuid.uuid4(), uuid.uuid4()
    await _clan(async_session, clan_a)
    await _clan(async_session, clan_b)

    a_member, a_pending = uuid.uuid4(), uuid.uuid4()
    b_member, b_pending = uuid.uuid4(), uuid.uuid4()
    shared = uuid.uuid4()

    await _profile(async_session, a_member, email="a-member@example.com", display_name="A Member")
    await _role(async_session, a_member, clan_a)
    await _profile(async_session, a_pending, email="a-pending@example.com", display_name="A Pend")
    await _role(async_session, a_pending, clan_a, role="viewer", approved=False)

    await _profile(async_session, b_member, email="b-member@example.com", display_name="B Member")
    await _role(async_session, b_member, clan_b)
    await _profile(async_session, b_pending, email="b-pending@example.com", display_name="B Pend")
    await _role(async_session, b_pending, clan_b, role="viewer", approved=False)

    # Approved in A, still pending in B.
    await _profile(async_session, shared, email="shared@example.com", display_name="Shared")
    await _role(async_session, shared, clan_a)
    await _role(async_session, shared, clan_b, role="viewer", approved=False)
    await async_session.commit()

    a_approved = await _approved(async_session, clan_a)
    a_pending_rows = await _pending(async_session, clan_a)
    b_approved = await _approved(async_session, clan_b)
    b_pending_rows = await _pending(async_session, clan_b)

    assert {r["user_id"] for r in a_approved} == {str(a_member), str(shared)}
    assert {r["user_id"] for r in a_pending_rows} == {str(a_pending)}
    assert {r["user_id"] for r in b_approved} == {str(b_member)}
    assert {r["user_id"] for r in b_pending_rows} == {str(b_pending), str(shared)}

    a_blob = str(a_approved) + str(a_pending_rows)
    b_blob = str(b_approved) + str(b_pending_rows)

    # A's lists carry nothing of B's identities...
    for leaked in ("b-member@example.com", "b-pending@example.com", "B Member", "B Pend"):
        assert leaked not in a_blob, f"clan A leaked clan B's {leaked!r}"
    # ...and B's lists carry nothing of A's.
    for leaked in ("a-member@example.com", "a-pending@example.com", "A Member", "A Pend"):
        assert leaked not in b_blob, f"clan B leaked clan A's {leaked!r}"

    # The shared profile's email appears only where a pending decision needs it:
    # B's admin queue. It must not reach A's viewer-readable approved list.
    assert any(r["email"] == "shared@example.com" for r in b_pending_rows)
    assert "shared@example.com" not in str(a_approved)
