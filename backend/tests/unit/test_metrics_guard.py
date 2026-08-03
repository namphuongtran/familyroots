"""The /internal/metrics failure throttle (ADR-040).

Tested directly rather than through TestClient because the properties that matter
— per-IP isolation, window expiry, bounded memory, unspoofable IP resolution —
need many distinct client addresses, and TestClient reports one fixed peer.
"""

from collections.abc import Callable

import pytest

from app.core.metrics_guard import (
    METRICS_FAILURE_WINDOW_SECONDS,
    METRICS_MAX_FAILED_ATTEMPTS,
    MetricsFailureThrottle,
)

pytestmark = pytest.mark.unit


def _headers(**kw: str) -> Callable[[str], str | None]:
    lowered = {k.replace("_", "-").lower(): v for k, v in kw.items()}
    return lowered.get


def test_budget_is_per_ip() -> None:
    """One attacker must not be able to throttle everyone else — the same property
    that keeps a hostile probe from starving the real scraper."""
    guard = MetricsFailureThrottle()
    for _ in range(METRICS_MAX_FAILED_ATTEMPTS):
        guard.record_failure("10.0.0.1")
    assert guard.is_exhausted("10.0.0.1") is True
    assert guard.is_exhausted("10.0.0.2") is False


def test_exhaustion_is_at_the_limit_not_past_it() -> None:
    guard = MetricsFailureThrottle()
    for i in range(METRICS_MAX_FAILED_ATTEMPTS - 1):
        guard.record_failure("10.0.0.1")
        assert guard.is_exhausted("10.0.0.1") is False, i
    guard.record_failure("10.0.0.1")
    assert guard.is_exhausted("10.0.0.1") is True


def test_the_window_expires(monkeypatch: pytest.MonkeyPatch) -> None:
    """A throttle that never released would turn one bad afternoon into a permanent
    outage for that address."""
    clock = [1000.0]
    monkeypatch.setattr("app.core.metrics_guard.time.monotonic", lambda: clock[0])
    guard = MetricsFailureThrottle()
    for _ in range(METRICS_MAX_FAILED_ATTEMPTS):
        guard.record_failure("10.0.0.1")
    assert guard.is_exhausted("10.0.0.1") is True

    clock[0] += METRICS_FAILURE_WINDOW_SECONDS + 1
    assert guard.is_exhausted("10.0.0.1") is False


def test_memory_is_bounded_against_ip_rotation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Per-IP buckets are an attacker-controlled dict. Without the periodic sweep, an
    attacker rotating source addresses leaves one permanent entry per address and
    grows it without bound — the same failure mode the auth limiter guards against.
    """
    clock = [1000.0]
    monkeypatch.setattr("app.core.metrics_guard.time.monotonic", lambda: clock[0])
    guard = MetricsFailureThrottle()
    for i in range(500):
        guard.record_failure(f"10.1.{i // 256}.{i % 256}")
    assert guard.tracked_ips() == 500

    # A single request two windows later must evict every expired bucket, not just
    # the requesting one.
    clock[0] += METRICS_FAILURE_WINDOW_SECONDS * 2 + 1
    guard.is_exhausted("192.168.0.1")
    assert guard.tracked_ips() == 0


def test_recording_a_failure_reports_the_running_count() -> None:
    """The handler logs this number; an always-1 counter would hide the campaign."""
    guard = MetricsFailureThrottle()
    assert [guard.record_failure("10.0.0.1") for _ in range(3)] == [1, 2, 3]


def test_client_ip_ignores_forwarded_for_when_untrusted() -> None:
    """Directly exposed: X-Forwarded-For is caller-supplied, so honouring it would
    hand the attacker a fresh budget per guess."""
    guard = MetricsFailureThrottle(trust_forwarded_for=False)
    ip = guard.client_ip(_headers(x_forwarded_for="1.2.3.4"), "203.0.113.9")
    assert ip == "203.0.113.9"


def test_client_ip_takes_the_rightmost_forwarded_for_when_trusted() -> None:
    """Behind one appending proxy only the rightmost entry was written by the proxy.
    Taking the leftmost would let an attacker both rotate identities and *claim the
    scraper's address*, exhausting the budget of the one client that must never be
    blocked."""
    guard = MetricsFailureThrottle(trust_forwarded_for=True)
    ip = guard.client_ip(_headers(x_forwarded_for="1.2.3.4, 203.0.113.9"), "10.0.0.1")
    assert ip == "203.0.113.9"


def test_client_ip_falls_back_to_a_placeholder() -> None:
    """A missing peer must not become a None key that collides with nothing."""
    guard = MetricsFailureThrottle(trust_forwarded_for=True)
    assert guard.client_ip(_headers(), None) == "unknown"
