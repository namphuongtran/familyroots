"""SQLAlchemy implementation of the Person read operations.

Every read has a batch form (single ANY-style query for N persons) and the
single-person methods delegate to it with a one-element list — one SQL
implementation per concern, so /persons/batch stays O(1) queries per include
token instead of O(N) per person.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.domain.person.query_port import PersonQueryPort
from app.models.clan_membership import ClanMembership
from app.models.document import Document
from app.models.event import Event
from app.models.marriage import Marriage
from app.models.parent_child import ParentChild
from app.models.person import Person
from app.schemas.document import DocumentSummary
from app.schemas.event import EventResponse, TimelineEvent
from app.schemas.historical_date import to_historical_date
from app.schemas.marriage import MarriageResponse
from app.schemas.parent_child import ParentChildResponse
from app.services.translator import t


def _empty_map(person_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[dict[str, Any]]]:
    return {pid: [] for pid in person_ids}


class SqlAlchemyPersonQueryPort(PersonQueryPort):
    """SQLAlchemy implementation of PersonQueryPort."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── marriages ────────────────────────────────────────────────────────

    async def get_marriages_batch(
        self, clan_id: uuid.UUID, person_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list[dict[str, Any]]]:
        out = _empty_map(person_ids)
        if not person_ids:
            return out
        result = await self._session.execute(
            select(Marriage).where(
                or_(Marriage.person1_id.in_(person_ids), Marriage.person2_id.in_(person_ids)),
                Marriage.created_by_clan_id == clan_id,
                Marriage.is_deleted.is_(False),
            )
        )
        for m in result.scalars().all():
            dumped = MarriageResponse.model_validate(m).model_dump()
            for pid in (m.person1_id, m.person2_id):
                if pid in out:
                    out[pid].append(dumped)
        return out

    async def get_marriages(self, clan_id: uuid.UUID, person_id: uuid.UUID) -> list[dict[str, Any]]:
        return (await self.get_marriages_batch(clan_id, [person_id]))[person_id]

    # ── parent-child links ───────────────────────────────────────────────

    async def get_parent_child_links_batch(
        self, clan_id: uuid.UUID, person_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list[dict[str, Any]]]:
        out = _empty_map(person_ids)
        if not person_ids:
            return out
        result = await self._session.execute(
            select(ParentChild).where(
                or_(ParentChild.parent_id.in_(person_ids), ParentChild.child_id.in_(person_ids)),
                ParentChild.created_by_clan_id == clan_id,
                ParentChild.is_deleted.is_(False),
            )
        )
        for link in result.scalars().all():
            dumped = ParentChildResponse.model_validate(link).model_dump()
            for pid in (link.parent_id, link.child_id):
                if pid in out:
                    out[pid].append(dumped)
        return out

    async def get_parent_child_links(
        self, clan_id: uuid.UUID, person_id: uuid.UUID
    ) -> list[dict[str, Any]]:
        return (await self.get_parent_child_links_batch(clan_id, [person_id]))[person_id]

    # ── documents ────────────────────────────────────────────────────────

    async def get_documents_batch(
        self, clan_id: uuid.UUID, person_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list[dict[str, Any]]]:
        out = _empty_map(person_ids)
        if not person_ids:
            return out
        result = await self._session.execute(
            select(Document).where(
                Document.clan_id == clan_id,
                Document.person_id.in_(person_ids),
                Document.is_deleted.is_(False),
            )
        )
        for d in result.scalars().all():
            if d.person_id in out:
                out[d.person_id].append(DocumentSummary.model_validate(d).model_dump())
        return out

    async def get_documents(self, clan_id: uuid.UUID, person_id: uuid.UUID) -> list[dict[str, Any]]:
        return (await self.get_documents_batch(clan_id, [person_id]))[person_id]

    # ── events ───────────────────────────────────────────────────────────

    async def get_events_batch(
        self, clan_id: uuid.UUID, person_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list[dict[str, Any]]]:
        out = _empty_map(person_ids)
        if not person_ids:
            return out
        for ev in await self._event_rows(clan_id, person_ids):
            if ev.person_id in out:
                out[ev.person_id].append(EventResponse.model_validate(ev).model_dump())
        return out

    async def get_events(self, clan_id: uuid.UUID, person_id: uuid.UUID) -> list[dict[str, Any]]:
        return (await self.get_events_batch(clan_id, [person_id]))[person_id]

    async def _event_rows(self, clan_id: uuid.UUID, person_ids: list[uuid.UUID]) -> list[Event]:
        result = await self._session.execute(
            select(Event).where(Event.clan_id == clan_id, Event.person_id.in_(person_ids))
        )
        return list(result.scalars().all())

    # ── timeline ─────────────────────────────────────────────────────────

    async def get_timelines_batch(
        self, clan_id: uuid.UUID, person_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list[dict[str, Any]]]:
        """Chronological timelines (birth/death, marriages, events) for N
        persons in exactly three queries."""
        out = _empty_map(person_ids)
        if not person_ids:
            return out

        # 1. Persons — scoped to the caller's clan (via membership) and
        # excluding soft-deleted, so the timeline is self-contained rather
        # than relying on the route's prior clan check.
        person_result = await self._session.execute(
            select(Person)
            .join(ClanMembership, ClanMembership.person_id == Person.id)
            .where(
                Person.id.in_(person_ids),
                ClanMembership.clan_id == clan_id,
                Person.is_deleted.is_(False),
            )
        )
        for person in person_result.scalars().all():
            if person.birth_date:
                out[person.id].append(
                    TimelineEvent(
                        event_date=to_historical_date(
                            person.birth_date,
                            person.birth_date_precision,
                            person.birth_date_display,
                            person.lunar_birth_date,
                        ),
                        event_type="birth",
                        title=t("timeline.birth"),
                    ).model_dump()
                )
            if person.death_date:
                out[person.id].append(
                    TimelineEvent(
                        event_date=to_historical_date(
                            person.death_date,
                            person.death_date_precision,
                            person.death_date_display,
                            person.lunar_death_date,
                        ),
                        event_type="death",
                        title=t("timeline.death"),
                    ).model_dump()
                )

        # 2. Marriages — clan-scoped; a soft-deleted spouse must not surface.
        p1 = aliased(Person)
        p2 = aliased(Person)
        spouse_result = await self._session.execute(
            select(
                Marriage.person1_id,
                Marriage.person2_id,
                Marriage.marriage_date,
                Marriage.marriage_date_precision,
                Marriage.marriage_date_display,
                p1.full_name.label("p1_name"),
                p1.is_deleted.label("p1_deleted"),
                p2.full_name.label("p2_name"),
                p2.is_deleted.label("p2_deleted"),
            )
            .join(p1, p1.id == Marriage.person1_id)
            .join(p2, p2.id == Marriage.person2_id)
            .where(
                or_(Marriage.person1_id.in_(person_ids), Marriage.person2_id.in_(person_ids)),
                Marriage.created_by_clan_id == clan_id,
                Marriage.is_deleted.is_(False),
            )
        )
        for row in spouse_result.mappings().all():
            if not row["marriage_date"]:
                continue
            sides = (
                (row["person1_id"], row["person2_id"], row["p2_name"], row["p2_deleted"]),
                (row["person2_id"], row["person1_id"], row["p1_name"], row["p1_deleted"]),
            )
            for pid, spouse_id, spouse_name, spouse_deleted in sides:
                if pid not in out or spouse_deleted:
                    continue
                out[pid].append(
                    TimelineEvent(
                        event_date=to_historical_date(
                            row["marriage_date"],
                            row["marriage_date_precision"],
                            row["marriage_date_display"],
                            None,
                        ),
                        event_type="marriage",
                        title=t("timeline.marriage"),
                        related_person_id=spouse_id,
                        related_person_name=spouse_name,
                    ).model_dump()
                )

        # 3. Lifecycle events.
        for ev in await self._event_rows(clan_id, person_ids):
            if ev.person_id in out:
                out[ev.person_id].append(
                    TimelineEvent(
                        event_date=to_historical_date(
                            ev.event_date, ev.event_date_precision, ev.event_date_display, None
                        ),
                        event_type=ev.event_type,
                        title=ev.title,
                        description=ev.description,
                    ).model_dump()
                )

        for timeline in out.values():
            timeline.sort(key=lambda e: (e.get("event_date") or {}).get("date") or date.max)
        return out

    async def get_timeline(self, clan_id: uuid.UUID, person_id: uuid.UUID) -> list[dict[str, Any]]:
        """Build a chronological timeline from birth/death, marriages, and events."""
        return (await self.get_timelines_batch(clan_id, [person_id]))[person_id]
