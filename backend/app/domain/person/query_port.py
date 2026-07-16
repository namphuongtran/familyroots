"""Query Port protocol for the Person bounded context."""

from __future__ import annotations

import uuid
from typing import Any, Protocol


class PersonQueryPort(Protocol):
    """Abstract persistence contract for Person read operations.
    Handles retrieving aggregations and nested relations for the application layer.
    """

    async def get_marriages(self, clan_id: uuid.UUID, person_id: uuid.UUID) -> list[dict[str, Any]]:
        """Fetch marriages for a person, scoped to the active clan."""
        ...

    async def get_parent_child_links(
        self, clan_id: uuid.UUID, person_id: uuid.UUID
    ) -> list[dict[str, Any]]:
        """Fetch parent-child links for a person, scoped to the active clan."""
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

    # Batch forms — one query serves N persons (the batch endpoint must stay
    # O(1) queries per include token, not O(N) per person). Each returns a map
    # keyed by every requested person id (empty list when nothing matches).

    async def get_marriages_batch(
        self, clan_id: uuid.UUID, person_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list[dict[str, Any]]]: ...

    async def get_parent_child_links_batch(
        self, clan_id: uuid.UUID, person_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list[dict[str, Any]]]: ...

    async def get_documents_batch(
        self, clan_id: uuid.UUID, person_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list[dict[str, Any]]]: ...

    async def get_events_batch(
        self, clan_id: uuid.UUID, person_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list[dict[str, Any]]]: ...

    async def get_timelines_batch(
        self, clan_id: uuid.UUID, person_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list[dict[str, Any]]]: ...
