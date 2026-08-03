"""/internal/metrics is invisible unless explicitly enabled AND correctly tokened.

404 (not 401) on every failure path, per ADR-021: a scanner must not learn the
endpoint exists. ADR-040 adds a length floor on the configured token and a
failure throttle that keeps that 404 unchanged.
"""

import logging

import pytest
from fastapi.testclient import TestClient

from app.core.config import MIN_METRICS_TOKEN_LENGTH, settings
from app.core.metrics_guard import METRICS_MAX_FAILED_ATTEMPTS
from app.main import create_app

# Sits *exactly* on the ADR-040 floor, which
# `test_a_token_exactly_at_the_floor_is_accepted` asserts and depends on: it checks the
# boundary from above, so this must be the shortest token the floor accepts, not merely
# a long one. Sliced from the constant rather than hardcoded to 32 so raising the floor
# lengthens this instead of silently turning that boundary test into a no-op.
#
# Assembled from short pieces rather than written out: a bare 32-character hex literal is
# indistinguishable from a leaked credential, and gitleaks rightly flagged the first
# version of this line as `generic-api-key`. Silencing the scanner with an allowlist
# entry would train everyone to wave through the exact shape it exists to catch.
#
# The previous "s3cret" is now rejected by both the settings validator and the handler's
# runtime backstop, so it can no longer stand in for a real token.
_TOKEN = (("not-a-real-token-" + "0123456789abcdef") * 2)[:MIN_METRICS_TOKEN_LENGTH]


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(), raise_server_exceptions=False)


def test_disabled_by_default(client: TestClient) -> None:
    assert client.get("/internal/metrics").status_code == 404


def test_enabled_without_a_token_header_is_404(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "METRICS_ENABLED", True)
    monkeypatch.setattr(settings, "METRICS_TOKEN", _TOKEN)
    assert client.get("/internal/metrics").status_code == 404


def test_wrong_token_is_404(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "METRICS_ENABLED", True)
    monkeypatch.setattr(settings, "METRICS_TOKEN", _TOKEN)
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
    monkeypatch.setattr(settings, "METRICS_TOKEN", _TOKEN)
    response = client.get("/internal/metrics", headers={b"X-Metrics-Token": b"caf\xc3\xa9"})
    assert response.status_code == 404


