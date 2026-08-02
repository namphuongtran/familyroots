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
    # Must NOT be /health or /internal/metrics — both are in excluded_handlers, so
    # they record nothing and the exposition would contain only the #HELP/#TYPE
    # preamble of an empty metric. A 401 still counts as a recorded request.
    assert client.get("/api/v1/persons").status_code in {401, 403, 404, 422}
    response = client.get("/internal/metrics", headers={"X-Metrics-Token": "s3cret"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    samples = [
        line for line in response.text.splitlines() if line.startswith("http_requests_total{")
    ]
    assert samples, response.text


def test_excluded_handlers_are_anchored(monkeypatch: pytest.MonkeyPatch) -> None:
    """`excluded_handlers` are unanchored `re.search` patterns, so a bare "/health"
    would silently drop every route merely containing it from the metrics."""
    application = create_app()

    @application.get("/healthz-probe")
    async def probe() -> dict[str, str]:
        return {"status": "ok"}

    local = TestClient(application, raise_server_exceptions=False)
    monkeypatch.setattr(settings, "METRICS_ENABLED", True)
    monkeypatch.setattr(settings, "METRICS_TOKEN", "s3cret")
    assert local.get("/healthz-probe").status_code == 200
    body = local.get("/internal/metrics", headers={"X-Metrics-Token": "s3cret"}).text
    assert 'handler="/healthz-probe"' in body


def test_health_itself_stays_excluded(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """The anchors must still exclude what they were added for — /health is polled
    every few seconds by the platform and would dominate the series."""
    monkeypatch.setattr(settings, "METRICS_ENABLED", True)
    monkeypatch.setattr(settings, "METRICS_TOKEN", "s3cret")
    client.get("/health")
    body = client.get("/internal/metrics", headers={"X-Metrics-Token": "s3cret"}).text
    assert 'handler="/health"' not in body


def test_metrics_route_is_hidden_from_openapi(client: TestClient) -> None:
    """The public schema is the client contract; an ops endpoint does not belong in it."""
    assert "/internal/metrics" not in client.get("/openapi.json").json()["paths"]


def test_documented_middleware_order_matches_reality() -> None:
    """`Instrumentator.instrument()` is a hidden `add_middleware` call; when it sat
    outside the ordering block in `create_app`, three documents described an order
    the app did not have. Lock the real one in."""
    # getattr: Starlette types `cls` as _MiddlewareFactory, which has no __name__.
    order = [getattr(m.cls, "__name__", repr(m.cls)) for m in create_app().user_middleware]
    expected = [
        "PrometheusInstrumentatorMiddleware",
        "TrustedHostMiddleware",
        "CORSMiddleware",
        "TraceContextMiddleware",
        "LanguageMiddleware",
        "RequestMetaMiddleware",
        *(["SentryMiddleware"] if settings.SENTRY_DSN else []),
        "RateLimitMiddleware",
    ]
    assert order == expected
