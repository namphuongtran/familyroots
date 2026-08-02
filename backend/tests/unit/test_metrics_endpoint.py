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
