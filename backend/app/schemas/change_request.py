"""Pydantic v2 schemas for ChangeRequest requests and responses.

Wire shape note (`docs/contracts/rest-change-requests-api.md`): ``changes`` is a
*proposed request body*, not a rendered record, so its date fields keep the WRITE
shape used by ``PATCH /persons/{id}`` — scalar ``birth_date`` plus
``birth_date_precision`` / ``birth_date_display`` — and are NOT wrapped in the
``HistoricalDate`` response object. Wrapping them would mean a client could not feed
``changes`` back into the persons write endpoint, which is exactly what a reviewer's
"apply manually" fallback needs.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ChangeRequestCreateRequest(BaseModel):
    """Request body for proposing a change.

    ``action``/``resource_type`` are accepted (and constrained to the persisted
    CHECK-constraint vocabulary) rather than implied, so adding marriage/event/
    document proposals later needs no request-shape change. Anything outside the
    combination this build executes is rejected with
    ``change_request.unsupported_operation`` (422) by the domain, not by this schema
    — one code, one place, whatever the caller sends.
    """

    action: str = Field("update", pattern="^(create|update|delete)$")
    resource_type: str = Field(
        "person",
        pattern="^(person|marriage|parent_child|event|document)$",
    )
    resource_id: uuid.UUID | None = None
    changes: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Proposed field values, same field names and value shapes as the "
            "PATCH /persons/{id} body (minus expected_version)."
        ),
    )
    note: str | None = Field(
        None,
        max_length=2000,
        description="Optional free-text explanation from the requester.",
    )


class ChangeRequestReviewRequest(BaseModel):
    """Request body for approving or rejecting a change request."""

    review_notes: str | None = Field(None, max_length=2000)


class ChangeRequestConflict(BaseModel):
    """One proposed field whose target value moved to something else since submission."""

    field: str
    base: Any = None
    current: Any = None
    proposed: Any = None


class ChangeRequestTarget(BaseModel):
    """Live state of the resource a proposal points at (ADR-037).

    Present so a reviewer is never asked to approve blind: ``is_stale`` says the
    record moved at all, and ``conflicts`` says whether any of *these* fields moved
    — the only kind of movement that blocks approval.
    """

    resource_type: str
    resource_id: uuid.UUID | None = None
    exists: bool = False
    is_deleted: bool = False
    base_version: int = 1
    current_version: int | None = None
    is_stale: bool = False
    conflicts: list[ChangeRequestConflict] = Field(default_factory=list)


class ChangeRequestResponse(BaseModel):
    """Response schema for a change request."""

    id: uuid.UUID
    clan_id: uuid.UUID
    requester_id: uuid.UUID
    action: str
    resource_type: str
    resource_id: uuid.UUID | None = None
    changes: dict[str, Any] = Field(default_factory=dict)
    note: str | None = None
    status: str
    reviewed_by: uuid.UUID | None = None
    reviewed_at: datetime | None = None
    review_notes: str | None = None
    created_at: datetime
    target: ChangeRequestTarget
