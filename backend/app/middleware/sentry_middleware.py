"""Sentry middleware — capture exceptions and performance data."""

import sentry_sdk
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class SentryMiddleware(BaseHTTPMiddleware):
    """Attach request context to Sentry scope for richer error reports."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        with sentry_sdk.push_scope() as scope:
            scope.set_tag("path", request.url.path)
            scope.set_tag("method", request.method)

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
