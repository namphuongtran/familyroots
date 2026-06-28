"""In-memory rate limiting middleware for auth endpoints.

Sliding-window counter per client IP. Proxy-aware (opt-in via
``trust_forwarded_for``) and memory-bounded (empty buckets are evicted).
For multi-replica deployments, swap the in-memory store for Redis.
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate-limit specific path prefixes by client IP.

    Args:
        app: The ASGI application.
        path_prefix: Only apply limits to paths starting with this prefix.
        max_requests: Maximum requests allowed within the window.
        window_seconds: Time window in seconds.
        trust_forwarded_for: When True, derive the client IP from the first hop
            of the ``X-Forwarded-For`` header (use only behind a trusted proxy);
            otherwise use the direct socket peer.
    """

    def __init__(
        self,
        app: Any,
        *,
        path_prefix: str = "/api/v1/auth",
        max_requests: int = 20,
        window_seconds: int = 60,
        trust_forwarded_for: bool = False,
    ) -> None:
        super().__init__(app)
        self._prefix = path_prefix
        self._max = max_requests
        self._window = window_seconds
        self._trust_xff = trust_forwarded_for
        # {client_ip: [timestamp, ...]}; empty buckets are evicted in _prune.
        self._hits: dict[str, list[float]] = defaultdict(list)

    def _client_ip(self, request: Request) -> str:
        """Resolve the client IP, honoring X-Forwarded-For only when trusted.

        Behind a single trusted proxy/LB (e.g. Render) that *appends* the peer
        it observed, the trustworthy client IP is the RIGHTMOST X-Forwarded-For
        entry. The leftmost entries are client-supplied and spoofable — using
        them would let an attacker rotate a fake IP per request to bypass the
        limit and inflate bucket memory. (Assumes exactly one trusted appending
        proxy; multiple proxies would need a configurable trusted-hop count.)
        """
        if self._trust_xff:
            xff = request.headers.get("x-forwarded-for")
            if xff:
                return xff.split(",")[-1].strip()
        return request.client.host if request.client else "unknown"

    def _prune(self, client_ip: str, cutoff: float) -> list[float]:
        """Drop timestamps older than cutoff; evict the bucket if it empties."""
        bucket = [t for t in self._hits.get(client_ip, []) if t > cutoff]
        if bucket:
            self._hits[client_ip] = bucket
        else:
            self._hits.pop(client_ip, None)
        return bucket

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not request.url.path.startswith(self._prefix):
            return await call_next(request)

        client_ip = self._client_ip(request)
        now = time.monotonic()
        cutoff = now - self._window
        bucket = self._prune(client_ip, cutoff)

        if len(bucket) >= self._max:
            retry_after = int(bucket[0] - cutoff) + 1
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
                        "detail": {"retry_after": retry_after},
                    }
                },
                headers={"Retry-After": str(retry_after)},
            )

        self._hits[client_ip].append(now)
        return await call_next(request)
