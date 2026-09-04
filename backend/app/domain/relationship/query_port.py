"""Read-side ports for the Relationship bounded context.

**Separate from ``repository.py`` on purpose, and this is the whole point of
ADR-051 § 8.** ``MarriageRepository.get_by_id`` and
``ParentChildRepository.get_by_id`` load an edge for a **write** —
``app/application/relationship/handlers.py`` calls them from update and delete —
so they must keep returning an edge whose endpoint person is soft-deleted.
Otherwise an admin loses the ability to repair or remove that edge and the row
becomes unreachable through the API entirely (ADR-051 § 8).

The ports here answer the **read** question instead: what may a client be shown.
An edge whose endpoint person is soft-deleted is hidden, which is the same rule
the batch edge reads carry (``PersonQueryPort.get_marriages_batch`` and
``get_parent_child_links_batch``). Nothing cascades a person's delete
onto its edges — ADR-051 decided against that — so the rule is derived at read
time and both edge rows keep ``is_deleted = false``.

Two protocols rather than one, because the two query handlers each depend on
exactly one edge kind.
"""

from __future__ import annotations

import uuid
from typing import Protocol

from app.domain.relationship.entities import Marriage, ParentChild


class MarriageReadPort(Protocol):
    async def get_visible_by_id(
        self, marriage_id: uuid.UUID, clan_id: uuid.UUID
    ) -> Marriage | None:
        """The marriage a client may be shown, or ``None``.

        ``None`` when the row does not exist, belongs to another clan, is itself
        soft-deleted, **or** has a soft-deleted spouse on either end.
        """
        ...


class ParentChildReadPort(Protocol):
    async def get_visible_by_id(self, link_id: uuid.UUID, clan_id: uuid.UUID) -> ParentChild | None:
        """The lineage edge a client may be shown, or ``None``.

        ``None`` when the row does not exist, belongs to another clan, is itself
        soft-deleted, **or** has a soft-deleted person on either end.
        """
        ...
