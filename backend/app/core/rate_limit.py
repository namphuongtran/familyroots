"""In-memory rate limiting middleware for auth endpoints.

Uses a sliding-window counter approach with per-IP tracking.
For production at scale, swap the in-memory store for Redis.
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
    """

    def __init__(
        self,
        app: Any,
        *,
        path_prefix: str = "/api/v1/auth",
        max_requests: int = 20,
        window_seconds: int = 60,
    ) -> None:
        super().__init__(app)
        self._prefix = path_prefix
        self._max = max_requests
        self._window = window_seconds
        # {client_ip: [(timestamp, ...),]}
        self._hits: dict[str, list[float]] = defaultdict(list)

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if not request.url.path.startswith(self._prefix):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        cutoff = now - self._window

        # Prune expired entries
        bucket = self._hits[client_ip]
        self._hits[client_ip] = bucket = [t for t in bucket if t > cutoff]

        if len(bucket) >= self._max:
            retry_after = int(bucket[0] - cutoff) + 1
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please try again later."},
                headers={"Retry-After": str(retry_after)},
            )

        bucket.append(now)
        return await call_next(request)
