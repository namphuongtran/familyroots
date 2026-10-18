"""Rate limiter: proxy-aware client IP (opt-in) + the in-memory store's bounded memory."""

import time
from types import SimpleNamespace

from app.core.rate_limit import InMemoryRateLimitStore, RateLimitMiddleware

_WINDOW = 60


def _mw(trust: bool) -> RateLimitMiddleware:
    return RateLimitMiddleware(
        app=lambda *a, **k: None,
        counted_paths=("/api/v1/auth/login",),
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
    store = InMemoryRateLimitStore()
    ip = "10.0.0.9"
    # A single hit far in the past → pruning at "now" empties the bucket → key dropped.
    store._hits[ip] = [time.time() - 9999]
    store._prune(ip, time.time() - _WINDOW)
    assert ip not in store._hits


def test_live_hit_retained() -> None:
    store = InMemoryRateLimitStore()
    ip = "10.0.0.10"
    now = time.time()
    store._hits[ip] = [now]
    remaining = store._prune(ip, now - _WINDOW)
    assert remaining == [now]
    assert store._hits[ip] == [now]


def test_sweep_evicts_stale_one_shot_buckets() -> None:
    # Simulate a rotate-a-new-IP-per-request attacker: many one-shot IPs whose single
    # hit has expired, plus one still-active IP. A sweep must drop only the stale ones.
    store = InMemoryRateLimitStore()
    now = time.time()
    for i in range(50):
        store._hits[f"1.1.1.{i}"] = [now - 9999]  # expired, never returned
    store._hits["9.9.9.9"] = [now]  # fresh
    store._last_sweep = now - _WINDOW - 1  # a full window has elapsed → sweep runs
    store._maybe_sweep(now, now - _WINDOW, _WINDOW)
    assert list(store._hits) == ["9.9.9.9"], store._hits


def test_sweep_is_noop_within_window() -> None:
    # Bounded work: the O(n) sweep runs at most once per window, not every request.
    store = InMemoryRateLimitStore()
    now = time.time()
    store._hits["1.1.1.1"] = [now - 9999]  # stale, but too soon to sweep
    store._last_sweep = now
    store._maybe_sweep(now, now - _WINDOW, _WINDOW)
    assert "1.1.1.1" in store._hits


async def test_in_memory_store_refuses_at_the_budget_and_does_not_record_refusals() -> None:
    """The rules the shared store must match, read on the in-memory one.

    tests/integration/test_rate_limit_shared_store.py reads the same three facts on Upstash."""
    store = InMemoryRateLimitStore()
    now = 1_000_000.0
    decisions = [
        await store.hit("203.0.113.9", max_requests=20, window_seconds=_WINDOW, now=now + i)
        for i in range(22)
    ]

    assert [d.admitted for d in decisions] == [True] * 20 + [False, False]
    assert decisions[20].retry_after == 41
    later = now + 60.5
    assert (
        await store.hit("203.0.113.9", max_requests=20, window_seconds=_WINDOW, now=later)
    ).admitted
    assert not (
        await store.hit("203.0.113.9", max_requests=20, window_seconds=_WINDOW, now=later)
    ).admitted
