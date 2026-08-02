"""Trace-context middleware — one correlation id per request, shared with clients.

Registered outside LanguageMiddleware (and therefore outside RequestMeta, Sentry
and RateLimit) so that every log line produced while handling a request carries
the trace id — including the localized 429 the rate limiter builds.
"""

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.trace_context import (
    new_trace_context,
    reset_trace_context,
    set_trace_context,
)


class TraceContextMiddleware(BaseHTTPMiddleware):
    """Continue the caller's W3C trace or start a new one; echo it on the response."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        ctx = new_trace_context(
            request.headers.get("traceparent"),
            route=request.url.path,
            clan_id=request.headers.get("X-Current-Clan-Id"),
        )
        token = set_trace_context(ctx)
        try:
            response = await call_next(request)
            response.headers["traceparent"] = ctx.to_traceparent()
            return response
        finally:
            reset_trace_context(token)
