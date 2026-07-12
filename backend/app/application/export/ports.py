"""Read-side query port for the clan export use case.

Deliberately narrow: only the query port lives here. Storage presigning goes
through the existing `StoragePort` protocol in `app.domain.document.repository`
— no second storage protocol is defined for this aggregate.
"""

from __future__ import annotations

import uuid
from typing import Any, Protocol


class ExportQueryPort(Protocol):
    """Archival read-side queries — every method returns raw row dicts
    (``SELECT *``-shaped), including soft-deleted rows where noted, since this
    is a full archival dump rather than a normal CQRS read model."""

    async def clan(self, clan_id: uuid.UUID) -> dict[str, Any]:
        """Fetch the clan's own row."""
        ...

    async def persons(self, clan_id: uuid.UUID) -> list[dict[str, Any]]:
        """All persons with a membership in this clan — INCLUDES soft-deleted
        persons. Each row carries the person's own columns plus the joined
        membership fields ``membership_role``/``stored_generation``/
        ``is_founder``/``branch_id``/``membership_id``/``joined_at``/
        ``membership_created_at``/``membership_updated_at`` (the latter two are
        aliased off ``cm.created_at``/``cm.updated_at`` so they don't collide
        with the person row's own ``created_at``/``updated_at``)."""
        ...

    async def branches(self, clan_id: uuid.UUID) -> list[dict[str, Any]]:
        """All branches (chi/phái) owned by this clan."""
        ...

    async def marriages(self, clan_id: uuid.UUID) -> list[dict[str, Any]]:
        """All marriages created by this clan — INCLUDES soft-deleted rows."""
        ...

    async def parent_child(self, clan_id: uuid.UUID) -> list[dict[str, Any]]:
        """All parent-child edges created by this clan — INCLUDES soft-deleted
        rows."""
        ...

    async def events(self, clan_id: uuid.UUID) -> list[dict[str, Any]]:
        """All events (giỗ, anniversaries, ...) owned by this clan."""
        ...

    async def documents(self, clan_id: uuid.UUID) -> list[dict[str, Any]]:
        """Live (non-deleted) documents owned by this clan."""
        ...

    async def generation_map(self, clan_id: uuid.UUID) -> dict[uuid.UUID, int]:
        """Graph-computed đời (generation) per person, keyed by person_id.

        Walks `public.get_family_tree_flat` from every clan founder
        (`clan_memberships.is_founder = true`); the first founder processed
        wins for any person reachable from more than one founder."""
        ...
