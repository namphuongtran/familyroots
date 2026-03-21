"""Concrete domain event dispatcher.

Routes domain events to registered handlers. Includes a built-in
``AuditLogHandler`` that automatically creates ``AuditLog`` rows for
any event inheriting from ``AuditableEvent``, eliminating the need for
manual ``AuditLog(...)`` calls in route handlers.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.shared.events import AuditableEvent, DomainEvent, EventHandler
from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)


class InMemoryEventDispatcher:
    """Simple in-process event dispatcher.

    Routes each event to all handlers registered for its type.
    Handlers for parent event types also receive child events.
    """

    def __init__(self) -> None:
        self._handlers: dict[type[DomainEvent], list[EventHandler]] = defaultdict(list)

    def register(
        self,
        event_type: type[DomainEvent],
        handler: EventHandler,
    ) -> None:
        """Register a handler for a specific event type."""
        self._handlers[event_type].append(handler)

    async def dispatch(self, events: list[DomainEvent]) -> None:
        """Dispatch events to all matching handlers."""
        for event in events:
            for event_type, handlers in self._handlers.items():
                if isinstance(event, event_type):
                    for handler in handlers:
                        try:
                            await handler(event)
                        except Exception:
                            logger.exception(
                                "Event handler failed for %s",
                                type(event).__name__,
                            )


class AuditLogHandler:
    """Subscribes to ``AuditableEvent`` and writes ``AuditLog`` rows.

    This replaces ~25 manual ``AuditLog(...)`` calls currently scattered
    across all route handlers.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def handle(self, event: DomainEvent) -> None:
        """Create an AuditLog entry from an auditable domain event."""
        if not isinstance(event, AuditableEvent):
            return

        old_value: dict[str, Any] | None = event.old_value
        new_value: dict[str, Any] | None = event.new_value

        self._db.add(
            AuditLog(
                clan_id=event.clan_id,
                actor_id=event.actor_id,
                actor_role=event.actor_role,
                action=event.action,
                resource_type=event.resource_type,
                resource_id=event.resource_id,
                old_value=old_value,
                new_value=new_value,
            )
        )


def create_event_dispatcher(db: AsyncSession) -> InMemoryEventDispatcher:
    """Factory that wires up the standard event handlers."""
    dispatcher = InMemoryEventDispatcher()
    audit_handler = AuditLogHandler(db)
    dispatcher.register(AuditableEvent, audit_handler.handle)
    return dispatcher
