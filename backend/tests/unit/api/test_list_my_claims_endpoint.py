"""GET /api/v1/claims returns the caller's claims in the {data:...} envelope."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.claims import user_claims_router
from app.core.permissions import require_active_user
from app.infrastructure.dependencies import get_claim_query_handler
from app.schemas.claim import IdentityClaimPaginatedResponse


class _FakeClaimQueryHandler:
    def __init__(self) -> None:
        self.last: dict[str, Any] = {}

    async def list_my_claims(
        self, *, user_id: uuid.UUID, status: str | None = None, page: int = 1, page_size: int = 20
    ) -> IdentityClaimPaginatedResponse:
        self.last = {"user_id": user_id, "status": status, "page": page, "page_size": page_size}
        return IdentityClaimPaginatedResponse(items=[], total=0, page=page, page_size=page_size)


def _client(handler: _FakeClaimQueryHandler) -> TestClient:
    app = FastAPI()
    app.include_router(user_claims_router, prefix="/api/v1/claims")
    app.dependency_overrides[require_active_user] = lambda: SimpleNamespace(id=uuid.uuid4())
    app.dependency_overrides[get_claim_query_handler] = lambda: handler
    return TestClient(app)


def test_list_my_claims_envelope_and_params() -> None:
    handler = _FakeClaimQueryHandler()
    resp = _client(handler).get("/api/v1/claims?status=PENDING&page=2&page_size=5")
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body and body["data"]["total"] == 0  # {"data": {...}} envelope
    assert handler.last["status"] == "PENDING"
    assert handler.last["page"] == 2 and handler.last["page_size"] == 5


def test_list_my_claims_rejects_bad_page() -> None:
    resp = _client(_FakeClaimQueryHandler()).get("/api/v1/claims?page=0")
    assert resp.status_code == 422
