"""Query Port protocol for the Person bounded context."""

from __future__ import annotations

import uuid
from typing import Any, Protocol


class PersonQueryPort(Protocol):
    """Abstract persistence contract for Person read operations.
    Handles retrieving aggregations and nested relations for the application layer.
    """

    async def get_marriages(self, person_id: uuid.UUID) -> list[dict[str, Any]]:
        """Fetch all marriages for a person."""
        ...

    async def get_parent_child_links(self, person_id: uuid.UUID) -> list[dict[str, Any]]:
        """Fetch all parent-child relationships for a person."""
        ...

    async def get_documents(self, clan_id: uuid.UUID, person_id: uuid.UUID) -> list[dict[str, Any]]:
        """Fetch all documents linked to a person in a given clan."""
        ...

    async def get_events(self, clan_id: uuid.UUID, person_id: uuid.UUID) -> list[dict[str, Any]]:
        """Fetch all lifecycle events for a person in a given clan."""
        ...

    async def get_timeline(self, clan_id: uuid.UUID, person_id: uuid.UUID) -> list[dict[str, Any]]:
        """Build a chronological timeline combining birth, death, marriages, and events."""
        ...
