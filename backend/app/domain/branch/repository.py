"""Repository protocol for the Branch bounded context.

Defines the abstract persistence contract. The SQLAlchemy implementation
lives in ``app.infrastructure.persistence.branch_repository``.
"""

from __future__ import annotations

import uuid
from typing import Protocol

from app.domain.branch.entity import Branch


class BranchRepository(Protocol):
    """Abstract persistence contract for Branch entities."""

    async def get_by_id(self, branch_id: uuid.UUID, clan_id: uuid.UUID) -> Branch | None:
        """Fetch a branch by ID within a clan."""
        ...

    async def list_in_clan(self, clan_id: uuid.UUID) -> list[Branch]:
        """List all branches in a clan ordered by branch_order then name."""
        ...

    async def save(self, branch: Branch) -> None:
        """Insert or update a Branch entity."""
        ...

    async def delete(self, branch: Branch) -> None:
        """Hard-delete a branch."""
        ...
