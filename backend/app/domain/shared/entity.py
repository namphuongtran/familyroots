"""Base entity and aggregate root classes.

All domain entities inherit from ``Entity``. Entities that serve as
aggregate roots inherit from ``AggregateRoot`` and gain the ability to
collect and emit domain events during their lifecycle.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from app.domain.shared.events import DomainEvent


@dataclass
class Entity:
    """Base identity class — every domain entity carries a UUID."""

    id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class AggregateRoot(Entity):
    """Aggregate root that collects domain events.

    Use ``add_event()`` inside domain methods (e.g. ``soft_delete``).
    The Unit of Work harvests events via ``collect_events()`` on commit
    and dispatches them to registered handlers (audit log, notifications, …).
    """

    _events: list[DomainEvent] = field(default_factory=list, repr=False, compare=False)

    def add_event(self, event: DomainEvent) -> None:
        """Append a domain event to the internal buffer."""
        self._events.append(event)

    def collect_events(self) -> list[DomainEvent]:
        """Drain and return all pending domain events."""
        events = list(self._events)
        self._events.clear()
        return events
