"""Regression test for the update-handler precision/display write path.

Task 2 added write-DTO fields (birth_date_precision/display, death_date_precision/
display on person; event_date_precision/display on event; marriage_date_precision/
display and divorce_date_precision/display on marriage), but the aggregates didn't
know these fields yet, so the 3 PATCH routes (update_person, update_event,
update_marriage) temporarily excluded them from `changes` to avoid a spurious 422
(field_not_updatable).

Task 5 wired precision/display onto every aggregate's `_UPDATABLE_FIELDS` whitelist
and removed those excludes. These tests now pin the OPPOSITE of the old shim
behavior: a PATCH carrying a precision/display field must reach the handler's
`changes` dict (and therefore persist), alongside any ordinary field in the same
request.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.events import router as events_router
from app.api.v1.persons import router as persons_router
from app.api.v1.relationships import router as relationships_router
from app.core.database import get_db
from app.core.exceptions import unhandled_exception_handler
from app.core.security import get_current_clan_id, get_current_user
from app.infrastructure.dependencies import (
    get_event_command_handler,
    get_marriage_command_handler,
    get_person_command_handler,
)


class _RoleRow:
    """DB row satisfying require_role() with an editor membership.

    Editor satisfies RequireViewer (person route) and RequireEditor (event and
    marriage routes) alike, so one fake role row covers all three handlers.
    """

    role = "editor"
    is_approved = True


class _RoleResult:
    def first(self) -> _RoleRow:
        return _RoleRow()


class _FakeDbSession:
    async def execute(self, *_args: Any, **_kwargs: Any) -> _RoleResult:
        return _RoleResult()


@dataclass
class _FakeResponse:
    """Minimal stand-in returned by the fake command handlers below."""

    id: uuid.UUID = field(default_factory=uuid.uuid4)
    full_name: str = "Test Person"

    def model_dump(self) -> dict[str, Any]:
        return {"id": str(self.id), "full_name": self.full_name}


class _FakePersonCommandHandler:
    def __init__(self) -> None:
        self.received_changes: dict[str, Any] | None = None

    async def update(self, cmd: Any) -> _FakeResponse:
        self.received_changes = cmd.changes
        full_name = cmd.changes.get("full_name", "Test Person")
        return _FakeResponse(id=cmd.person_id, full_name=full_name)


class _FakeEventCommandHandler:
    def __init__(self) -> None:
        self.received_changes: dict[str, Any] | None = None

    async def update(
        self,
        *,
        event_id: uuid.UUID,
        clan_id: uuid.UUID,
        actor: Any,
        changes: dict[str, Any],
    ) -> _FakeResponse:
        self.received_changes = changes
        return _FakeResponse(id=event_id)


class _FakeMarriageCommandHandler:
    def __init__(self) -> None:
        self.received_changes: dict[str, Any] | None = None

    async def update(self, cmd: Any) -> _FakeResponse:
        self.received_changes = cmd.changes
        return _FakeResponse(id=cmd.marriage_id)


def _build_client() -> tuple[TestClient, dict[str, Any]]:
    app = FastAPI()
    app.include_router(persons_router, prefix="/api/v1/persons")
    app.include_router(events_router, prefix="/api/v1/events")
    app.include_router(relationships_router, prefix="/api/v1/relationships")
    app.add_exception_handler(Exception, unhandled_exception_handler)

    async def _override_user() -> dict[str, Any]:
        return {"sub": str(uuid.uuid4())}

    async def _override_clan_id() -> uuid.UUID:
        return uuid.uuid4()

    async def _override_db():
        yield _FakeDbSession()

    person_handler = _FakePersonCommandHandler()
    event_handler = _FakeEventCommandHandler()
    marriage_handler = _FakeMarriageCommandHandler()

    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_current_clan_id] = _override_clan_id
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_person_command_handler] = lambda: person_handler
    app.dependency_overrides[get_event_command_handler] = lambda: event_handler
    app.dependency_overrides[get_marriage_command_handler] = lambda: marriage_handler

    handlers = {
        "person": person_handler,
        "event": event_handler,
        "marriage": marriage_handler,
    }
    return TestClient(app, raise_server_exceptions=False), handlers


def test_update_person_with_precision_field_persists() -> None:
    client, handlers = _build_client()
    person_id = uuid.uuid4()

    response = client.patch(
        f"/api/v1/persons/{person_id}",
        json={
            "birth_date_precision": "circa",
            "full_name": "Updated Name",
            "expected_version": 1,
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["full_name"] == "Updated Name"
    # The precision field must now reach the aggregate's changes dict (shim removed).
    assert handlers["person"].received_changes == {
        "birth_date_precision": "circa",
        "full_name": "Updated Name",
    }


def test_update_person_with_only_precision_fields_reaches_changes() -> None:
    client, handlers = _build_client()
    person_id = uuid.uuid4()

    response = client.patch(
        f"/api/v1/persons/{person_id}",
        json={
            "birth_date_precision": "circa",
            "birth_date_display": "circa 1900",
            "death_date_precision": "year",
            "death_date_display": "1975",
            "expected_version": 1,
        },
    )

    assert response.status_code == 200, response.text
    assert handlers["person"].received_changes == {
        "birth_date_precision": "circa",
        "birth_date_display": "circa 1900",
        "death_date_precision": "year",
        "death_date_display": "1975",
    }


def test_update_event_with_precision_field_persists() -> None:
    client, handlers = _build_client()
    event_id = uuid.uuid4()

    response = client.patch(
        f"/api/v1/events/{event_id}",
        json={
            "event_date_precision": "month",
            "event_date_display": "Jan 1975",
            "title": "New title",
        },
    )

    assert response.status_code == 200, response.text
    assert handlers["event"].received_changes == {
        "event_date_precision": "month",
        "event_date_display": "Jan 1975",
        "title": "New title",
    }


def test_update_marriage_with_precision_field_persists() -> None:
    client, handlers = _build_client()
    marriage_id = uuid.uuid4()

    response = client.patch(
        f"/api/v1/relationships/marriages/{marriage_id}",
        json={
            "marriage_date_precision": "circa",
            "divorce_date_display": "unknown",
            "notes": "updated notes",
            "expected_version": 1,
        },
    )

    assert response.status_code == 200, response.text
    # expected_version is popped by the route (OCC, ADR-017) — never part of changes.
    assert handlers["marriage"].received_changes == {
        "marriage_date_precision": "circa",
        "divorce_date_display": "unknown",
        "notes": "updated notes",
    }