def test_surrogate_configured_token_is_404_not_500(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A METRICS_TOKEN holding bytes that are not valid UTF-8 must not crash the
    comparison either.

    os.environ decodes with surrogateescape (PEP 383): a raw env var byte >= 0x80
    that isn't part of a valid UTF-8 sequence surfaces as a surrogate code point in
    the Python str. Re-encoding that with plain .encode("utf-8") raises
    UnicodeEncodeError, which -- same as the header-side TypeError this endpoint
    already guards against -- would 500 for any request carrying a token header
    and 404 for one without, letting an operator misconfiguration reopen the
    ADR-021 existence oracle this handler exists to close.

    Padded to clear the ADR-040 length floor so this still exercises the
    comparison rather than short-circuiting on the weak-token check above it --
    `metrics_token_weakness` inspects length and character variety only, so a
    surrogate code point reaches the encode step exactly as before.
    """
    monkeypatch.setattr(settings, "METRICS_ENABLED", True)
    monkeypatch.setattr(settings, "METRICS_TOKEN", "s3cr\udcff" + "0123456789abcdef01234567890a")
    response = client.get("/internal/metrics", headers={"X-Metrics-Token": "anything"})
    assert response.status_code == 404


def test_non_ascii_configured_token_can_authenticate(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Comparing exact bytes on both sides (latin-1 for the wire header, utf-8 with
    surrogateescape for the configured value) means a non-ASCII token that the
    scraper sends as the identical raw bytes now matches -- unlike the previous
    utf-8-on-both-sides comparison, which compared mojibake against the original
    string and could never match a non-ASCII token."""
    monkeypatch.setattr(settings, "METRICS_ENABLED", True)
    # Padded to clear the ADR-040 length floor; the non-ASCII prefix is what this
    # test is about.
    monkeypatch.setattr(settings, "METRICS_TOKEN", "café" + "0123456789abcdef01234567890a")
    # "café".encode("utf-8") == b"caf\xc3\xa9"; sent as raw bytes because httpx
    # refuses a non-ASCII str header client-side (same constraint as the existing
    # non-ASCII-header test above).
    response = client.get(
        "/internal/metrics",
        headers={b"X-Metrics-Token": b"caf\xc3\xa9" + b"0123456789abcdef01234567890a"},
    )
    assert response.status_code == 200


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
    monkeypatch.setattr(settings, "METRICS_TOKEN", _TOKEN)
    # Must NOT be /health or /internal/metrics — both are in excluded_handlers, so
    # they record nothing and the exposition would contain only the #HELP/#TYPE
    # preamble of an empty metric. A 401 still counts as a recorded request.
    assert client.get("/api/v1/persons").status_code in {401, 403, 404, 422}
    response = client.get("/internal/metrics", headers={"X-Metrics-Token": _TOKEN})
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
    monkeypatch.setattr(settings, "METRICS_TOKEN", _TOKEN)
    assert local.get("/healthz-probe").status_code == 200
    body = local.get("/internal/metrics", headers={"X-Metrics-Token": _TOKEN}).text
    assert 'handler="/healthz-probe"' in body


def test_health_itself_stays_excluded(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """The anchors must still exclude what they were added for — /health is polled
    every few seconds by the platform and would dominate the series."""
    monkeypatch.setattr(settings, "METRICS_ENABLED", True)
    monkeypatch.setattr(settings, "METRICS_TOKEN", _TOKEN)
    client.get("/health")
    body = client.get("/internal/metrics", headers={"X-Metrics-Token": _TOKEN}).text
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


# ─── ADR-040: length floor + failure throttle ──────────────────────────────────


def _enable(monkeypatch: pytest.MonkeyPatch, token: str = _TOKEN) -> None:
    monkeypatch.setattr(settings, "METRICS_ENABLED", True)
    monkeypatch.setattr(settings, "METRICS_TOKEN", token)


def test_weak_configured_token_serves_nothing_even_with_the_right_header(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The runtime backstop, independent of settings validation.

    Settings rejects a short token at boot, but the handler must not *rely* on
    that: a monkeypatch, a directly-constructed Settings, or a future config path
    that skips validation must fail closed. Presenting the exact configured token
    is the sharpest form of the test — if the floor were only enforced in config,
    this would return 200 and a one-character METRICS_TOKEN would be live.
    """
    _enable(monkeypatch, "short")
    response = client.get("/internal/metrics", headers={"X-Metrics-Token": "short"})
    assert response.status_code == 404


def test_a_token_one_character_below_the_floor_is_refused(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Boundary, from below — the guard must not be off by one."""
    token = "b" + "a1b2c3d4e5f60718293a4b5c6d7e8f9"[: MIN_METRICS_TOKEN_LENGTH - 2]
    assert len(token) == MIN_METRICS_TOKEN_LENGTH - 1
    _enable(monkeypatch, token)
    assert client.get("/internal/metrics", headers={"X-Metrics-Token": token}).status_code == 404


def test_a_token_exactly_at_the_floor_is_accepted(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Boundary, from above — the floor must not reject a compliant token."""
    assert len(_TOKEN) == MIN_METRICS_TOKEN_LENGTH
    _enable(monkeypatch)
    assert client.get("/internal/metrics", headers={"X-Metrics-Token": _TOKEN}).status_code == 200


def test_long_but_degenerate_token_is_refused(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A length floor alone would accept 64 identical characters, which is long and
    trivially guessable. The distinct-character check rejects that shape. It is not
    an entropy measurement (see ADR-040) — "abcdefgh" x 8 would pass."""
    _enable(monkeypatch, "a" * 64)
    assert client.get("/internal/metrics", headers={"X-Metrics-Token": "a" * 64}).status_code == 404


def test_weak_token_is_reported_once_per_app_not_once_per_probe(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A silent 404 is indistinguishable from "switched off" to whoever is debugging
    the scrape, so a bypassed validation must say so — but once, or a scanner could
    drive unbounded log volume."""
    _enable(monkeypatch, "short")
    with caplog.at_level(logging.ERROR, logger="app.main"):
        for _ in range(5):
            client.get("/internal/metrics", headers={"X-Metrics-Token": "short"})
    assert len([r for r in caplog.records if "METRICS_TOKEN" in r.getMessage()]) == 1


def test_failed_attempts_are_throttled_and_stop_being_evaluated(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The core of the rate limit: past the budget the candidate token is not
    compared at all.

    Proven the only way that means anything — burn the budget with wrong guesses,
    then present the CORRECT token and require a 404. If the throttle merely
    withheld the body while still comparing, this would return 200 and the number
    of guesses an attacker gets would still be unbounded.
    """
    _enable(monkeypatch)
    for _ in range(METRICS_MAX_FAILED_ATTEMPTS):
        assert client.get("/internal/metrics", headers={"X-Metrics-Token": "no"}).status_code == 404
    assert client.get("/internal/metrics", headers={"X-Metrics-Token": _TOKEN}).status_code == 404


def test_the_throttle_never_answers_429(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-021 must survive ADR-040. No unknown path returns 429, so a 429 here
    would confirm to an unauthenticated scanner both that /internal/metrics exists
    and that it is worth guarding — a worse oracle than the 401 this endpoint
    already refuses to send."""
    _enable(monkeypatch)
    codes = {
        client.get("/internal/metrics", headers={"X-Metrics-Token": "no"}).status_code
        for _ in range(METRICS_MAX_FAILED_ATTEMPTS * 3)
    }
    assert codes == {404}


def test_a_throttled_response_is_identical_to_a_nonexistent_path(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Non-enumeration is about indistinguishability, not just the status code: an
    attacker comparing a throttled probe against a random path must see the same
    status, the same body and no extra headers (no Retry-After, nothing)."""
    _enable(monkeypatch)
    for _ in range(METRICS_MAX_FAILED_ATTEMPTS + 2):
        throttled = client.get("/internal/metrics", headers={"X-Metrics-Token": "no"})
    unknown = client.get("/internal/does-not-exist-at-all")

    assert throttled.status_code == unknown.status_code == 404
    assert throttled.json() == unknown.json()
    assert "retry-after" not in {k.lower() for k in throttled.headers}
    volatile = {"date", "traceparent", "content-length"}
    assert {k.lower() for k in throttled.headers} - volatile == {
        k.lower() for k in unknown.headers
    } - volatile


def test_successful_scrapes_never_consume_the_failure_budget(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A Prometheus scraper hits this path every few seconds forever. If successes
    counted, enabling metrics would throttle the monitoring it exists to serve —
    and an attacker could blind an operator by exhausting a shared budget."""
    _enable(monkeypatch)
    for _ in range(METRICS_MAX_FAILED_ATTEMPTS * 4):
        assert (
            client.get("/internal/metrics", headers={"X-Metrics-Token": _TOKEN}).status_code == 200
        )
    # Budget untouched: a wrong guess is still evaluated (rejected, not throttled),
    # and the next correct scrape still succeeds.
    assert client.get("/internal/metrics", headers={"X-Metrics-Token": "no"}).status_code == 404
    assert client.get("/internal/metrics", headers={"X-Metrics-Token": _TOKEN}).status_code == 200


def test_a_disabled_endpoint_records_no_failures(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Metrics is off by default, so this path takes internet background noise.
    Counting it would let anyone grow the throttle's table on an endpoint that has
    no secret to guess in the first place."""
    monkeypatch.setattr(settings, "METRICS_ENABLED", False)
    for _ in range(50):
        client.get("/internal/metrics", headers={"X-Metrics-Token": "no"})
    assert client.app.state.metrics_guard.tracked_ips() == 0  # type: ignore[attr-defined]


def test_failed_attempts_are_logged_but_bounded(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """§3.1's other half: a failed attempt used to leave no trace at all. It now
    logs — and, because the exhaustion check short-circuits ahead of the log, at
    most max_failures lines per IP per window, so the logging cannot be amplified
    into a cost attack. The attempted token must never appear in the record."""
    _enable(monkeypatch)
    with caplog.at_level(logging.WARNING, logger="app.main"):
        for _ in range(METRICS_MAX_FAILED_ATTEMPTS * 4):
            client.get("/internal/metrics", headers={"X-Metrics-Token": "guess-me"})
    records = [r for r in caplog.records if "/internal/metrics token" in r.getMessage()]
    assert len(records) == METRICS_MAX_FAILED_ATTEMPTS
    assert not any("guess-me" in r.getMessage() for r in records)
