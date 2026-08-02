"""SQLAlchemy implementation of ChangeRequestRepository.

Clan isolation is an explicit ``clan_id`` predicate on every statement here — the
PRIMARY guarantee (``change_requests`` is not yet in the RLS table rollout, ADR-008,
so there is no layer-2 backstop for it; see ADR-037). A change request belongs to
exactly one clan and is invisible, unfetchable and unreviewable from any other.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy import update as sql_update

from app.core.pagination import encode_cursor, paginate_query
from app.domain.change_request.entity import ChangeRequest as ChangeRequestEntity
from app.domain.change_request.person_changes import SUBMITTABLE_PERSON_FIELDS
from app.domain.change_request.repository import (
    ChangeRequestFilters,
    ChangeRequestPage,
    PersonTargetSnapshot,
)
from app.infrastructure.persistence.change_request_mapper import (
    REVIEW_FIELDS,
    to_domain,
    to_orm,
)
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from app.models.change_request import ChangeRequest as ChangeRequestModel
from app.models.clan_membership import ClanMembership
from app.models.person import Person as PersonModel
from app.schemas.change_request import normalize_person_values

_SNAPSHOT_FIELDS = sorted(SUBMITTABLE_PERSON_FIELDS)


class SqlAlchemyChangeRequestRepository:
    """Concrete ChangeRequest repository backed by SQLAlchemy + PostgreSQL."""

    def __init__(self, uow: SqlAlchemyUnitOfWork) -> None:
        # Takes the UoW (not a bare session) so save() can auto-track the aggregate —
        # tracking cannot be forgotten at the seam.
        self._uow = uow
        self._session = uow.session

    async def get_in_clan(
        self, change_request_id: uuid.UUID, clan_id: uuid.UUID
    ) -> ChangeRequestEntity | None:
        result = await self._session.execute(
            select(ChangeRequestModel).where(
                ChangeRequestModel.id == change_request_id,
                ChangeRequestModel.clan_id == clan_id,
            )
        )
        model = result.scalar_one_or_none()
        return to_domain(model) if model else None

    async def list_page_in_clan(
        self,
        clan_id: uuid.UUID,
        filters: ChangeRequestFilters,
        cursor: str | None = None,
        limit: int = 20,
    ) -> ChangeRequestPage:
        query = select(ChangeRequestModel).where(ChangeRequestModel.clan_id == clan_id)
        if filters.status:
            query = query.where(ChangeRequestModel.status == filters.status)
        if filters.requester_id:
            query = query.where(ChangeRequestModel.requester_id == filters.requester_id)

        # paginate_query fetches limit + 1 and orders (created_at, id) ASC — the one
        # clan-facing pagination scheme (ADR-010).
        result = await self._session.execute(
            paginate_query(query, ChangeRequestModel, cursor, limit)
        )
        rows = list(result.scalars().all())
        has_more = len(rows) > limit
        page = rows[:limit]
        next_cursor = encode_cursor(page[-1].created_at, page[-1].id) if has_more and page else None
        return ChangeRequestPage(
            items=[to_domain(m) for m in page],
            cursor=next_cursor,
            has_more=has_more,
        )

    async def save(self, change_request: ChangeRequestEntity) -> None:
        """Insert a new proposal, or write the review columns of an existing one.

        An update deliberately touches only ``REVIEW_FIELDS``: the payload a requester
        submitted is evidence of what they actually proposed, and the merge that
        approval performs is replayed against it, so it must never be rewritten
        underneath a reviewer.
        """
        self._uow.track(change_request)
        existing = await self._session.get(ChangeRequestModel, change_request.id)
        if existing is None:
            self._session.add(to_orm(change_request))
            return

        values = {f: getattr(change_request, f) for f in REVIEW_FIELDS}
        await self._session.execute(
            sql_update(ChangeRequestModel)
            .where(
                ChangeRequestModel.id == change_request.id,
                ChangeRequestModel.clan_id == change_request.clan_id,
            )
            .values(**values)
        )
        await self._session.refresh(existing)  # sync identity map with the core UPDATE

    # ── Target read model ────────────────────────────────────────────────────
    #
    # Values are returned already JSON-normalized so the merge compares like with
    # like: the payload's base_values and the proposal's changes are JSON, and this
    # is the third input to detect_conflicts.

    async def get_person_snapshot(
        self, person_id: uuid.UUID, clan_id: uuid.UUID
    ) -> PersonTargetSnapshot | None:
        snapshots = await self.get_person_snapshots([person_id], clan_id)
        return snapshots.get(person_id)

    async def get_person_snapshots(
        self, person_ids: list[uuid.UUID], clan_id: uuid.UUID
    ) -> dict[uuid.UUID, PersonTargetSnapshot]:
        """One query for a whole page of proposals — never one per row."""
        if not person_ids:
            return {}
        # Soft-deleted persons are INCLUDED (no is_deleted filter): a proposal whose
        # subject was deleted after submission has to be visibly blocked at review
        # time, which needs the row. Clan isolation still holds — membership in the
        # acting clan is the join predicate.
        result = await self._session.execute(
            select(PersonModel)
            .join(ClanMembership, ClanMembership.person_id == PersonModel.id)
            .where(
                PersonModel.id.in_(set(person_ids)),
                ClanMembership.clan_id == clan_id,
            )
        )
        snapshots: dict[uuid.UUID, PersonTargetSnapshot] = {}
        for model in result.scalars().all():
            snapshots[model.id] = PersonTargetSnapshot(
                person_id=model.id,
                version=model.version,
                is_deleted=model.is_deleted,
                values=normalize_person_values(
                    {f: getattr(model, f) for f in _SNAPSHOT_FIELDS}, _SNAPSHOT_FIELDS
                ),
            )
        return snapshots
