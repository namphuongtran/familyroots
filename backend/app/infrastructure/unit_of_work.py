"""SQLAlchemy-backed Unit of Work.

Wraps an ``AsyncSession`` and adds domain event dispatching. On
``commit()``, the UoW:

1. Flushes pending changes to the DB
2. Collects domain events from all tracked aggregates
3. Dispatches events to handlers (audit log, notifications, …)
4. Commits the transaction (including any audit log rows added by handlers)
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.shared.entity import AggregateRoot
from app.domain.shared.events import DomainEvent
from app.infrastructure.event_dispatcher import InMemoryEventDispatcher


class SqlAlchemyUnitOfWork:
    """Concrete UoW backed by SQLAlchemy + domain event dispatching."""

    def __init__(
        self,
        session: AsyncSession,
        event_dispatcher: InMemoryEventDispatcher,
    ) -> None:
        self._session = session
        self._dispatcher = event_dispatcher
        self._aggregates: list[AggregateRoot] = []

    @property
    def session(self) -> AsyncSession:
        """Access the underlying session for repositories."""
        return self._session

    def track(self, aggregate: AggregateRoot) -> None:
        """Register an aggregate root so its events are collected on commit."""
        if aggregate not in self._aggregates:
            self._aggregates.append(aggregate)

    async def commit(self) -> None:
        """Flush, collect events, dispatch them, then commit."""
        await self._session.flush()

        # Collect domain events from all tracked aggregates
        events: list[DomainEvent] = []
        for aggregate in self._aggregates:
            events.extend(aggregate.collect_events())

        # Dispatch events (e.g. audit log handler adds AuditLog rows)
        if events:
            await self._dispatcher.dispatch(events)

        await self._session.commit()

        # Clear tracked aggregates after successful commit
        self._aggregates.clear()

    async def rollback(self) -> None:
        """Roll back the current transaction."""
        await self._session.rollback()
        self._aggregates.clear()

    async def flush(self) -> None:
        """Flush pending changes without committing."""
        await self._session.flush()
