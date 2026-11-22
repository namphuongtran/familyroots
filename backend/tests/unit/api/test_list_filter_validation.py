"""An unknown value in a list filter answers 422, not a 200 with an empty page."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.v1.claims import admin_claims_router
from app.core.permissions import (
    ClanRole,
    RequireClanRole,
    RequireEditor,
    RequireViewer,
    require_active_user,
)
from app.core.security import get_current_clan_id, get_current_user
from app.infrastructure.dependencies import (
    get_claim_query_handler,
    get_event_query_handler,
    get_person_query_handler,
)
from app.main import create_app
from app.services.translator import load_translations

_META = {"cursor": None, "has_more": False, "limit": 20}


class _Handler:
    """Answers every list call with an empty page."""

    async def list_my_claims(self, **_: Any) -> dict[str, Any]:
        return {"data": [], "meta": _META}

    async def list_clan_claims(self, **_: Any) -> dict[str, Any]:
        return {"data": [], "meta": _META}

    async def list_persons(self, *_: Any, **__: Any) -> tuple[list[Any], dict[str, Any]]:
        return [], _META

    async def redact_pii(self, *_: Any, **__: Any) -> None:
        return None

    async def list_events(self, **_: Any) -> tuple[list[Any], dict[str, Any]]:
        return [], _META


@pytest.fixture
def client() -> TestClient:
    load_translations()
    app = create_app()
    clan_id = uuid.uuid4()
    app.dependency_overrides[get_current_user] = lambda: {"sub": str(uuid.uuid4())}
    app.dependency_overrides[get_current_clan_id] = lambda: clan_id
    app.dependency_overrides[RequireViewer.dependency] = lambda: ClanRole.VIEWER
    app.dependency_overrides[RequireEditor.dependency] = lambda: ClanRole.EDITOR
    app.dependency_overrides[require_active_user] = lambda: SimpleNamespace(id=uuid.uuid4())
    # The clan claims route's role check is a RequireClanRole instance (a DB lookup).
    for route in admin_claims_router.routes:
        for sub in getattr(getattr(route, "dependant", None), "dependencies", []):
            if isinstance(sub.call, RequireClanRole):
                app.dependency_overrides[sub.call] = lambda: SimpleNamespace(id=uuid.uuid4())
    for dep in (get_claim_query_handler, get_person_query_handler, get_event_query_handler):
        app.dependency_overrides[dep] = lambda: _Handler()
    c = TestClient(app, raise_server_exceptions=False)
    c.clan_id = clan_id  # type: ignore[attr-defined]
    return c


def _urls(client: TestClient) -> dict[str, str]:
    cid = client.clan_id  # type: ignore[attr-defined]
    return {
        "my_claims": "/api/v1/claims",
        "clan_claims": f"/api/v1/clans/{cid}/claims",
    }


@pytest.mark.parametrize("route", ["my_claims", "clan_claims"])
def test_claims_unknown_status_is_422(client: TestClient, route: str) -> None:
    resp = client.get(_urls(client)[route], params={"status": "pending"})
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize("route", ["my_claims", "clan_claims"])
@pytest.mark.parametrize("status", ["PENDING", "APPROVED", "REJECTED", "CANCELLED"])
def test_claims_valid_status_is_200(client: TestClient, route: str, status: str) -> None:
    resp = client.get(_urls(client)[route], params={"status": status})
    assert resp.status_code == 200, resp.text


def test_persons_unknown_gender_is_422(client: TestClient) -> None:
    resp = client.get("/api/v1/persons", params={"gender": "Male"})
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize("gender", ["male", "female", "unknown"])
def test_persons_valid_gender_is_200(client: TestClient, gender: str) -> None:
    assert client.get("/api/v1/persons", params={"gender": gender}).status_code == 200


def test_events_unknown_event_type_is_422(client: TestClient) -> None:
    resp = client.get("/api/v1/events", params={"event_type": "Birthday"})
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize(
    "event_type",
    ["death_anniversary", "birthday", "wedding_anniversary", "clan_ceremony", "custom"],
)
def test_events_valid_event_type_is_200(client: TestClient, event_type: str) -> None:
    assert client.get("/api/v1/events", params={"event_type": event_type}).status_code == 200
