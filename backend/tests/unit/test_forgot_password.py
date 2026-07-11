"""forgot-password is 200-always and non-enumerating (no existence/provider leak)."""

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.infrastructure.dependencies import get_auth_session_service
from app.main import create_app
from app.services.translator import load_translations


def _client(send_mock: AsyncMock) -> TestClient:
    app = create_app()

    class _Svc:
        send_password_reset = send_mock

    app.dependency_overrides[get_auth_session_service] = lambda: _Svc()
    return TestClient(app)


def test_forgot_password_returns_200_and_calls_service() -> None:
    load_translations()
    send = AsyncMock()
    resp = _client(send).post("/api/v1/auth/forgot-password", json={"email": "a@example.com"})
    assert resp.status_code == 200
    body = resp.json()["data"]
    # localized, not the raw key
    assert body["message"] and body["message"] != "auth.password_reset_sent"
    send.assert_awaited_once()
    assert send.await_args is not None
    assert send.await_args.kwargs == {"email": "a@example.com"}


def test_forgot_password_swallows_provider_error_still_200() -> None:
    load_translations()
    send = AsyncMock(side_effect=RuntimeError("provider down"))
    resp = _client(send).post("/api/v1/auth/forgot-password", json={"email": "x@example.com"})
    assert resp.status_code == 200  # never leak provider state
    assert resp.json()["data"]["message"] != "auth.password_reset_sent"


def test_forgot_password_rejects_bad_email() -> None:
    resp = _client(AsyncMock()).post("/api/v1/auth/forgot-password", json={"email": "not-an-email"})
    assert resp.status_code == 422  # Pydantic EmailStr validation
