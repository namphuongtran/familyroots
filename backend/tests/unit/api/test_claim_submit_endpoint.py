"""Request-level test for POST /persons/{id}/claim (F-1 5c: wrap in {data})."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.persons import router as persons_router
from app.core.database import get_db
from app.core.security import get_current_clan_id, get_current_user
from app.infrastructure.dependencies import get_claim_command_handler


@dataclass
class _FakeClaimResponse:
    id: uuid.UUID
    user_id: uuid.UUID
    person_id: uuid.UUID
    status: str = "PENDING"
    requester_note: str | None = None

    def model_dump(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "person_id": self.person_id,
            "status": self.status,
            "requester_note": self.requester_note,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }


class _RoleRow:
    role = "viewer"
    is_approved = True


class _RoleResult:
    def first(self) -> _RoleRow:
        return _RoleRow()


class _FakeDbSession:
    async def execute(self, *_args: Any, **_kwargs: Any) -> _RoleResult:
        return _RoleResult()


class _FakeClaimCommandHandler:
    def __init__(self, result: _FakeClaimResponse) -> None:
        self._result = result
        self.last_call: dict[str, Any] | None = None

    async def submit_claim(
        self, *, user_id: uuid.UUID, person_id: uuid.UUID, requester_note: str | None
    ) -> _FakeClaimResponse:
        self.last_call = {
            "user_id": user_id,
            "person_id": person_id,
            "requester_note": requester_note,
        }
        return self._result


def _build_client(handler: _FakeClaimCommandHandler, user_id: uuid.UUID) -> TestClient:
    app = FastAPI()
    app.include_router(persons_router, prefix="/api/v1/persons")

    async def _override_user() -> dict[str, Any]:
        return {"sub": str(user_id)}

    async def _override_clan_id() -> uuid.UUID:
        return uuid.uuid4()

    async def _override_db():
        yield _FakeDbSession()

    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_current_clan_id] = _override_clan_id
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_claim_command_handler] = lambda: handler

    return TestClient(app)


def test_submit_claim_wraps_result_in_data_envelope() -> None:
    user_id = uuid.uuid4()
    person_id = uuid.uuid4()
    claim_id = uuid.uuid4()
    handler = _FakeClaimCommandHandler(
        _FakeClaimResponse(id=claim_id, user_id=user_id, person_id=person_id)
    )
    client = _build_client(handler, user_id)

    response = client.post(
        f"/api/v1/persons/{person_id}/claim",
        json={"requester_note": "I am this person"},
    )

    assert response.status_code == 201
    body = response.json()
    assert set(body.keys()) == {"data"}
    assert body["data"]["id"] == str(claim_id)
    assert body["data"]["status"] == "PENDING"
    assert handler.last_call == {
        "user_id": user_id,
        "person_id": person_id,
        "requester_note": "I am this person",
    }
