"""Event use-case handlers.

Orchestrate event CRUD through domain entities and repository protocol.
No SQLAlchemy imports — fully DIP-compliant.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

from app.domain.event.entity import Event
from app.domain.event.repository import EventRepository
from app.domain.shared.exceptions import EntityNotFoundError
from app.domain.shared.unit_of_work import UnitOfWork
from app.domain.shared.value_objects import ActorInfo
from app.schemas.event import EventResponse


class EventCommandHandler:
    """Handles event write operations."""

    def __init__(self, repo: EventRepository, uow: UnitOfWork) -> None:
        self._repo = repo
        self._uow = uow

    async def create(
        self,
        *,
        clan_id: uuid.UUID,
        actor: ActorInfo,
        person_id: uuid.UUID | None,
        event_type: str,
        title: str,
        description: str | None,
        event_date: date,
        is_lunar_calendar: bool,
        is_recurring: bool,
        notify_days_before: int | None,
    ) -> EventResponse:
        event = Event.create(
            clan_id=clan_id,
            actor=actor,
            event_type=event_type,
            title=title,
            event_date=event_date,
            person_id=person_id,
            description=description,
            is_lunar_calendar=is_lunar_calendar,
            is_recurring=is_recurring,
            notify_days_before=notify_days_before or 7,
        )
        self._uow.track(event)
        await self._repo.save(event)
        await self._uow.commit()

        return EventResponse(
            id=event.id,
            clan_id=event.clan_id,
            person_id=event.person_id,
            event_type=event.event_type,
            title=event.title,
            description=event.description,
            event_date=event.event_date,
            is_lunar_calendar=event.is_lunar_calendar,
            is_recurring=event.is_recurring,
            notify_days_before=event.notify_days_before,
            created_by=event.created_by,
            created_at=event.created_at,
            updated_at=event.updated_at,
        )

    async def update(
        self,
        *,
        event_id: uuid.UUID,
        clan_id: uuid.UUID,
        actor: ActorInfo,
        changes: dict[str, Any],
    ) -> EventResponse:
        event = await self._get_or_raise(event_id, clan_id)
        event.update(changes, actor)
        self._uow.track(event)
        await self._repo.save(event)
        await self._uow.commit()

        return EventResponse(
            id=event.id,
            clan_id=event.clan_id,
            person_id=event.person_id,
            event_type=event.event_type,
            title=event.title,
            description=event.description,
            event_date=event.event_date,
            is_lunar_calendar=event.is_lunar_calendar,
            is_recurring=event.is_recurring,
            notify_days_before=event.notify_days_before,
            created_by=event.created_by,
            created_at=event.created_at,
            updated_at=event.updated_at,
        )

    async def delete(
        self,
        *,
        event_id: uuid.UUID,
        clan_id: uuid.UUID,
        actor: ActorInfo,
    ) -> None:
        event = await self._get_or_raise(event_id, clan_id)
        event.delete(actor)
        self._uow.track(event)
        await self._repo.delete(event)
        await self._uow.commit()

    async def _get_or_raise(self, event_id: uuid.UUID, clan_id: uuid.UUID) -> Event:
        event = await self._repo.get_by_id(event_id, clan_id)
        if not event:
            raise EntityNotFoundError("event_not_found")
        return event


class EventQueryHandler:
    """Read-only handler for event queries."""

    def __init__(self, repo: EventRepository) -> None:
        self._repo = repo

    async def get(self, *, event_id: uuid.UUID, clan_id: uuid.UUID) -> EventResponse:
        event = await self._repo.get_by_id(event_id, clan_id)
        if not event:
            raise EntityNotFoundError("event_not_found")
        return EventResponse(
            id=event.id,
            clan_id=event.clan_id,
            person_id=event.person_id,
            event_type=event.event_type,
            title=event.title,
            description=event.description,
            event_date=event.event_date,
            is_lunar_calendar=event.is_lunar_calendar,
            is_recurring=event.is_recurring,
            notify_days_before=event.notify_days_before,
            created_by=event.created_by,
            created_at=event.created_at,
            updated_at=event.updated_at,
        )

    async def list_events(
        self,
        *,
        clan_id: uuid.UUID,
        person_id: uuid.UUID | None = None,
        event_type: str | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> list[EventResponse]:
        events = await self._repo.list_in_clan(
            clan_id,
            person_id=person_id,
            event_type=event_type,
            cursor=cursor,
            limit=limit,
        )
        return [
            EventResponse(
                id=e.id,
                clan_id=e.clan_id,
                person_id=e.person_id,
                event_type=e.event_type,
                title=e.title,
                description=e.description,
                event_date=e.event_date,
                is_lunar_calendar=e.is_lunar_calendar,
                is_recurring=e.is_recurring,
                notify_days_before=e.notify_days_before,
                created_by=e.created_by,
                created_at=e.created_at,
                updated_at=e.updated_at,
            )
            for e in events
        ]

    async def get_upcoming(self, *, clan_id: uuid.UUID, days: int = 30) -> list[dict[str, Any]]:
        """Get upcoming events within the next N days with recurring logic."""
        today = date.today()
        end_date = today + timedelta(days=days)
        return await self._repo.get_upcoming(clan_id, today=today, end_date=end_date)
