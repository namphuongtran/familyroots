"""Failure throttle for `GET /internal/metrics` (ADR-040).

Deliberately *not* the auth `RateLimitMiddleware`: that one counts every request
to a path prefix and answers over-budget requests with a `429` + error envelope.
On this endpoint a 429 would be an existence oracle — no unknown path ever
returns 429 — which is exactly the property ADR-021 closed and ADR-040 must not
reopen. So this throttle produces no response of its own at all: it only tells
the handler whether to stop evaluating candidate tokens, and the handler keeps
answering with the same 404 it already returned.

Two further differences from the auth limiter, both deliberate:

* Only **failed** attempts are counted. A correct token is the scraper's normal,
  every-15-seconds behaviour and must never fill a budget, or an operator could
  throttle their own monitoring simply by scraping.
* The budget is consulted *before* the token comparison. Withholding the body
  from an over-budget request while still evaluating its guess would leave the
  guessing unlimited, which is the thing being limited.

In-memory and per-process, like the auth limiter: with several replicas each
holds its own budget, so the effective limit is `max_failures x replicas` per
window. That is the accepted trade (see ADR-040) — swap in Redis if it ever
needs to be exact.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from app.core.request_meta import resolve_client_ip

# Failed attempts allowed per client IP per window. A scraper holding the right
# token is unaffected (successes are not counted), and nothing else has any
# business probing this path, so this can be far tighter than the auth limiter's
# 20/min: a misconfigured scraper polling every 15s produces 4/min and still
# logs, while a brute-force campaign is cut to 5 guesses/min/IP.
METRICS_MAX_FAILED_ATTEMPTS = 5
METRICS_FAILURE_WINDOW_SECONDS = 60


class MetricsFailureThrottle:
    """Sliding-window counter of *failed* metrics-token attempts, keyed by client IP.

    Framework-free on purpose (it takes a header getter and a peer address, not a
    `Request`) so the window, the eviction and the proxy-trust behaviour are all
    directly unit-testable without an ASGI stack.
    """

    def __init__(
        self,
        *,
        max_failures: int = METRICS_MAX_FAILED_ATTEMPTS,
        window_seconds: int = METRICS_FAILURE_WINDOW_SECONDS,
        trust_forwarded_for: bool = False,
    ) -> None:
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self._trust_xff = trust_forwarded_for
        # {client_ip: [failure timestamp, ...]}. Only ever written on a failed
        # attempt, and only while METRICS_ENABLED is true, so a disabled endpoint
        # cannot be used to grow this at all.
        self._failures: dict[str, list[float]] = {}
        self._last_sweep = time.monotonic()
        # One-shot latch so a bypassed settings validation is reported once per
        # app rather than once per probe (see ADR-040 / app/main.py).
        self.weak_token_reported = False

    def client_ip(self, headers_get: Callable[[str], str | None], client_host: str | None) -> str:
        """Resolve the client IP with the same rightmost-XFF rule as the rate
        limiter and the audit-meta middleware (`resolve_client_ip`, ADR-021).

        Rightmost matters more here than anywhere else: the budget is per IP, so a
        spoofable left-hand `X-Forwarded-For` entry would let an attacker rotate a
        fresh identity per guess and remove the limit entirely — and, worse, let
        them exhaust the *scraper's* budget by claiming its address.
        """
        return resolve_client_ip(headers_get, client_host, self._trust_xff) or "unknown"

    def _prune(self, client_ip: str, cutoff: float) -> list[float]:
        """Drop timestamps older than *cutoff*; evict the bucket if it empties."""
        bucket = [t for t in self._failures.get(client_ip, []) if t > cutoff]
        if bucket:
            self._failures[client_ip] = bucket
        else:
            self._failures.pop(client_ip, None)
        return bucket

    def _maybe_sweep(self, now: float, cutoff: float) -> None:
        """At most once per window, evict every bucket whose newest failure expired.

        `_prune` only touches the requesting IP, so an attacker rotating source
        addresses would otherwise leave a permanent one-entry bucket per address
        and grow `_failures` without bound. Same discipline as the auth limiter.
        """
        if now - self._last_sweep < self.window_seconds:
            return
        for ip in [ip for ip, ts in self._failures.items() if not ts or ts[-1] <= cutoff]:
            del self._failures[ip]
        self._last_sweep = now

    def is_exhausted(self, client_ip: str) -> bool:
        """True when *client_ip* has used its failure budget for this window."""
        now = time.monotonic()
        cutoff = now - self.window_seconds
        self._maybe_sweep(now, cutoff)
        return len(self._prune(client_ip, cutoff)) >= self.max_failures

    def record_failure(self, client_ip: str) -> int:
        """Count one failed attempt and return the running total for the window."""
        now = time.monotonic()
        bucket = self._prune(client_ip, now - self.window_seconds)
        bucket.append(now)
        self._failures[client_ip] = bucket
        return len(bucket)

    def tracked_ips(self) -> int:
        """Size of the failure table — for the memory-bound regression test."""
        return len(self._failures)
