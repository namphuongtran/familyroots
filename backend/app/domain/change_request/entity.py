"""ChangeRequest domain entity — pure Python, no framework dependencies.

A ChangeRequest is a *proposal* to modify clan data, made by a member who may not be
allowed to make the edit themselves (in practice a viewer reading the gia phả who
spots a wrong date). A reviewer approves it — which applies it through the ordinary
domain write path — or rejects it.

Scope of this build (ADR-037): ``action="update"`` on ``resource_type="person"``
only. The persisted column set already covers create/delete and the other resource
types, so they can be added later without a schema or contract change; every guard
below is written as a check against the *supported* set rather than an assumption
that person-update is the only shape.

Staleness: the proposal records the target's ``version`` AND the target's value for
each proposed field at submission time (``base_version`` / ``base_values``). The
approval path replays a three-way merge against those — see
``app.domain.change_request.person_changes.detect_conflicts`` and ADR-037.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.domain.change_request.events import (
    ChangeRequestApproved,
    ChangeRequestRejected,
    ChangeRequestSubmitted,
)
from app.domain.change_request.person_changes import (
    SUBMITTABLE_PERSON_FIELDS,
    FieldConflict,
    detect_conflicts,
)
from app.domain.shared.entity import AggregateRoot
from app.domain.shared.exceptions import BusinessRuleViolation, ConflictError
from app.domain.shared.value_objects import ActorInfo

ACTION_UPDATE = "update"
RESOURCE_PERSON = "person"

STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"

# What this build actually executes. The DB CHECK constraints are wider on purpose
# (they already permit create/delete and marriage/parent_child/event/document) so
# widening this tuple is the only change a later build needs.
SUPPORTED_OPERATIONS: tuple[tuple[str, str], ...] = ((ACTION_UPDATE, RESOURCE_PERSON),)


@dataclass
class ChangeRequest(AggregateRoot):
    """Aggregate root for a proposed change to a clan resource."""

    clan_id: uuid.UUID = field(default_factory=uuid.uuid4)
    requester_id: uuid.UUID = field(default_factory=uuid.uuid4)

    action: str = ACTION_UPDATE
    resource_type: str = RESOURCE_PERSON
    resource_id: uuid.UUID | None = None

    # ── Proposal body (persisted inside the `payload` JSONB column) ───────────
    # All three are JSON-normalized (dates are ISO strings) so the merge below can
    # compare them without re-deriving types.
    changes: dict[str, Any] = field(default_factory=dict)
    base_values: dict[str, Any] = field(default_factory=dict)
    base_version: int = 1
    note: str | None = None

    # ── Review state ──────────────────────────────────────────────────────────
    status: str = STATUS_PENDING
    reviewed_by: uuid.UUID | None = None
    reviewed_at: datetime | None = None
    review_notes: str | None = None

    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    # ── Factory ───────────────────────────────────────────────────────────────

    @classmethod
    def submit_person_update(
        cls,
        *,
        clan_id: uuid.UUID,
        requester: ActorInfo,
        person_id: uuid.UUID,
        changes: dict[str, Any],
        base_values: dict[str, Any],
        base_version: int,
        note: str | None = None,
    ) -> ChangeRequest:
        """Create a pending person-update proposal and emit the submission event."""
        validate_supported(ACTION_UPDATE, RESOURCE_PERSON)
        validate_person_fields(changes)

        request = cls(
            clan_id=clan_id,
            requester_id=requester.user_id,
            action=ACTION_UPDATE,
            resource_type=RESOURCE_PERSON,
            resource_id=person_id,
            changes=dict(changes),
            # Only the proposed fields are snapshotted: a full row copy would be a
            # second, staler mirror of the person record and would put contact PII
            # into the payload for no benefit.
            base_values={f: base_values.get(f) for f in changes},
            base_version=base_version,
            note=note,
        )
        request.add_event(
            ChangeRequestSubmitted(
                clan_id=clan_id,
                actor_id=requester.user_id,
                actor_role=requester.role,
                change_request_id=request.id,
                target_resource_type=RESOURCE_PERSON,
                target_resource_id=person_id,
                fields=tuple(sorted(changes)),
            )
        )
        return request

    # ── Review transitions ────────────────────────────────────────────────────

    def conflicts_against(self, current_values: dict[str, Any]) -> list[FieldConflict]:
        """Proposed fields that can no longer be applied without losing an edit."""
        return detect_conflicts(self.changes, self.base_values, current_values)

    def approve(
        self,
        reviewer: ActorInfo,
        *,
        applied_version: int | None = None,
        review_notes: str | None = None,
    ) -> None:
        """Mark the proposal approved. The caller has ALREADY applied it.

        ``applied_version`` is the target's version after the write, recorded so the
        audit trail shows what the proposal actually landed on rather than what it
        was written against.
        """
        self._require_pending()
        self.status = STATUS_APPROVED
        self.reviewed_by = reviewer.user_id
        self.reviewed_at = datetime.now(UTC)
        self.review_notes = review_notes
        self.add_event(
            ChangeRequestApproved(
                clan_id=self.clan_id,
                actor_id=reviewer.user_id,
                actor_role=reviewer.role,
                change_request_id=self.id,
                target_resource_type=self.resource_type,
                target_resource_id=self.resource_id,
                changes=dict(self.changes),
                base_version=self.base_version,
                applied_version=applied_version,
            )
        )

    def reject(self, reviewer: ActorInfo, *, review_notes: str | None = None) -> None:
        """Mark the proposal rejected. Nothing is written to the target."""
        self._require_pending()
        self.status = STATUS_REJECTED
        self.reviewed_by = reviewer.user_id
        self.reviewed_at = datetime.now(UTC)
        self.review_notes = review_notes
        self.add_event(
            ChangeRequestRejected(
                clan_id=self.clan_id,
                actor_id=reviewer.user_id,
                actor_role=reviewer.role,
                change_request_id=self.id,
                target_resource_type=self.resource_type,
                target_resource_id=self.resource_id,
                review_notes=review_notes,
            )
        )

    def _require_pending(self) -> None:
        if self.status != STATUS_PENDING:
            raise ConflictError("change_request.not_pending", detail={"status": self.status})


# ── Standalone guards (used by the factory and re-checked at review time) ─────


def validate_supported(action: str, resource_type: str) -> None:
    """Reject an operation this build does not execute.

    Re-checked on the review path, not just at submit: a row written by an earlier
    or later build (or straight into the DB) must not be silently half-applied.
    """
    if (action, resource_type) not in SUPPORTED_OPERATIONS:
        raise BusinessRuleViolation(
            "change_request.unsupported_operation",
            detail={
                "action": action,
                "resource_type": resource_type,
                "supported": [{"action": a, "resource_type": r} for a, r in SUPPORTED_OPERATIONS],
            },
        )


def validate_person_fields(changes: dict[str, Any]) -> None:
    """Reject an empty proposal or one touching a non-submittable person field."""
    if not changes:
        raise BusinessRuleViolation("change_request.no_changes")
    rejected = sorted(set(changes) - SUBMITTABLE_PERSON_FIELDS)
    if rejected:
        raise BusinessRuleViolation(
            "change_request.field_not_submittable",
            detail={"fields": rejected, "allowed": sorted(SUBMITTABLE_PERSON_FIELDS)},
        )
