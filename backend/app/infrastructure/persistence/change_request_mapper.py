"""Mapping between the ChangeRequest aggregate and its ORM row.

The proposal body (``changes`` / ``base_values`` / ``base_version`` / ``note``) lives
inside the existing ``payload`` JSONB column rather than in new columns. That is a
deliberate consequence of adopting the dormant table as-is (ADR-037): the column set
predates this feature, is already shaped for every resource type, and needs no
migration. The keys below are therefore a **storage contract** — read defensively so
a row written by an earlier build (or by hand) degrades to an empty proposal instead
of raising on load.
"""

from __future__ import annotations

from typing import Any

from app.domain.change_request.entity import ChangeRequest
from app.models.change_request import ChangeRequest as ChangeRequestModel

# Columns a review may write. Everything else about a proposal is immutable once
# submitted — the requester's payload is evidence, not a working draft.
REVIEW_FIELDS = ("status", "reviewed_by", "reviewed_at", "review_notes")


def build_payload(change_request: ChangeRequest) -> dict[str, Any]:
    """Pack the proposal body into the JSONB column."""
    return {
        "changes": change_request.changes,
        "base_values": change_request.base_values,
        "base_version": change_request.base_version,
        "note": change_request.note,
    }


def to_domain(model: ChangeRequestModel) -> ChangeRequest:
    payload: dict[str, Any] = model.payload if isinstance(model.payload, dict) else {}
    changes = payload.get("changes")
    base_values = payload.get("base_values")
    base_version = payload.get("base_version")
    return ChangeRequest(
        id=model.id,
        clan_id=model.clan_id,
        requester_id=model.requester_id,
        action=model.action,
        resource_type=model.resource_type,
        resource_id=model.resource_id,
        changes=dict(changes) if isinstance(changes, dict) else {},
        base_values=dict(base_values) if isinstance(base_values, dict) else {},
        base_version=base_version if isinstance(base_version, int) else 1,
        note=payload.get("note"),
        status=model.status,
        reviewed_by=model.reviewed_by,
        reviewed_at=model.reviewed_at,
        review_notes=model.review_notes,
        created_at=model.created_at,
    )


def to_orm(change_request: ChangeRequest) -> ChangeRequestModel:
    return ChangeRequestModel(
        id=change_request.id,
        clan_id=change_request.clan_id,
        requester_id=change_request.requester_id,
        action=change_request.action,
        resource_type=change_request.resource_type,
        resource_id=change_request.resource_id,
        payload=build_payload(change_request),
        status=change_request.status,
        reviewed_by=change_request.reviewed_by,
        reviewed_at=change_request.reviewed_at,
        review_notes=change_request.review_notes,
        # Set explicitly rather than left to the server default: the list endpoint
        # keysets on (created_at, id), so the value the entity was ordered by in
        # memory must be the value stored.
        created_at=change_request.created_at,
    )
