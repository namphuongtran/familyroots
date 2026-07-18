"""Request-level tests for GET /api/v1/me/clans and POST /api/v1/me/clans/{id}/select.

``MeQueryHandler.list_clans`` returns a plain list of membership dicts, and the
ROUTE wraps that into the standard ``{"data": ...}`` envelope — a plain canonical
array with NO ``meta`` key (the old non-canonical ``meta: {"count": n}`` was
intentionally removed, ADR-024).
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.me import router as me_router
from app.core.security import get_current_user
from app.infrastructure.dependencies import get_me_query_handler


class _FakeMeQueryHandler:
    async def list_clans(self, *, user_id: str) -> list[dict[str, Any]]:
        return [
            {
                "clan_id": str(uuid.uuid4()),
                "clan_name": "N",
                "clan_slug": "n",
                "role": "admin",
                "joined_at": None,
            }
        ]

    async def select_clan(self, *, user_id: str, clan_id: uuid.UUID) -> dict[str, Any]:
        return {
            "clan_id": str(clan_id),
            "clan_name": "N",
            "clan_slug": "n",
            "role": "admin",
            "message": "Clan selected. Set X-Current-Clan-Id header to this clan_id.",
        }


def _client(handler: _FakeMeQueryHandler) -> TestClient:
    app = FastAPI()
    app.include_router(me_router, prefix="/api/v1/me")
    app.dependency_overrides[get_current_user] = lambda: {"sub": str(uuid.uuid4())}
    app.dependency_overrides[get_me_query_handler] = lambda: handler
    return TestClient(app)


def test_list_my_clans_envelope() -> None:
    client = _client(_FakeMeQueryHandler())
    resp = client.get("/api/v1/me/clans")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body.keys()) == {"data"}
    assert isinstance(body["data"], list)
    assert body["data"][0]["role"] == "admin"


def test_select_clan_envelope() -> None:
    client = _client(_FakeMeQueryHandler())
    clan_id = uuid.uuid4()
    resp = client.post(f"/api/v1/me/clans/{clan_id}/select")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body.keys()) == {"data"}
    assert body["data"]["clan_id"] == str(clan_id)
    assert body["data"]["role"] == "admin"
