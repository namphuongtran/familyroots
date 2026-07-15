"""Request-scoped transport metadata for audit enrichment (spec 2026-07-14).

Domain events stay transport-free; AuditLogHandler enriches at write time from
this ContextVar. Outside a request (scheduler/purge jobs) it is None -> NULL
columns, which is the correct semantics for system-initiated changes.
"""

from __future__ import annotations

from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True)
class RequestMeta:
    ip: str | None
    user_agent: str | None


_request_meta: ContextVar[RequestMeta | None] = ContextVar("request_meta", default=None)


def set_request_meta(meta: RequestMeta) -> object:
    return _request_meta.set(meta)


def get_request_meta() -> RequestMeta | None:
    return _request_meta.get()


def reset_request_meta(token: object) -> None:
    _request_meta.reset(token)  # type: ignore[arg-type]


def resolve_client_ip(
    headers_get: Callable[[str], str | None], client_host: str | None, trust_xff: bool
) -> str | None:
    """Rightmost-XFF rule shared with the rate limiter: only the entry appended
    by our single trusted proxy is trustworthy; leftmost entries are spoofable."""
    if trust_xff:
        xff = headers_get("x-forwarded-for")
        if xff:
            return xff.split(",")[-1].strip()
    return client_host
