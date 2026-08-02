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

# X-Current-Clan-Id is attacker-controlled and unbounded, and lands verbatim in every
# log line of the request. Nothing authorizes off it (clan scoping is enforced in the
# repository layer), but an unbounded value multiplied across a request's log lines is
# a cheap log-volume amplifier. Long enough for a UUID with room to spare.
_MAX_CLAN_ID_LOG_CHARS = 64


class TraceContextMiddleware(BaseHTTPMiddleware):
    """Continue the caller's W3C trace or start a new one; echo it on the response."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        claimed_clan_id = request.headers.get("X-Current-Clan-Id")
        ctx = new_trace_context(
            request.headers.get("traceparent"),
            # Raw path, not a route template: /persons/<uuid> stays distinct per person.
            route=request.url.path,
            clan_id=(
                claimed_clan_id[:_MAX_CLAN_ID_LOG_CHARS] if claimed_clan_id is not None else None
            ),
        )
        token = set_trace_context(ctx)
        # Also stash it on the request scope. Starlette hoists the catch-all
        # `Exception` handler into ServerErrorMiddleware, which runs OUTSIDE every
        # user middleware — i.e. after the `finally` below has already reset the
        # ContextVar. `HTTPConnection.state` writes into `scope["state"]`, which that
        # handler still holds, so an unhandled 500 stays correlatable.
        request.state.trace_context = ctx
        try:
            response = await call_next(request)
            response.headers["traceparent"] = ctx.to_traceparent()
            return response
        finally:
            reset_trace_context(token)
