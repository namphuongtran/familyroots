"""Login / profile handlers must map the typed AuthProfileView correctly.

Locks the semantics that used to live in fragile raw-Row attribute access
(``row.UserProfile`` broke at runtime because SQLAlchemy keys rows by mapped
class name, not import alias — a login 500 on main). The read seam now returns
``AuthProfileView``; these tests pin the handler mapping for every membership
state: approved, pending, none, and missing profile.
"""

import uuid
from typing import Any

import pytest

from app.application.auth.handlers import AuthCommandHandler, AuthQueryHandler
from app.domain.auth.identity_provider import AuthenticatedIdentity, AuthTokens
from app.domain.auth.repository import AuthProfileView

USER_ID = uuid.uuid4()
CLAN_ID = uuid.uuid4()


class _StubIdentity:
    async def sign_in(self, *, email: str, password: str) -> AuthenticatedIdentity:
        return AuthenticatedIdentity(
            user_id=str(USER_ID),
            email=email,
            full_name="Test User",
            tokens=AuthTokens(access_token="at", refresh_token="rt", expires_in=3600),
        )


class _StubQueryPort:
    def __init__(self, view: AuthProfileView | None, pending: bool = False) -> None:
        self._view = view
        self._pending = pending

    async def get_profile(self, user_id: uuid.UUID) -> AuthProfileView | None:
        return self._view

    async def get_login_profile(self, user_id: uuid.UUID) -> AuthProfileView | None:
        return self._view

    async def has_pending_membership(self, user_id: uuid.UUID) -> bool:
        return self._pending


def _login_handler(view: AuthProfileView | None) -> AuthCommandHandler:
    return AuthCommandHandler(
        repo=None,  # type: ignore[arg-type]  # login never touches the write repo
        uow=None,  # type: ignore[arg-type]
        identity=_StubIdentity(),
        query_port=_StubQueryPort(view),
    )


@pytest.mark.asyncio
async def test_login_approved_membership_maps_role_and_clan() -> None:
    view = AuthProfileView(
        person_id=None, clan_id=CLAN_ID, clan_name="Họ Trần", role="admin", is_approved=True
    )
    resp = await _login_handler(view).login(email="a@b.c", password="x")
    assert resp.user.clan_id == CLAN_ID
    assert resp.user.clan_name == "Họ Trần"
    assert resp.user.role == "admin"
    assert resp.user.is_approved is True


@pytest.mark.asyncio
async def test_login_pending_membership_hides_role_but_shows_clan() -> None:
    view = AuthProfileView(
        person_id=None, clan_id=CLAN_ID, clan_name="Họ Trần", role="viewer", is_approved=False
    )
    resp = await _login_handler(view).login(email="a@b.c", password="x")
    # A pending membership carries a role but must not grant one in the response.
    assert resp.user.role is None
    assert resp.user.is_approved is False
    assert resp.user.clan_id == CLAN_ID


@pytest.mark.asyncio
@pytest.mark.parametrize("view", [None, AuthProfileView()])
async def test_login_without_membership_or_profile(view: Any) -> None:
    resp = await _login_handler(view).login(email="a@b.c", password="x")
    assert resp.user.clan_id is None
    assert resp.user.role is None
    assert resp.user.is_approved is False
    assert resp.user.person_id is None


@pytest.mark.asyncio
async def test_get_profile_maps_view_and_pending_flag() -> None:
    person_id = uuid.uuid4()
    view = AuthProfileView(
        person_id=person_id, clan_id=CLAN_ID, clan_name="Họ Lê", role="editor", is_approved=True
    )
    handler = AuthQueryHandler(_StubQueryPort(view, pending=True))
    profile = await handler.get_profile(user_id=USER_ID, email="a@b.c", full_name="T")
    assert profile.clan_id == CLAN_ID
    assert profile.role == "editor"
    assert profile.is_approved is True
    assert profile.has_pending_membership is True
    assert profile.person_id == person_id


@pytest.mark.asyncio
async def test_get_profile_without_profile_row() -> None:
    handler = AuthQueryHandler(_StubQueryPort(None))
    profile = await handler.get_profile(user_id=USER_ID, email="a@b.c", full_name="T")
    assert profile.clan_id is None
    assert profile.is_approved is False
