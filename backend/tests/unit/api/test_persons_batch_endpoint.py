"""Request-level tests for the persons batch read endpoint."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.persons import router as persons_router
from app.application.person.commands import GetPerson
from app.core.database import get_db
from app.core.exceptions import unhandled_exception_handler
from app.core.security import get_current_clan_id, get_current_user
from app.domain.shared.exceptions import EntityNotFoundError
from app.infrastructure.dependencies import get_person_query_handler


@dataclass
class _FakePerson:
    id: uuid.UUID
    full_name: str
    gender: str = "unknown"

    def model_dump(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "full_name": self.full_name,
            "gender": self.gender,
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


class _FakePersonQueryHandler:
    def __init__(
        self, persons: dict[uuid.UUID, _FakePerson], *, timeline_raises: bool = False
    ) -> None:
        self._persons = persons
        self._timeline_raises = timeline_raises

    async def get(self, query: GetPerson) -> _FakePerson:
        person = self._persons.get(query.person_id)
        if not person:
            raise EntityNotFoundError("person_not_found")
        return person

    async def redact_pii(self, persons: Any, *, viewer_role: str, viewer_user_id: Any) -> None:
        # PII redaction (L11) is covered in test_person_pii_visibility; not exercised
        # here — this batch test targets profile/fields/stats behavior.
        return None

    async def get_persons_stats(
        self, clan_id: uuid.UUID, person_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, dict[str, int]]:
        return {pid: {"spouse_count": 1, "child_count": 2} for pid in person_ids}

    async def get_marriages(self, clan_id: uuid.UUID, person_id: uuid.UUID) -> list[dict[str, Any]]:
        return [{"marriage_id": f"m-{person_id}"}]

    async def get_parent_child(
        self, clan_id: uuid.UUID, person_id: uuid.UUID
    ) -> list[dict[str, Any]]:
        return [{"relation_id": f"pc-{person_id}"}]

    async def get_timeline(self, clan_id: uuid.UUID, person_id: uuid.UUID) -> list[dict[str, Any]]:
        if self._timeline_raises:
            raise RuntimeError("timeline query blew up")
        return [{"event_type": "birth", "person_id": str(person_id), "clan_id": str(clan_id)}]

    async def get_documents(self, clan_id: uuid.UUID, person_id: uuid.UUID) -> list[dict[str, Any]]:
        return [{"document_id": f"doc-{person_id}", "clan_id": str(clan_id)}]


def _build_client(
    persons: dict[uuid.UUID, _FakePerson],
    clan_id: uuid.UUID,
    *,
    timeline_raises: bool = False,
) -> TestClient:
    app = FastAPI()
    app.include_router(persons_router, prefix="/api/v1/persons")
    # Mirror app.main's registration so an unhandled exception surfaces via the
    # same structured 500 envelope the real app produces, not a raw traceback.
    app.add_exception_handler(Exception, unhandled_exception_handler)

    async def _override_user() -> dict[str, Any]:
        return {"sub": str(uuid.uuid4())}

    async def _override_clan_id() -> uuid.UUID:
        return clan_id

    async def _override_db():
        yield _FakeDbSession()

    def _override_handler() -> _FakePersonQueryHandler:
        return _FakePersonQueryHandler(persons, timeline_raises=timeline_raises)

    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_current_clan_id] = _override_clan_id
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_person_query_handler] = _override_handler

    # raise_server_exceptions=False: let an unhandled exception ride through the
    # real middleware stack (ServerErrorMiddleware re-raises by default so bare
    # test clients can surface bugs) and come back as the 500 response the real
    # app.main exception handler produces, instead of blowing up the test itself.
    return TestClient(app, raise_server_exceptions=False)


def test_batch_endpoint_returns_sparse_profile_with_stats() -> None:
    clan_id = uuid.uuid4()
    id1 = uuid.uuid4()
    id2 = uuid.uuid4()
    client = _build_client(
        {
            id1: _FakePerson(id=id1, full_name="Nguyen A", gender="male"),
            id2: _FakePerson(id=id2, full_name="Nguyen B", gender="female"),
        },
        clan_id,
    )

    response = client.post(
        "/api/v1/persons/batch",
        json={
            "ids": [str(id1), str(id2)],
            "profile": "summary",
            "include": "stats",
            "fields": "id,full_name,stats",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["errors"] == []
    assert len(body["data"]) == 2
    assert set(body["data"][0].keys()) == {"id", "full_name", "stats"}
    assert body["data"][0]["stats"] == {"spouse_count": 1, "child_count": 2}


def test_batch_endpoint_supports_per_id_includes() -> None:
    clan_id = uuid.uuid4()
    id1 = uuid.uuid4()
    id2 = uuid.uuid4()
    client = _build_client(
        {
            id1: _FakePerson(id=id1, full_name="Nguyen C", gender="male"),
            id2: _FakePerson(id=id2, full_name="Nguyen D", gender="female"),
        },
        clan_id,
    )

    response = client.post(
        "/api/v1/persons/batch",
        json={
            "ids": [str(id1), str(id2)],
            "profile": "summary",
            "include_by_id": {str(id1): "marriages,parent_child"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["errors"] == []

    first = body["data"][0]
    second = body["data"][1]

    assert "marriages" in first
    assert "parent_child" in first
    assert "marriages" not in second
    assert "parent_child" not in second


def test_batch_endpoint_reports_not_found_without_failing_whole_request() -> None:
    clan_id = uuid.uuid4()
    existing_id = uuid.uuid4()
    missing_id = uuid.uuid4()
    client = _build_client(
        {
            existing_id: _FakePerson(id=existing_id, full_name="Nguyen E", gender="male"),
        },
        clan_id,
    )

    response = client.post(
        "/api/v1/persons/batch",
        json={
            "ids": [str(existing_id), str(missing_id)],
            "profile": "summary",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]) == 1
    assert body["data"][0]["id"] == str(existing_id)
    assert body["errors"] == [{"id": str(missing_id), "code": "person_not_found"}]


def test_batch_endpoint_rejects_malformed_include_by_id_keys() -> None:
    clan_id = uuid.uuid4()
    existing_id = uuid.uuid4()
    client = _build_client(
        {
            existing_id: _FakePerson(id=existing_id, full_name="Nguyen F", gender="male"),
        },
        clan_id,
    )

    response = client.post(
        "/api/v1/persons/batch",
        json={
            "ids": [str(existing_id)],
            "profile": "summary",
            "include_by_id": {"not-a-uuid": "marriages"},
        },
    )

    assert response.status_code == 422


def test_batch_endpoint_ignores_unsupported_include_tokens() -> None:
    clan_id = uuid.uuid4()
    existing_id = uuid.uuid4()
    client = _build_client(
        {
            existing_id: _FakePerson(id=existing_id, full_name="Nguyen G", gender="female"),
        },
        clan_id,
    )

    response = client.post(
        "/api/v1/persons/batch",
        json={
            "ids": [str(existing_id)],
            "profile": "summary",
            "include": "unknown_token",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["errors"] == []
    assert len(body["data"]) == 1
    assert "unknown_token" not in body["data"][0]


def test_batch_endpoint_propagates_include_subquery_error_for_one_of_several() -> None:
    # Regression test for PR-J: with several persons in the batch, one include
    # sub-query (get_timeline) raises for every person. The include gather must
    # await *all* the coroutines (no orphaned tasks) before surfacing the error,
    # and the failure must propagate as a real error — never come back as a
    # 200 with the include silently degraded to [] for that person.
    clan_id = uuid.uuid4()
    id1 = uuid.uuid4()
    id2 = uuid.uuid4()
    client = _build_client(
        {
            id1: _FakePerson(id=id1, full_name="Nguyen H", gender="male"),
            id2: _FakePerson(id=id2, full_name="Nguyen I", gender="female"),
        },
        clan_id,
        timeline_raises=True,
    )

    response = client.post(
        "/api/v1/persons/batch",
        json={
            "ids": [str(id1), str(id2)],
            "profile": "summary",
            "include": "timeline",
        },
    )

    assert response.status_code == 500
    body = response.json()
    # The generic 500 envelope — not the batch response shape (no top-level
    # "data"/"errors"), confirming the failure was never folded into a per-item
    # error or degraded to an empty include.
    assert body["error"]["code"] == "internal_error"
    assert "data" not in body
