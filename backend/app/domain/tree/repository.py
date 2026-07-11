"""Repository protocol for the Tree bounded context."""

from __future__ import annotations

import uuid
from typing import Any, Protocol


class TreeRepository(Protocol):
    """Abstract read-only query port for family tree operations."""

    async def person_in_clan(self, person_id: uuid.UUID, clan_id: uuid.UUID) -> bool:
        """Check if a person belongs to a clan."""
        ...

    async def find_clan_founder(self, clan_id: uuid.UUID) -> uuid.UUID | None:
        """Find the earliest ancestor in a clan."""
        ...

    async def build_descendants_tree(
        self,
        root_id: uuid.UUID,
        clan_id: uuid.UUID,
        max_generations: int,
    ) -> dict[str, Any] | None:
        """Build a hierarchical tree dict rooted at root_id."""
        ...

    async def get_ancestors(self, person_id: uuid.UUID, clan_id: uuid.UUID) -> list[dict[str, Any]]:
        """Return a flat list of ancestors from person up to root."""
        ...

    async def get_ancestors_flat(
        self, person_id: uuid.UUID, clan_id: uuid.UUID, max_generations: int = 50
    ) -> list[dict[str, Any]]:
        """Ancestor chain (depth ASC, self at depth 0) incl. child_id + raw generation.

        One row per lineage edge: an ancestor reached via two different children
        (pedigree collapse) appears once per lineage, each with its own child_id.
        Callers that need a deduplicated person list (e.g. get_ancestors) must
        collapse by id themselves."""
        ...

    async def find_path(
        self, from_id: uuid.UUID, to_id: uuid.UUID, clan_id: uuid.UUID
    ) -> list[dict[str, Any]]:
        """Find the relationship path between two persons."""
        ...

    async def build_focus_view(
        self,
        focus_id: uuid.UUID,
        clan_id: uuid.UUID,
        descendant_depth: int,
        base_generation: int | None,
    ) -> dict[str, Any]:
        """Enriched focus subtree (computed đời, branch, birth_order sort, has_more)."""
        ...
