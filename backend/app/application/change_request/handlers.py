"""Change-request use-case handlers (ADR-037).

The approval path is the interesting one. It does NOT open a second write path into
persons: it loads the same ``Person`` aggregate, calls the same ``Person.update()``
(so the same field whitelist and the same death-before-birth invariant apply), and
saves through the same ``PersonRepository.save(expected_version=...)`` conditional
UPDATE that ``PATCH /persons/{id}`` uses (ADR-017). The only difference is
composition: the person write and the change-request status write share ONE Unit of
Work, so they commit together with both aggregates' domain events — approving and
applying can never come apart.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.application.change_request.commands import (
    GetChangeRequest,
    ListChangeRequests,
    ReviewChangeRequest,
    SubmitChangeRequest,
)
from app.domain.change_request.entity import (
    STATUS_PENDING,
    ChangeRequest,
    validate_person_fields,
    validate_supported,
)
from app.domain.change_request.repository import (
    ChangeRequestFilters,
    ChangeRequestRepository,
    PersonTargetSnapshot,
)
from app.domain.person.repository import PersonRepository
from app.domain.shared.exceptions import (
    ConflictError,
    EntityNotFoundError,
    ValidationError,
)
from app.domain.shared.unit_of_work import UnitOfWork
from app.schemas.change_request import (
    ChangeRequestConflict,
    ChangeRequestResponse,
    ChangeRequestTarget,
    normalize_person_values,
    to_person_changes,
)

_VIEWER_ROLE = "viewer"


def _to_response(
    change_request: ChangeRequest, snapshot: PersonTargetSnapshot | None
) -> ChangeRequestResponse:
    """Serialize a proposal plus the live state of what it points at.

    Conflicts are only meaningful while the proposal is still actionable; on a
    reviewed one they would be noise about an outcome nobody can change.
    """
    conflicts: list[ChangeRequestConflict] = []
    if snapshot is not None and change_request.status == STATUS_PENDING:
        conflicts = [
            ChangeRequestConflict(**conflict.as_dict())
            for conflict in change_request.conflicts_against(snapshot.values)
        ]
    return ChangeRequestResponse(
        id=change_request.id,
        clan_id=change_request.clan_id,
        requester_id=change_request.requester_id,
        action=change_request.action,
        resource_type=change_request.resource_type,
        resource_id=change_request.resource_id,
        changes=change_request.changes,
        note=change_request.note,
        status=change_request.status,
        reviewed_by=change_request.reviewed_by,
        reviewed_at=change_request.reviewed_at,
        review_notes=change_request.review_notes,
        created_at=change_request.created_at,
        target=ChangeRequestTarget(
            resource_type=change_request.resource_type,
            resource_id=change_request.resource_id,
            exists=snapshot is not None,
            is_deleted=snapshot.is_deleted if snapshot else False,
            base_version=change_request.base_version,
            current_version=snapshot.version if snapshot else None,
            is_stale=snapshot is not None and snapshot.version != change_request.base_version,
            conflicts=conflicts,
        ),
    )


def _require_target_id(change_request_resource_id: uuid.UUID | None) -> uuid.UUID:
    """An update proposal without a target is malformed, not a missing person."""
    if change_request_resource_id is None:
        raise ValidationError("validation_error", detail={"fields": ["resource_id"]})
    return change_request_resource_id


class ChangeRequestCommandHandler:
    """Handles change-request writes: submit, approve, reject."""

    def __init__(
        self,
        repo: ChangeRequestRepository,
        person_repo: PersonRepository,
        uow: UnitOfWork,
    ) -> None:
        self._repo = repo
        self._person_repo = person_repo
        self._uow = uow

    async def submit(self, cmd: SubmitChangeRequest) -> ChangeRequestResponse:
        """Record a proposal against the target's CURRENT state.

        Both halves of the staleness baseline are captured here: ``base_version``
        (did the row move at all?) and ``base_values`` for exactly the proposed
        fields (did *these* facts move?). Without the second half, approval could
        only ever be all-or-nothing on the row version.
        """
        validate_supported(cmd.action, cmd.resource_type)
        person_id = _require_target_id(cmd.resource_id)
        # Field whitelist first: Pydantic ignores unknown keys, so validating the
        # change set before this check would silently DROP a misspelled field and
        # store a proposal the requester never made.
        validate_person_fields(cmd.changes)
        changes = normalize_person_values(cmd.changes, cmd.changes.keys())

        snapshot = await self._repo.get_person_snapshot(person_id, cmd.clan_id)
        if snapshot is None or snapshot.is_deleted:
            # Same 404 the person read paths give: a proposal cannot be raised
            # against a record the requester is not allowed to see.
            raise EntityNotFoundError("person_not_found", {"person_id": str(person_id)})

        change_request = ChangeRequest.submit_person_update(
            clan_id=cmd.clan_id,
            requester=cmd.actor,
            person_id=person_id,
            changes=changes,
            base_values=snapshot.values,
            base_version=snapshot.version,
            note=cmd.note,
        )
        await self._repo.save(change_request)
        await self._uow.commit()
        return _to_response(change_request, snapshot)

    async def approve(self, cmd: ReviewChangeRequest) -> ChangeRequestResponse:
        """Apply the proposal and mark it approved, atomically.

        Refuses — rather than half-applying — when the target moved in a way that
        matters. "Approved" therefore always means the target now holds the proposed
        values; there is no path where a reviewer is told the change landed and it
        did not.
        """
        change_request = await self._load_pending(cmd)
        person_id = _require_target_id(change_request.resource_id)

        person = await self._person_repo.get_in_clan(person_id, cmd.clan_id, include_deleted=True)
        if person is None:
            raise EntityNotFoundError("person_not_found", {"person_id": str(person_id)})
        if person.is_deleted:
            # The subject is gone from the gia phả. Editing a deleted record and
            # reporting "approved" would be a lie about a visible outcome; the
            # reviewer restores first, or rejects.
            raise ConflictError(
                "change_request.target_deleted", detail={"person_id": str(person_id)}
            )

        fields = list(change_request.changes)
        current_values = normalize_person_values(
            {name: getattr(person, name, None) for name in fields}, fields
        )
        conflicts = change_request.conflicts_against(current_values)
        if conflicts:
            raise ConflictError(
                "change_request.target_conflict",
                detail={
                    "conflicts": [conflict.as_dict() for conflict in conflicts],
                    "base_version": change_request.base_version,
                    "current_version": person.version,
                },
            )

        # From here the merge is safe: every proposed field either still holds the
        # value the requester saw, or already holds the value they proposed.
        expected_version = person.version
        person.update(to_person_changes(change_request.changes), cmd.actor, cmd.clan_id)
        # Conditional UPDATE on the freshly-read version (ADR-017), NOT on
        # base_version: the merge already decided the old proposal is applicable, and
        # this predicate closes the remaining window against a writer that commits
        # between the read above and this write — that one still gets stale_write.
        await self._person_repo.save(person, expected_version=expected_version)

        change_request.approve(
            cmd.actor,
            applied_version=person.version,
            review_notes=cmd.review_notes,
        )
        await self._repo.save(change_request)
        await self._uow.commit()

        return _to_response(
            change_request,
            PersonTargetSnapshot(
                person_id=person.id,
                version=person.version,
                is_deleted=person.is_deleted,
                values=normalize_person_values(
                    {name: getattr(person, name, None) for name in fields}, fields
                ),
            ),
        )

    async def reject(self, cmd: ReviewChangeRequest) -> ChangeRequestResponse:
        """Decline the proposal. Nothing is written to the target.

        Deliberately has no target-state preconditions: a proposal against a deleted
        or heavily-edited record is exactly the kind a reviewer needs to be able to
        clear out of the queue.
        """
        change_request = await self._load_pending(cmd)
        change_request.reject(cmd.actor, review_notes=cmd.review_notes)
        await self._repo.save(change_request)
        await self._uow.commit()

        snapshot = None
        if change_request.resource_id is not None:
            snapshot = await self._repo.get_person_snapshot(change_request.resource_id, cmd.clan_id)
        return _to_response(change_request, snapshot)

    async def _load_pending(self, cmd: ReviewChangeRequest) -> ChangeRequest:
        change_request = await self._repo.get_in_clan(cmd.change_request_id, cmd.clan_id)
        if change_request is None:
            raise EntityNotFoundError("change_request_not_found")
        # Re-checked at review time, not trusted from submit: a row written by a
        # different build must not be half-executed by this one.
        validate_supported(change_request.action, change_request.resource_type)
        # Before any target write — an already-reviewed proposal must not cause a
        # person edit on its way to discovering it is not pending.
        change_request.ensure_pending()
        return change_request


class ChangeRequestQueryHandler:
    """Read-only handler for the change-request queue."""

    def __init__(self, repo: ChangeRequestRepository) -> None:
        self._repo = repo

    async def get(self, query: GetChangeRequest) -> ChangeRequestResponse:
        change_request = await self._repo.get_in_clan(query.change_request_id, query.clan_id)
        if change_request is None or not _may_read(
            query.viewer_role, query.viewer_user_id, change_request
        ):
            # A viewer asking for someone else's proposal gets the same 404 as one
            # that does not exist — the queue is not an enumeration oracle (ADR-021).
            raise EntityNotFoundError("change_request_not_found")

        snapshot = None
        if change_request.resource_id is not None:
            snapshot = await self._repo.get_person_snapshot(
                change_request.resource_id, query.clan_id
            )
        return _to_response(change_request, snapshot)

    async def list(
        self, query: ListChangeRequests
    ) -> tuple[list[ChangeRequestResponse], dict[str, Any]]:
        """The clan queue for a reviewer; only their own proposals for a viewer."""
        filters = ChangeRequestFilters(
            status=query.status,
            requester_id=query.viewer_user_id if query.viewer_role == _VIEWER_ROLE else None,
        )
        page = await self._repo.list_page_in_clan(query.clan_id, filters, query.cursor, query.limit)

        # One batched snapshot query for the whole page — never one per row.
        person_ids = [cr.resource_id for cr in page.items if cr.resource_id is not None]
        snapshots = await self._repo.get_person_snapshots(person_ids, query.clan_id)

        data = [
            _to_response(cr, snapshots.get(cr.resource_id) if cr.resource_id else None)
            for cr in page.items
        ]
        meta = {"cursor": page.cursor, "has_more": page.has_more, "limit": query.limit}
        return data, meta


def _may_read(viewer_role: str, viewer_user_id: uuid.UUID, change_request: ChangeRequest) -> bool:
    """Viewers see only what they proposed; editors and admins see the clan queue."""
    if viewer_role != _VIEWER_ROLE:
        return True
    return change_request.requester_id == viewer_user_id
