"""Rate limiting middleware for auth endpoints, over a pluggable count store (ADR-072).

Sliding-window log per client IP. Proxy-aware (opt-in via ``trust_forwarded_for``).
Where the log lives is a ``RateLimitStore``: in process memory per instance
(``InMemoryRateLimitStore``, development, tests, the e2e harness), or one store every
instance shares (``app/infrastructure/upstash_rate_limit_store.py``, production on Vercel).
If the shared store fails, the request is decided by this instance's in-memory bucket,
so sign-in never fails because of the store.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Protocol

import sentry_sdk
from starlette._utils import get_route_path
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import compile_path

from app.core.request_meta import resolve_client_ip

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RateDecision:
    """Whether one request was admitted. A refusal says how many seconds until a slot frees."""

    admitted: bool
    retry_after: int = 0


class RateLimitStoreUnavailableError(Exception):
    """The store could not decide: an error, a timeout or an answer it could not read."""


class RateLimitStore(Protocol):
    async def hit(
        self, key: str, *, max_requests: int, window_seconds: int, now: float
    ) -> RateDecision:
        """Decide one request under *key* and record it if admitted, as one atomic step.

        The window slides: a hit counts while it is newer than ``now - window_seconds``.
        A refused request is not recorded. ``retry_after`` is taken from the oldest
        admitted hit still in the window, plus one second. *now* is wall-clock seconds,
        because a shared store compares hits recorded by different processes.
        Raises ``RateLimitStoreUnavailableError`` when the store cannot decide.
        """
        ...


def retry_after_seconds(oldest_hit: float, cutoff: float) -> int:
    """Seconds until the oldest admitted hit leaves the window, rounded up past it."""
    return int(oldest_hit - cutoff) + 1


class InMemoryRateLimitStore:
    """The log in this process's memory, so one per instance.

    Memory-bounded: the current key's bucket is pruned on every hit, and a periodic global
    sweep evicts buckets for keys that never return (so a rotate-a-new-IP-per-request
    attacker can't leak memory without bound).
    """

    def __init__(self) -> None:
        # {key: [timestamp, ...]}; the active key's bucket is evicted when empty in _prune,
        # and stale buckets are swept globally every window (_maybe_sweep).
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._last_sweep: float | None = None

    async def hit(
        self, key: str, *, max_requests: int, window_seconds: int, now: float
    ) -> RateDecision:
        cutoff = now - window_seconds
        self._maybe_sweep(now, cutoff, window_seconds)
        bucket = self._prune(key, cutoff)
        if len(bucket) >= max_requests:
            return RateDecision(admitted=False, retry_after=retry_after_seconds(bucket[0], cutoff))
        self._hits[key].append(now)
        return RateDecision(admitted=True)

    def _prune(self, key: str, cutoff: float) -> list[float]:
        """Drop timestamps older than cutoff; evict the bucket if it empties."""
        bucket = [t for t in self._hits.get(key, []) if t > cutoff]
        if bucket:
            self._hits[key] = bucket
        else:
            self._hits.pop(key, None)
        return bucket

    def _maybe_sweep(self, now: float, cutoff: float, window_seconds: int) -> None:
        """At most once per window, evict every bucket whose newest hit is expired.

        _prune only touches the requesting key, so a one-shot IP would otherwise leave
        a permanent single-entry bucket and let an attacker rotating source IPs grow
        ``_hits`` without bound. This caps it to roughly the IPs seen in the last window.

        The peak between sweeps is still proportional to attack throughput (one bucket
        per new IP per window); a hard ``len(_hits)`` cap would make the ceiling
        rate-independent, but is unnecessary at auth-endpoint volumes.
        """
        if self._last_sweep is None:
            self._last_sweep = now
        if now - self._last_sweep < window_seconds:
            return
        stale = [key for key, ts in self._hits.items() if not ts or ts[-1] <= cutoff]
        for key in stale:
            del self._hits[key]
        self._last_sweep = now


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate-limit specific paths by client IP, whatever the method.

    Args:
        app: The ASGI application.
        counted_paths: Only requests whose path matches one of these route templates are
            counted and limited, all in one bucket per IP. A ``{name}`` segment matches any
            one path segment, as in the router (``/api/v1/invitations/{token}/accept``).
            Every other path passes uncounted.
        max_requests: Maximum requests allowed within the window.
        window_seconds: Time window in seconds.
        trust_forwarded_for: When True, derive the client IP from the first hop
            of the ``X-Forwarded-For`` header (use only behind a trusted proxy);
            otherwise use the direct socket peer.
        store: Where the count lives. None keeps it in this instance's memory. A shared
            store that raises ``RateLimitStoreUnavailableError`` hands the request to this
            instance's in-memory bucket instead, and Sentry gets a warning.
    """

    def __init__(
        self,
        app: Any,
        *,
        counted_paths: Iterable[str],
        max_requests: int = 20,
        window_seconds: int = 60,
        trust_forwarded_for: bool = False,
        store: RateLimitStore | None = None,
    ) -> None:
        super().__init__(app)
        self._counted = tuple(compile_path(template)[0] for template in counted_paths)
        self._max = max_requests
        self._window = window_seconds
        self._trust_xff = trust_forwarded_for
        self._local = InMemoryRateLimitStore()
        self._store: RateLimitStore = store if store is not None else self._local
        self._last_store_warning: float | None = None

    def _client_ip(self, request: Request) -> str:
        """Resolve the client IP, honoring X-Forwarded-For only when trusted.

        Behind a single trusted proxy/LB that *appends* the peer it observed,
        or one that overwrites the header with it (Vercel), the trustworthy
        client IP is the RIGHTMOST X-Forwarded-For entry. The leftmost entries
        are client-supplied and spoofable — using them would let an attacker
        rotate a fake IP per request to bypass the limit and inflate bucket
        memory. (Assumes exactly one trusted proxy; multiple proxies would need
        a configurable trusted-hop count.)
        """
        return (
            resolve_client_ip(
                request.headers.get,
                request.client.host if request.client else None,
                self._trust_xff,
            )
            or "unknown"
        )

    async def _decide(self, client_ip: str, now: float) -> RateDecision:
        try:
            return await self._store.hit(
                client_ip, max_requests=self._max, window_seconds=self._window, now=now
            )
        except RateLimitStoreUnavailableError as exc:
            self._warn_store_unavailable(exc, now)
            return await self._local.hit(
                client_ip, max_requests=self._max, window_seconds=self._window, now=now
            )

    def _warn_store_unavailable(self, exc: RateLimitStoreUnavailableError, now: float) -> None:
        """Log every fallback, and tell Sentry at most once a window per instance.

        An outage fails every counted request, and one Sentry event each would spend the
        project's quota on a single fact."""
        logger.warning("rate limit store unavailable, deciding in memory: %s", exc)
        if self._last_store_warning is not None and now - self._last_store_warning < self._window:
            return
        self._last_store_warning = now
        sentry_sdk.capture_message(
            f"Rate limit store unavailable, falling back to the in-memory bucket: {exc}",
            level="warning",
        )

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # The path the router matches, not request.url.path: that one re-parses the decoded
        # path as a URL, so a "%3F" or "%23" inside a token would cut it short and the request
        # would reach accept uncounted.
        path = get_route_path(request.scope)
        if not any(pattern.match(path) for pattern in self._counted):
            return await call_next(request)

        decision = await self._decide(self._client_ip(request), time.time())
        if not decision.admitted:
            # Middleware runs outside the exception-handler layer, so emit the
            # standard {error:{code,message,detail}} envelope directly (clients parse
            # error.code uniformly). LanguageMiddleware runs before this one, so the
            # locale is set; t() falls back to vi otherwise.
            from app.services.translator import t

            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "rate_limited",
                        "message": t("error.rate_limited"),
                        "detail": {"retry_after": decision.retry_after},
                    }
                },
                headers={"Retry-After": str(decision.retry_after)},
            )

        return await call_next(request)
