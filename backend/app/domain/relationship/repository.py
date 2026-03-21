"""Repository protocol for the Relationship bounded context."""

from __future__ import annotations

import uuid
from typing import Protocol

from app.domain.relationship.entities import Marriage, ParentChild


class MarriageRepository(Protocol):
    async def get_by_id(self, marriage_id: uuid.UUID) -> Marriage | None: ...
    async def save(self, marriage: Marriage) -> None: ...


class ParentChildRepository(Protocol):
    async def get_by_id(self, link_id: uuid.UUID) -> ParentChild | None: ...
    async def save(self, link: ParentChild) -> None: ...
