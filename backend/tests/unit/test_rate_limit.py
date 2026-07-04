"""Rate limiter: proxy-aware client IP (opt-in) + bounded bucket memory."""

import time
from types import SimpleNamespace

from app.core.rate_limit import RateLimitMiddleware


def _mw(trust: bool) -> RateLimitMiddleware:
    return RateLimitMiddleware(
        app=lambda *a, **k: None,
        path_prefix="/api/v1/auth",
        max_requests=2,
        window_seconds=60,
        trust_forwarded_for=trust,
    )


def _req(path: str, *, xff: str | None = None, host: str = "10.0.0.1") -> SimpleNamespace:
    headers: dict[str, str] = {}
    if xff is not None:
        headers["x-forwarded-for"] = xff
    return SimpleNamespace(
        url=SimpleNamespace(path=path),
        headers=headers,
        client=SimpleNamespace(host=host),
    )


def test_client_ip_uses_rightmost_xff_hop_when_trusted() -> None:
    # Behind a single trusted appending proxy, the real client is the RIGHTMOST
    # hop; the leftmost ("1.2.3.4") is client-supplied/spoofable and must be ignored.
    mw = _mw(trust=True)
    ip = mw._client_ip(_req("/api/v1/auth/login", xff="1.2.3.4, 203.0.113.7"))  # type: ignore[arg-type]
    assert ip == "203.0.113.7"


def test_client_ip_ignores_xff_when_not_trusted() -> None:
    mw = _mw(trust=False)
    ip = mw._client_ip(_req("/api/v1/auth/login", xff="203.0.113.7"))  # type: ignore[arg-type]
    assert ip == "10.0.0.1"


def test_client_ip_falls_back_to_peer_when_no_xff() -> None:
    mw = _mw(trust=True)
    ip = mw._client_ip(_req("/api/v1/auth/login", host="192.168.1.5"))  # type: ignore[arg-type]
    assert ip == "192.168.1.5"


def test_empty_bucket_is_evicted() -> None:
    mw = _mw(trust=False)
    ip = "10.0.0.9"
    # A single hit far in the past → pruning at "now" empties the bucket → key dropped.
    mw._hits[ip] = [time.monotonic() - 9999]
    mw._prune(ip, time.monotonic() - mw._window)
    assert ip not in mw._hits


def test_live_hit_retained() -> None:
    mw = _mw(trust=False)
    ip = "10.0.0.10"
    now = time.monotonic()
    mw._hits[ip] = [now]
    remaining = mw._prune(ip, now - mw._window)
    assert remaining == [now]
    assert mw._hits[ip] == [now]


def test_sweep_evicts_stale_one_shot_buckets() -> None:
    # Simulate a rotate-a-new-IP-per-request attacker: many one-shot IPs whose single
    # hit has expired, plus one still-active IP. A sweep must drop only the stale ones.
    mw = _mw(trust=False)
    now = time.monotonic()
    for i in range(50):
        mw._hits[f"1.1.1.{i}"] = [now - 9999]  # expired, never returned
    mw._hits["9.9.9.9"] = [now]  # fresh
    mw._last_sweep = now - mw._window - 1  # a full window has elapsed → sweep runs
    mw._maybe_sweep(now, now - mw._window)
    assert list(mw._hits) == ["9.9.9.9"], mw._hits


def test_sweep_is_noop_within_window() -> None:
    # Bounded work: the O(n) sweep runs at most once per window, not every request.
    mw = _mw(trust=False)
    now = time.monotonic()
    mw._hits["1.1.1.1"] = [now - 9999]  # stale, but too soon to sweep
    mw._last_sweep = now
    mw._maybe_sweep(now, now - mw._window)
    assert "1.1.1.1" in mw._hits
