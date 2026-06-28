"""Repository protocol for the Event bounded context."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any, Protocol

from app.domain.event.entity import Event


class EventRepository(Protocol):
    """Abstract persistence contract for Event entities."""

    async def get_by_id(self, event_id: uuid.UUID, clan_id: uuid.UUID) -> Event | None:
        """Fetch an event by ID within a clan."""
        ...

    async def person_in_clan(self, person_id: uuid.UUID, clan_id: uuid.UUID) -> bool:
        """Whether person_id is a member (clan_memberships) of clan_id."""
        ...

    async def list_in_clan(
        self,
        clan_id: uuid.UUID,
        *,
        person_id: uuid.UUID | None = None,
        event_type: str | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> list[Event]:
        """List events in a clan with optional filters and cursor pagination."""
        ...

    async def get_upcoming(
        self,
        clan_id: uuid.UUID,
        *,
        today: date,
        end_date: date,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get upcoming events with recurring logic (returns raw dicts for complex SQL)."""
        ...

    async def save(self, event: Event) -> None:
        """Insert or update an Event entity."""
        ...

    async def delete(self, event: Event) -> None:
        """Hard-delete an event."""
        ...
