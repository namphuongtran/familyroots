"""Repository port for the ChangeRequest bounded context.

The SQLAlchemy implementation lives in
``app.infrastructure.persistence.change_request_repository``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.domain.change_request.entity import ChangeRequest


@dataclass(frozen=True)
class PersonTargetSnapshot:
    """What a reviewer needs to know about a proposal's target person, right now.

    Read-model only: it carries the target's current OCC ``version``, its
    soft-delete state, and its current value for each submittable field, so the
    review surface can show "this record moved, and here is exactly which of the
    proposed fields moved with it" without a second round-trip per request.
    """

    person_id: uuid.UUID
    version: int
    is_deleted: bool
    values: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChangeRequestPage:
    """One cursor page of the queue: the rows plus the opaque next-page token."""

    items: list[ChangeRequest]
    cursor: str | None
    has_more: bool


@dataclass(frozen=True)
class ChangeRequestFilters:
    """Filter criteria for the clan's change-request queue."""

    status: str | None = None
    # Set by the application layer for a viewer, who may only see their own
    # proposals — never a client-supplied filter.
    requester_id: uuid.UUID | None = None


class ChangeRequestRepository(Protocol):
    """Abstract persistence contract for ChangeRequest aggregates."""

    async def get_in_clan(
        self, change_request_id: uuid.UUID, clan_id: uuid.UUID
    ) -> ChangeRequest | None:
        """Fetch a change request only if it belongs to the given clan."""
        ...

    async def list_page_in_clan(
        self,
        clan_id: uuid.UUID,
        filters: ChangeRequestFilters,
        cursor: str | None = None,
        limit: int = 20,
    ) -> ChangeRequestPage:
        """One page of a clan's queue, ``(created_at, id)`` ASC (ADR-010).

        The adapter owns cursor encoding/decoding so the application layer needs no
        pagination helper import (the import-linter ratchet must not grow).
        """
        ...

    async def save(self, change_request: ChangeRequest) -> None:
        """Insert or update the aggregate (tracked on the UoW for event dispatch)."""
        ...

    async def get_person_snapshot(
        self, person_id: uuid.UUID, clan_id: uuid.UUID
    ) -> PersonTargetSnapshot | None:
        """Snapshot a target person, INCLUDING soft-deleted ones.

        Soft-deleted targets are included deliberately: a proposal whose subject was
        deleted after submission must be visibly blocked at review time, not
        silently reported as "person not found".
        """
        ...

    async def get_person_snapshots(
        self, person_ids: list[uuid.UUID], clan_id: uuid.UUID
    ) -> dict[uuid.UUID, PersonTargetSnapshot]:
        """Batch form of ``get_person_snapshot`` — one query for a whole page."""
        ...
