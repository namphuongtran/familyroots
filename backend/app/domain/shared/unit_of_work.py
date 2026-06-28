"""Unit of Work protocol.

Co-ordinates a transactional boundary: all changes within a UoW are
either committed together or rolled back. On ``commit()`` the UoW also
collects domain events from tracked aggregates and dispatches them.
"""

from __future__ import annotations

from typing import Protocol

from app.domain.shared.entity import AggregateRoot


class UnitOfWork(Protocol):
    """Transactional boundary with domain event dispatching."""

    def track(self, aggregate: AggregateRoot) -> None:
        """Register an aggregate so its domain events are collected on commit."""
        ...

    async def commit(self) -> None:
        """Flush changes, dispatch collected domain events, then commit."""
        ...

    async def rollback(self) -> None:
        """Roll back all pending changes."""
        ...

    async def flush(self) -> None:
        """Flush pending changes to the database without committing."""
        ...
