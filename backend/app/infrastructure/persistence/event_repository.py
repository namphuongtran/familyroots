"""SQLAlchemy implementation of EventRepository.

Encapsulates all Event persistence including the complex upcoming-events
query with recurring logic (optimized as a CTE).
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.event.entity import Event as EventEntity
from app.infrastructure.persistence.event_mapper import apply_to_orm, to_domain, to_orm
from app.models.event import Event as EventModel


class SqlAlchemyEventRepository:
    """Concrete Event repository backed by SQLAlchemy + PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(
        self, event_id: uuid.UUID, clan_id: uuid.UUID
    ) -> EventEntity | None:
        result = await self._session.execute(
            select(EventModel).where(
                EventModel.id == event_id, EventModel.clan_id == clan_id
            )
        )
        model = result.scalar_one_or_none()
        return to_domain(model) if model else None

    async def list_in_clan(
        self,
        clan_id: uuid.UUID,
        *,
        person_id: uuid.UUID | None = None,
        event_type: str | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> list[EventEntity]:
        from app.core.pagination import paginate_query

        query = select(EventModel).where(EventModel.clan_id == clan_id)
        if person_id:
            query = query.where(EventModel.person_id == person_id)
        if event_type:
            query = query.where(EventModel.event_type == event_type)

        query = paginate_query(query, EventModel, cursor, limit)
        result = await self._session.execute(query)
        return [to_domain(m) for m in result.scalars().all()]

    async def get_upcoming(
        self,
        clan_id: uuid.UUID,
        *,
        today: date,
        end_date: date,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Upcoming events with recurring logic — optimized CTE."""
        result = await self._session.execute(
            text("""
                WITH next_dates AS (
                    SELECT
                        e.id, e.person_id, e.event_type, e.title,
                        e.event_date, e.is_lunar_calendar, e.is_recurring,
                        p.full_name AS person_name,
                        p.avatar_url AS person_avatar_url,
                        CASE
                            WHEN e.is_recurring THEN
                                CASE
                                    WHEN MAKE_DATE(
                                        EXTRACT(YEAR FROM :today)::int,
                                        EXTRACT(MONTH FROM e.event_date)::int,
                                        EXTRACT(DAY FROM e.event_date)::int
                                    ) >= :today
                                    THEN MAKE_DATE(
                                        EXTRACT(YEAR FROM :today)::int,
                                        EXTRACT(MONTH FROM e.event_date)::int,
                                        EXTRACT(DAY FROM e.event_date)::int
                                    )
                                    ELSE MAKE_DATE(
                                        EXTRACT(YEAR FROM :today)::int + 1,
                                        EXTRACT(MONTH FROM e.event_date)::int,
                                        EXTRACT(DAY FROM e.event_date)::int
                                    )
                                END
                            ELSE e.event_date
                        END AS next_occurrence
                    FROM public.events e
                    LEFT JOIN public.persons p ON p.id = e.person_id
                    WHERE e.clan_id = :clan_id
                        AND (e.is_recurring = true OR e.event_date >= :today)
                )
                SELECT * FROM next_dates
                WHERE next_occurrence BETWEEN :today AND :end_date
                ORDER BY next_occurrence ASC
                LIMIT :lim
            """),
            {"clan_id": clan_id, "today": today, "end_date": end_date, "lim": limit},
        )
        rows = result.mappings().all()

        upcoming = []
        for row in rows:
            next_occ = row["next_occurrence"]
            upcoming.append(
                {
                    "id": str(row["id"]),
                    "person_id": str(row["person_id"]) if row["person_id"] else None,
                    "person_name": row["person_name"],
                    "person_avatar_url": row["person_avatar_url"],
                    "event_type": row["event_type"],
                    "title": row["title"],
                    "event_date": row["event_date"].isoformat(),
                    "next_occurrence": next_occ.isoformat() if next_occ else None,
                    "days_until": (next_occ - today).days if next_occ else None,
                    "is_lunar_calendar": row["is_lunar_calendar"],
                }
            )
        return upcoming

    async def save(self, event: EventEntity) -> None:
        """Insert or update an Event."""
        existing = await self._session.execute(
            select(EventModel).where(EventModel.id == event.id)
        )
        model = existing.scalar_one_or_none()
        if model:
            apply_to_orm(event, model)
        else:
            self._session.add(to_orm(event))

    async def delete(self, event: EventEntity) -> None:
        """Hard-delete an event."""
        result = await self._session.execute(
            select(EventModel).where(EventModel.id == event.id)
        )
        model = result.scalar_one_or_none()
        if model:
            await self._session.delete(model)
