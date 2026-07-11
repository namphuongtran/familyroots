"""GET /api/v1/claims returns the caller's claims in the {data, meta} cursor envelope."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.claims import user_claims_router
from app.core.permissions import require_active_user
from app.infrastructure.dependencies import get_claim_query_handler


class _FakeClaimQueryHandler:
    def __init__(self) -> None:
        self.last: dict[str, Any] = {}

    async def list_my_claims(
        self,
        *,
        user_id: uuid.UUID,
        status: str | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        self.last = {"user_id": user_id, "status": status, "cursor": cursor, "limit": limit}
        return {"data": [], "meta": {"cursor": None, "has_more": False, "limit": limit}}


def _client(handler: _FakeClaimQueryHandler) -> TestClient:
    app = FastAPI()
    app.include_router(user_claims_router, prefix="/api/v1/claims")
    app.dependency_overrides[require_active_user] = lambda: SimpleNamespace(id=uuid.uuid4())
    app.dependency_overrides[get_claim_query_handler] = lambda: handler
    return TestClient(app)


def test_list_my_claims_envelope_and_params() -> None:
    handler = _FakeClaimQueryHandler()
    resp = _client(handler).get("/api/v1/claims?status=PENDING&cursor=abc&limit=5")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"data", "meta"}  # {"data": [...], "meta": {...}} envelope
    assert body["data"] == []
    assert body["meta"] == {"cursor": None, "has_more": False, "limit": 5}
    assert handler.last["status"] == "PENDING"
    assert handler.last["cursor"] == "abc" and handler.last["limit"] == 5


def test_list_my_claims_rejects_bad_limit() -> None:
    assert _client(_FakeClaimQueryHandler()).get("/api/v1/claims?limit=0").status_code == 422
    assert _client(_FakeClaimQueryHandler()).get("/api/v1/claims?limit=101").status_code == 422
