"""Request-level tests for POST /clans/{cid}/invitations and POST /invitations/{token}/accept.

The handlers (``InvitationCommandHandler.create``/``.accept``) are untouched fakes —
these tests assert the ROUTE wraps their output into the standard ``{"data": ...}``
envelope (F-1), while ``create_invitation`` keeps its 201 status code.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.invitations import admin_invitations_router, user_invitations_router
from app.core.database import get_db
from app.core.security import ensure_user_profile, get_current_clan_id, get_current_user
from app.infrastructure.dependencies import (
    get_invitation_accept_handler,
    get_invitation_command_handler,
)
from app.schemas.auth import UserProfile


class _RoleRow:
    role = "admin"
    is_approved = True


class _RoleResult:
    def first(self) -> _RoleRow:
        return _RoleRow()


class _FakeDb:
    async def execute(self, *_a: Any, **_k: Any) -> _RoleResult:
        return _RoleResult()


class _FakeCreateHandler:
    def __init__(self) -> None:
        self.last_cmd: Any = None

    async def create(self, cmd: Any) -> dict[str, Any]:
        self.last_cmd = cmd
        return {
            "id": uuid.uuid4(),
            "email": cmd.email,
            "role": cmd.role,
            "token": "a" * 40,
            "expires_at": datetime.now(UTC),
            "accept_path": "/api/v1/invitations/aaaa/accept",
        }


class _FakeAcceptHandler:
    def __init__(self, clan_id: uuid.UUID) -> None:
        self._clan_id = clan_id

    async def accept(self, cmd: Any) -> dict[str, Any]:
        return {"clan_id": self._clan_id, "role": "editor"}


def _admin_client(handler: _FakeCreateHandler, clan_id: uuid.UUID) -> TestClient:
    app = FastAPI()
    app.include_router(admin_invitations_router, prefix="/api/v1/clans/{clan_id}/invitations")
    app.dependency_overrides[ensure_user_profile] = lambda: UserProfile(
        id=uuid.uuid4(), email="admin@x.com", full_name="Admin"
    )
    app.dependency_overrides[get_current_clan_id] = lambda: clan_id
    app.dependency_overrides[get_db] = lambda: _FakeDb()
    app.dependency_overrides[get_invitation_command_handler] = lambda: handler
    return TestClient(app)


def _user_client(handler: _FakeAcceptHandler) -> TestClient:
    app = FastAPI()
    app.include_router(user_invitations_router, prefix="/api/v1/invitations")
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": str(uuid.uuid4()),
        "email": "invitee@x.com",
        "user_metadata": {"full_name": "Invitee"},
    }
    # ADR-048: accept has its OWN provider (the privileged system session), separate from
    # the create/revoke command handler that stays on the RLS request session.
    app.dependency_overrides[get_invitation_accept_handler] = lambda: handler
    return TestClient(app)


def test_create_invitation_envelope() -> None:
    clan_id = uuid.uuid4()
    handler = _FakeCreateHandler()
    resp = _admin_client(handler, clan_id).post(
        f"/api/v1/clans/{clan_id}/invitations", json={"email": "a@x.com", "role": "editor"}
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert set(body.keys()) == {"data"}
    assert body["data"]["token"] == "a" * 40
    assert body["data"]["accept_path"] == "/api/v1/invitations/aaaa/accept"
    assert body["data"]["email"] == "a@x.com"
    assert body["data"]["role"] == "editor"


def test_accept_invitation_envelope() -> None:
    clan_id = uuid.uuid4()
    handler = _FakeAcceptHandler(clan_id)
    resp = _user_client(handler).post("/api/v1/invitations/some-token/accept")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body.keys()) == {"data"}
    assert body["data"]["clan_id"] == str(clan_id)
    assert body["data"]["role"] == "editor"
    assert isinstance(body["data"]["message"], str) and body["data"]["message"]
