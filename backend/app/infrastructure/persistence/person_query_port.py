"""SQLAlchemy implementation of the Person read operations."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

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


class SqlAlchemyPersonQueryPort(PersonQueryPort):
    """SQLAlchemy implementation of PersonQueryPort."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_marriages(self, clan_id: uuid.UUID, person_id: uuid.UUID) -> list[dict[str, Any]]:
        result = await self._session.execute(
            select(Marriage).where(
                or_(Marriage.person1_id == person_id, Marriage.person2_id == person_id),
                Marriage.created_by_clan_id == clan_id,
                Marriage.is_deleted.is_(False),
            )
        )
        marriages = result.scalars().all()
        return [MarriageResponse.model_validate(m).model_dump() for m in marriages]

    async def get_parent_child_links(
        self, clan_id: uuid.UUID, person_id: uuid.UUID
    ) -> list[dict[str, Any]]:
        result = await self._session.execute(
            select(ParentChild).where(
                or_(ParentChild.parent_id == person_id, ParentChild.child_id == person_id),
                ParentChild.created_by_clan_id == clan_id,
                ParentChild.is_deleted.is_(False),
            )
        )
        links = result.scalars().all()
        return [ParentChildResponse.model_validate(link).model_dump() for link in links]

    async def get_documents(self, clan_id: uuid.UUID, person_id: uuid.UUID) -> list[dict[str, Any]]:
        result = await self._session.execute(
            select(Document).where(
                Document.clan_id == clan_id,
                Document.person_id == person_id,
                Document.is_deleted.is_(False),
            )
        )
        docs = result.scalars().all()
        return [DocumentSummary.model_validate(d).model_dump() for d in docs]

    async def get_events(self, clan_id: uuid.UUID, person_id: uuid.UUID) -> list[dict[str, Any]]:
        result = await self._session.execute(
            select(Event).where(Event.clan_id == clan_id, Event.person_id == person_id)
        )
        events = result.scalars().all()
        return [EventResponse.model_validate(e).model_dump() for e in events]

    async def get_timeline(self, clan_id: uuid.UUID, person_id: uuid.UUID) -> list[dict[str, Any]]:
        """Build a chronological timeline from birth/death, marriages, and events."""
        timeline: list[dict[str, Any]] = []

        # Fetch person for birth/death dates — scoped to the caller's clan (via
        # membership) and excluding soft-deleted, so the timeline is self-contained
        # rather than relying on the route's prior clan check.
        person_result = await self._session.execute(
            select(Person)
            .join(ClanMembership, ClanMembership.person_id == Person.id)
            .where(
                Person.id == person_id,
                ClanMembership.clan_id == clan_id,
                Person.is_deleted.is_(False),
            )
        )
        person = person_result.scalar_one_or_none()

        if person and person.birth_date:
            timeline.append(
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
        if person and person.death_date:
            timeline.append(
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

        # Fetch marriages — scoped to the caller's clan to prevent cross-clan leaks
        spouse_result = await self._session.execute(
            text("""
                SELECT m.marriage_date, m.marriage_date_precision, m.marriage_date_display,
                       m.status,
                       CASE WHEN m.person1_id = :pid THEN m.person2_id
                            ELSE m.person1_id END AS spouse_id,
                       p.full_name AS spouse_name
                FROM public.marriages m
                JOIN public.persons p
                  ON p.id = CASE WHEN m.person1_id = :pid
                                 THEN m.person2_id ELSE m.person1_id END
                WHERE (m.person1_id = :pid OR m.person2_id = :pid)
                  AND m.created_by_clan_id = :clan_id
                  AND m.is_deleted = false
                  AND p.is_deleted = false
            """),
            {"pid": person_id, "clan_id": clan_id},
        )
        for row in spouse_result.mappings().all():
            if row["marriage_date"]:
                timeline.append(
                    TimelineEvent(
                        event_date=to_historical_date(
                            row["marriage_date"],
                            row["marriage_date_precision"],
                            row["marriage_date_display"],
                            None,
                        ),
                        event_type="marriage",
                        title=t("timeline.marriage"),
                        related_person_id=row["spouse_id"],
                        related_person_name=row["spouse_name"],
                    ).model_dump()
                )

        # Fetch lifecycle events
        events_result = await self._session.execute(
            select(Event).where(Event.clan_id == clan_id, Event.person_id == person_id)
        )
        for ev in events_result.scalars().all():
            timeline.append(
                TimelineEvent(
                    event_date=to_historical_date(
                        ev.event_date, ev.event_date_precision, ev.event_date_display, None
                    ),
                    event_type=ev.event_type,
                    title=ev.title,
                    description=ev.description,
                ).model_dump()
            )

        timeline.sort(key=lambda e: (e.get("event_date") or {}).get("date") or date.max)
        return timeline
