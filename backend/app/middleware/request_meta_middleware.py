"""Request-meta middleware — captures client IP + User-Agent for audit enrichment.

Populates the ``request_meta`` ContextVar (app/core/request_meta.py) for the
duration of the request so ``AuditLogHandler`` can attach transport metadata to
audit rows without domain events carrying transport-specific data.
"""

import ipaddress
from typing import Any

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.core.request_meta import (
    RequestMeta,
    reset_request_meta,
    resolve_client_ip,
    set_request_meta,
)

_MAX_USER_AGENT_LEN = 500


def _validated_ip(ip: str | None) -> str | None:
    """Reject anything that isn't a real IP literal before it reaches the audit
    row's INET column — e.g. starlette TestClient's placeholder host
    ("testclient") or a malformed/non-IP X-Forwarded-For value. Postgres would
    otherwise raise on INSERT and abort the whole write transaction (the audit
    handler's failure re-raises through the event dispatcher)."""
    if ip is None:
        return None
    try:
        ipaddress.ip_address(ip)
    except ValueError:
        return None
    return ip


class RequestMetaMiddleware(BaseHTTPMiddleware):
    """Extract client IP (proxy-aware) and User-Agent into a request-scoped ContextVar.

    ``trust_forwarded_for`` is captured at construction time (from
    ``settings.RATE_LIMIT_TRUST_FORWARDED_FOR`` when registered in ``main.py``),
    mirroring ``RateLimitMiddleware``'s constructor parameter — this keeps the
    XFF-trust decision fixed per app instance rather than re-read from a mutable
    global on every request.
    """

    def __init__(self, app: Any, *, trust_forwarded_for: bool = False) -> None:
        super().__init__(app)
        self._trust_xff = trust_forwarded_for

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        ip = _validated_ip(
            resolve_client_ip(
                request.headers.get,
                request.client.host if request.client else None,
                self._trust_xff,
            )
        )
        user_agent = request.headers.get("user-agent") or None
        if user_agent is not None:
            user_agent = user_agent[:_MAX_USER_AGENT_LEN]
        token = set_request_meta(RequestMeta(ip=ip, user_agent=user_agent))
        try:
            return await call_next(request)
        finally:
            reset_request_meta(token)
