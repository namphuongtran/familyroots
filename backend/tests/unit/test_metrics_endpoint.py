"""/internal/metrics is invisible unless explicitly enabled AND correctly tokened.

404 (not 401) on every failure path, per ADR-021: a scanner must not learn the
endpoint exists.
"""

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(), raise_server_exceptions=False)


def test_disabled_by_default(client: TestClient) -> None:
    assert client.get("/internal/metrics").status_code == 404


def test_enabled_without_a_token_header_is_404(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "METRICS_ENABLED", True)
    monkeypatch.setattr(settings, "METRICS_TOKEN", "s3cret")
    assert client.get("/internal/metrics").status_code == 404


def test_wrong_token_is_404(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "METRICS_ENABLED", True)
    monkeypatch.setattr(settings, "METRICS_TOKEN", "s3cret")
    response = client.get("/internal/metrics", headers={"X-Metrics-Token": "wrong"})
    assert response.status_code == 404


def test_non_ascii_token_is_404_not_500(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-ASCII token byte must not crash the comparison.

    Starlette decodes header bytes as latin-1, so any byte >= 0x80 produces a
    non-ASCII str; `secrets.compare_digest(str, str)` raises TypeError on those.
    A 500 here (against 404 for a nonexistent path) would let an unauthenticated
    scanner confirm the endpoint exists in one request, and would emit a Sentry
    event per probe. Headers are sent as raw bytes because httpx refuses a
    non-ASCII str header client-side.
    """
    monkeypatch.setattr(settings, "METRICS_ENABLED", True)
    monkeypatch.setattr(settings, "METRICS_TOKEN", "s3cret")
    response = client.get("/internal/metrics", headers={b"X-Metrics-Token": b"caf\xc3\xa9"})
    assert response.status_code == 404


def test_enabled_with_an_empty_token_setting_is_404(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Config validation forbids this pair, but the route must not rely on that:
    a runtime override (or a future config path) must never open the endpoint up."""
    monkeypatch.setattr(settings, "METRICS_ENABLED", True)
    monkeypatch.setattr(settings, "METRICS_TOKEN", "")
    assert client.get("/internal/metrics").status_code == 404
    assert client.get("/internal/metrics", headers={"X-Metrics-Token": ""}).status_code == 404


def test_correct_token_returns_prometheus_exposition(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "METRICS_ENABLED", True)
    monkeypatch.setattr(settings, "METRICS_TOKEN", "s3cret")
    client.get("/health")  # generate at least one sample
    response = client.get("/internal/metrics", headers={"X-Metrics-Token": "s3cret"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "http_request" in response.text


def test_metrics_route_is_hidden_from_openapi(client: TestClient) -> None:
    """The public schema is the client contract; an ops endpoint does not belong in it."""
    assert "/internal/metrics" not in client.get("/openapi.json").json()["paths"]
