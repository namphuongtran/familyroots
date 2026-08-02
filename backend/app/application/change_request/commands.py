"""Command and query DTOs for the change-request bounded context."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from app.domain.shared.value_objects import ActorInfo


@dataclass(frozen=True)
class SubmitChangeRequest:
    """Propose a change. ``action``/``resource_type`` are carried, not assumed, so the
    unsupported-operation guard sees what the caller actually asked for."""

    clan_id: uuid.UUID
    actor: ActorInfo
    action: str
    resource_type: str
    resource_id: uuid.UUID | None
    changes: dict[str, Any] = field(default_factory=dict)
    note: str | None = None


@dataclass(frozen=True)
class ReviewChangeRequest:
    """Approve or reject one proposal. The reviewer is the actor of the resulting
    write — they authorize it, so the person-update audit row is theirs."""

    change_request_id: uuid.UUID
    clan_id: uuid.UUID
    actor: ActorInfo
    review_notes: str | None = None


@dataclass(frozen=True)
class GetChangeRequest:
    """Fetch one proposal. ``viewer_*`` drive the own-proposals-only rule for viewers."""

    change_request_id: uuid.UUID
    clan_id: uuid.UUID
    viewer_user_id: uuid.UUID
    viewer_role: str


@dataclass(frozen=True)
class ListChangeRequests:
    """Page the clan queue (reviewers) or the caller's own proposals (viewers)."""

    clan_id: uuid.UUID
    viewer_user_id: uuid.UUID
    viewer_role: str
    status: str | None = None
    cursor: str | None = None
    limit: int = 20
