"""Generic repository protocol.

Defines a minimal CRUD contract for persistence. Concrete
implementations live in ``app.infrastructure.persistence``.

Each bounded context extends this with domain-specific query methods.
"""

from __future__ import annotations

import uuid
from typing import Protocol, TypeVar

T = TypeVar("T", covariant=True)


class Repository(Protocol[T]):
    """Minimal repository contract shared by all bounded contexts."""

    async def get_by_id(self, entity_id: uuid.UUID) -> T | None:
        """Fetch a single entity by its primary key, or ``None``."""
        ...

    async def save(self, entity: object) -> None:
        """Persist a new entity or update an existing one."""
        ...

    async def delete(self, entity: object) -> None:
        """Remove an entity from the persistent store."""
        ...
