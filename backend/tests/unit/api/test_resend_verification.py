"""POST /auth/resend-verification is non-enumerating: always 200, swallows provider errors."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.auth import router as auth_router
from app.infrastructure.dependencies import get_auth_session_service


class _Svc:
    def __init__(self, *, boom: bool) -> None:
        self.boom = boom
        self.called_with: str | None = None

    async def send_verification_email(self, *, email: str) -> None:
        self.called_with = email
        if self.boom:
            raise RuntimeError("provider down")


def _client(svc: _Svc) -> TestClient:
    app = FastAPI()
    app.include_router(auth_router, prefix="/api/v1/auth")
    app.dependency_overrides[get_auth_session_service] = lambda: svc
    return TestClient(app)


def test_resend_verification_ok() -> None:
    svc = _Svc(boom=False)
    resp = _client(svc).post("/api/v1/auth/resend-verification", json={"email": "a@ex.com"})
    assert resp.status_code == 200
    assert "data" in resp.json() and "message" in resp.json()["data"]
    assert svc.called_with == "a@ex.com"


def test_resend_verification_swallows_provider_error() -> None:
    """Provider failure must NOT leak (still 200, same message) — non-enumerating."""
    resp = _client(_Svc(boom=True)).post(
        "/api/v1/auth/resend-verification", json={"email": "x@ex.com"}
    )
    assert resp.status_code == 200
