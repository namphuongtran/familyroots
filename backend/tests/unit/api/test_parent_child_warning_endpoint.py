"""Request-level test for POST /relationships/parent-child (F-1 5d: warning->meta).

meta.warning must be present only when the handler actually returns a warning, and
absent otherwise (not present-but-null).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.relationships import router as relationships_router
from app.core.database import get_db
from app.core.security import get_current_clan_id, get_current_user
from app.infrastructure.dependencies import get_parent_child_command_handler


@dataclass
class _FakeLink:
    id: uuid.UUID
    parent_id: uuid.UUID
    child_id: uuid.UUID
    relationship_type: str = "biological"

    def model_dump(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "parent_id": self.parent_id,
            "child_id": self.child_id,
            "relationship_type": self.relationship_type,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }


class _RoleRow:
    role = "editor"
    is_approved = True


class _RoleResult:
    def first(self) -> _RoleRow:
        return _RoleRow()


class _FakeDbSession:
    async def execute(self, *_args: Any, **_kwargs: Any) -> _RoleResult:
        return _RoleResult()


class _FakeParentChildCommandHandler:
    def __init__(self, link: _FakeLink, warning: dict[str, Any] | None) -> None:
        self._link = link
        self._warning = warning

    async def create(self, cmd: Any) -> tuple[_FakeLink, dict[str, Any] | None]:
        return self._link, self._warning


def _build_client(handler: _FakeParentChildCommandHandler, clan_id: uuid.UUID) -> TestClient:
    app = FastAPI()
    app.include_router(relationships_router, prefix="/api/v1/relationships")

    async def _override_user() -> dict[str, Any]:
        return {"sub": str(uuid.uuid4())}

    async def _override_clan_id() -> uuid.UUID:
        return clan_id

    async def _override_db():
        yield _FakeDbSession()

    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_current_clan_id] = _override_clan_id
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_parent_child_command_handler] = lambda: handler

    return TestClient(app)


def _body(parent_id: uuid.UUID, child_id: uuid.UUID) -> dict[str, Any]:
    return {"parent_id": str(parent_id), "child_id": str(child_id)}


def test_parent_child_create_reports_warning_under_meta_when_present() -> None:
    clan_id = uuid.uuid4()
    parent_id, child_id = uuid.uuid4(), uuid.uuid4()
    link = _FakeLink(id=uuid.uuid4(), parent_id=parent_id, child_id=child_id)
    warning = {"warning": "Unusual age gap: 90.0 years"}
    client = _build_client(_FakeParentChildCommandHandler(link, warning), clan_id)

    response = client.post("/api/v1/relationships/parent-child", json=_body(parent_id, child_id))

    assert response.status_code == 201
    body = response.json()
    assert body["data"]["id"] == str(link.id)
    assert body["meta"] == {"warning": warning}


def test_parent_child_create_omits_meta_when_no_warning() -> None:
    clan_id = uuid.uuid4()
    parent_id, child_id = uuid.uuid4(), uuid.uuid4()
    link = _FakeLink(id=uuid.uuid4(), parent_id=parent_id, child_id=child_id)
    client = _build_client(_FakeParentChildCommandHandler(link, None), clan_id)

    response = client.post("/api/v1/relationships/parent-child", json=_body(parent_id, child_id))

    assert response.status_code == 201
    body = response.json()
    assert body["data"]["id"] == str(link.id)
    assert "meta" not in body
