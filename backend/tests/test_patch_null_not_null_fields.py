"""A PATCH that nulls a NOT NULL column answers 422 naming the field, not 500.

Reading: the request is sent and the response body read. The handler is a spy that
fails the test if it is reached, so a null that slips past validation is caught
whether the real database would then answer 500 or not.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.branches import router as branches_router
from app.api.v1.events import router as events_router
from app.api.v1.persons import router as persons_router
from app.core.database import get_db
from app.core.security import get_current_clan_id, get_current_user
from app.infrastructure.dependencies import (
    get_branch_command_handler,
    get_event_command_handler,
    get_person_command_handler,
)


class _Row:
    role = "admin"
    is_approved = True


class _Result:
    def first(self) -> _Row:
        return _Row()


class _Db:
    async def execute(self, *_a: Any, **_k: Any) -> _Result:
        return _Result()


class _Spy:
    def __init__(self) -> None:
        self.called = False

    async def update(self, *_a: Any, **_k: Any) -> Any:
        self.called = True
        raise AssertionError("a null for a NOT NULL field reached the handler")


def _client(spy: _Spy) -> TestClient:
    app = FastAPI()
    app.include_router(branches_router, prefix="/branches")
    app.include_router(events_router, prefix="/events")
    app.include_router(persons_router, prefix="/persons")

    async def _user() -> dict[str, Any]:
        return {"sub": str(uuid.uuid4())}

    async def _clan() -> uuid.UUID:
        return uuid.uuid4()

    async def _db():
        yield _Db()

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_current_clan_id] = _clan
    app.dependency_overrides[get_db] = _db
    for dep in (
        get_branch_command_handler,
        get_event_command_handler,
        get_person_command_handler,
    ):
        app.dependency_overrides[dep] = lambda: spy
    return TestClient(app, raise_server_exceptions=False)


_CASES = [
    ("branches", "name", {}),
    *[
        ("persons", f, {"expected_version": 1})
        for f in ("full_name", "gender", "birth_date_precision", "death_date_precision")
    ],
    *[
        ("events", f, {"expected_version": 1})
        for f in (
            "event_type",
            "title",
            "event_date",
            "event_date_precision",
            "is_lunar_calendar",
            "is_recurring",
            "notify_days_before",
        )
    ],
]


@pytest.mark.parametrize(("resource", "field", "extra"), _CASES)
def test_patch_null_on_not_null_field_is_422_and_names_the_field(
    resource: str, field: str, extra: dict[str, Any]
) -> None:
    spy = _Spy()
    resp = _client(spy).patch(f"/{resource}/{uuid.uuid4()}", json={**extra, field: None})

    assert resp.status_code == 422, resp.text
    assert field in resp.text
    assert not spy.called


@pytest.mark.parametrize(
    ("resource", "extra"), [("branches", {}), ("events", {"expected_version": 1})]
)
def test_patch_null_on_nullable_field_still_passes_validation(
    resource: str, extra: dict[str, Any]
) -> None:
    spy = _Spy()
    resp = _client(spy).patch(f"/{resource}/{uuid.uuid4()}", json={**extra, "description": None})

    assert spy.called  # reached the handler: validation accepted the null
    assert resp.status_code != 422
