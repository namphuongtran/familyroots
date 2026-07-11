"""Request-level tests for GET /api/v1/tree/focus/{person_id}."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.tree import router as tree_router
from app.application.tree.queries import GetFocusView
from app.core.database import get_db
from app.core.security import get_current_clan_id, get_current_user
from app.infrastructure.dependencies import get_tree_query_handler


class _RoleRow:
    role = "viewer"
    is_approved = True


class _RoleResult:
    def first(self) -> _RoleRow:
        return _RoleRow()


class _FakeDb:
    async def execute(self, *_a: Any, **_k: Any) -> _RoleResult:
        return _RoleResult()


class _FakeHandler:
    def __init__(self) -> None:
        self.last_query: GetFocusView | None = None

    async def get_focus_view(self, query: GetFocusView) -> dict[str, Any]:
        self.last_query = query
        return {
            "focus_person_id": str(query.person_id),
            "generation_of_focus": 1,
            "ancestors": [],
            "focus_subtree": {
                "id": str(query.person_id),
                "full_name": "P",
                "gender": "male",
                "children": [],
            },
        }


def _client(handler: _FakeHandler) -> TestClient:
    app = FastAPI()
    app.include_router(tree_router, prefix="/api/v1/tree")
    app.dependency_overrides[get_current_user] = lambda: {"sub": str(uuid.uuid4())}
    app.dependency_overrides[get_current_clan_id] = lambda: uuid.uuid4()
    app.dependency_overrides[get_db] = lambda: _FakeDb()
    app.dependency_overrides[get_tree_query_handler] = lambda: handler
    return TestClient(app)


def test_focus_defaults_and_envelope() -> None:
    handler = _FakeHandler()
    pid = uuid.uuid4()
    resp = _client(handler).get(f"/api/v1/tree/focus/{pid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["focus_person_id"] == str(pid)
    assert handler.last_query is not None
    assert handler.last_query.descendant_depth == 2  # default window
    assert handler.last_query.ancestor_depth == 50


def test_focus_param_bounds_rejected() -> None:
    handler = _FakeHandler()
    pid = uuid.uuid4()
    client = _client(handler)
    assert client.get(f"/api/v1/tree/focus/{pid}?descendants=0").status_code == 422
    assert client.get(f"/api/v1/tree/focus/{pid}?descendants=7").status_code == 422
    assert client.get(f"/api/v1/tree/focus/{pid}?ancestors=51").status_code == 422
