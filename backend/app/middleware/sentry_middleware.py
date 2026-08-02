"""Sentry middleware — capture exceptions and performance data."""

import sentry_sdk
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.trace_context import get_trace_context

__all__ = ["SentryMiddleware", "sentry_sdk"]


class SentryMiddleware(BaseHTTPMiddleware):
    """Attach request context to Sentry scope for richer error reports."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        with sentry_sdk.push_scope() as scope:
            scope.set_tag("path", request.url.path)
            scope.set_tag("method", request.method)

            # Pivot from a Sentry issue to the JSON log lines for the same request.
            # Populated by TraceContextMiddleware, which is registered outside this one.
            trace = get_trace_context()
            if trace is not None:
                scope.set_tag("trace_id", trace.trace_id)

            clan_id = request.headers.get("X-Current-Clan-Id")
            if clan_id:
                scope.set_tag("clan_id", clan_id)

            # Extract user ID from Authorization if available
            auth = request.headers.get("Authorization", "")
            if auth.startswith("Bearer "):
                scope.set_tag("has_auth", "true")

            try:
                response = await call_next(request)
                return response
            except Exception as exc:
                sentry_sdk.capture_exception(exc)
                raise
