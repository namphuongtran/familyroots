"""Request-level tests for the persons list endpoint (GET /persons).

F-1 5a: the list route returns the standard {data, meta} envelope — meta carries
cursor/has_more/limit pagination info, and the previous bare "total" key is gone.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.persons import router as persons_router
from app.application.person.commands import ListPersons
from app.core.database import get_db
from app.core.security import get_current_clan_id, get_current_user
from app.infrastructure.dependencies import get_person_query_handler


@dataclass
class _FakePerson:
    id: uuid.UUID
    full_name: str
    gender: str = "unknown"

    def model_dump(self) -> dict[str, Any]:
        return {"id": self.id, "full_name": self.full_name, "gender": self.gender}


class _RoleRow:
    role = "viewer"
    is_approved = True


class _RoleResult:
    def first(self) -> _RoleRow:
        return _RoleRow()


class _FakeDbSession:
    async def execute(self, *_args: Any, **_kwargs: Any) -> _RoleResult:
        return _RoleResult()


class _FakePersonQueryHandler:
    """Returns a fixed (data, meta) pair, mirroring PersonQueryHandler.list_persons."""

    def __init__(self, persons: list[_FakePerson], meta: dict[str, Any]) -> None:
        self._persons = persons
        self._meta = meta
        self.last_query: ListPersons | None = None

    async def list_persons(self, query: ListPersons) -> tuple[list[_FakePerson], dict[str, Any]]:
        self.last_query = query
        return self._persons, self._meta

    async def redact_pii(self, persons: Any, *, viewer_role: str, viewer_user_id: Any) -> None:
        return None

    async def get_persons_stats(
        self, clan_id: uuid.UUID, person_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, dict[str, int]]:
        return {}


def _build_client(handler: _FakePersonQueryHandler, clan_id: uuid.UUID) -> TestClient:
    app = FastAPI()
    app.include_router(persons_router, prefix="/api/v1/persons")

    async def _override_user() -> dict[str, Any]:
        return {"sub": str(uuid.uuid4())}

    async def _override_clan_id() -> uuid.UUID:
        return clan_id

    async def _override_db():
        yield _FakeDbSession()

    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_current_clan_id] = _override_clan_id
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_person_query_handler] = lambda: handler

    return TestClient(app)


def test_list_persons_returns_data_and_meta_envelope_without_total() -> None:
    clan_id = uuid.uuid4()
    id1, id2 = uuid.uuid4(), uuid.uuid4()
    cursor_id = str(id2)
    handler = _FakePersonQueryHandler(
        persons=[
            _FakePerson(id=id1, full_name="Nguyen A"),
            _FakePerson(id=id2, full_name="Nguyen B"),
        ],
        meta={"cursor": cursor_id, "has_more": True, "limit": 2},
    )
    client = _build_client(handler, clan_id)

    response = client.get("/api/v1/persons", params={"limit": 2})

    assert response.status_code == 200
    body = response.json()
    assert body["meta"] == {"cursor": cursor_id, "has_more": True, "limit": 2}
    assert len(body["data"]) == 2
    assert "total" not in body
    assert "total" not in body["meta"]


def test_list_persons_last_page_has_no_cursor() -> None:
    clan_id = uuid.uuid4()
    handler = _FakePersonQueryHandler(
        persons=[_FakePerson(id=uuid.uuid4(), full_name="Nguyen C")],
        meta={"cursor": None, "has_more": False, "limit": 20},
    )
    client = _build_client(handler, clan_id)

    response = client.get("/api/v1/persons")

    assert response.status_code == 200
    body = response.json()
    assert body["meta"] == {"cursor": None, "has_more": False, "limit": 20}
    assert "total" not in body
