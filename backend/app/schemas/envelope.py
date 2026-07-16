"""Generic response envelopes — OpenAPI documentation models.

Every 2xx body on this API is ``{"data": ...}`` (lists add ``"meta"``), and
every error is ``{"error": {code, message, detail}}`` — docs/contracts/ is
the spec. These models exist so the generated OpenAPI carries those shapes
for client codegen (openapi-typescript, Dio/Retrofit).

They are declared via each route's ``responses=`` parameter —
**documentation-only**, never ``response_model=``: runtime re-validation
would break the sparse ``fields=``/``include=`` responses (subset payloads
by design) and the profile projections. Routes keep building their bodies
exactly as before; when a route supports sparse fields, the documented
schema describes the FULL shape and clients treat filtered responses as
subsets of it.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Envelope[T](BaseModel):
    """The canonical success envelope: every 2xx body is {"data": ...}."""

    data: T


class ListMeta(BaseModel):
    """Cursor-pagination meta carried by every list endpoint."""

    cursor: str | None = None
    has_more: bool = False
    limit: int = 20


class PageEnvelope[T](BaseModel):
    """A cursor-paginated list: {"data": [...], "meta": {cursor, has_more, limit}}."""

    data: list[T]
    meta: ListMeta


class MessageData(BaseModel):
    """Delete/action acknowledgements: {"data": {"message": ..., "id": ...}}."""

    message: str
    id: str | None = None


class ErrorDetail(BaseModel):
    code: str
    message: str
    detail: dict[str, Any] = Field(default_factory=dict)


class ErrorEnvelope(BaseModel):
    """The stable error envelope every non-2xx response uses."""

    error: ErrorDetail


# Router-level defaults: merged into every operation's OpenAPI when passed to
# include_router(..., responses=DEFAULT_ERROR_RESPONSES). Documentation-only.
DEFAULT_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorEnvelope, "description": "Missing/invalid token"},
    403: {"model": ErrorEnvelope, "description": "Insufficient role / clan mismatch"},
    404: {"model": ErrorEnvelope, "description": "Not found (incl. cross-clan reads)"},
    409: {"model": ErrorEnvelope, "description": "Conflict (stale_write, duplicates)"},
    422: {"model": ErrorEnvelope, "description": "Validation error"},
}


def ok(model: Any) -> dict[int | str, dict[str, Any]]:
    """responses= entry documenting a 200 {"data": <model>} envelope."""
    return {200: {"model": Envelope[model]}}


def created(model: Any) -> dict[int | str, dict[str, Any]]:
    """responses= entry documenting a 201 {"data": <model>} envelope."""
    return {201: {"model": Envelope[model]}}


def page(model: Any) -> dict[int | str, dict[str, Any]]:
    """responses= entry documenting a 200 cursor-paginated list envelope."""
    return {200: {"model": PageEnvelope[model]}}


def ok_list(model: Any) -> dict[int | str, dict[str, Any]]:
    """responses= entry for a plain (non-paginated) array under data."""
    return {200: {"model": Envelope[list[model]]}}


def ok_message() -> dict[int | str, dict[str, Any]]:
    """responses= entry for delete/action message envelopes."""
    return {200: {"model": Envelope[MessageData]}}
