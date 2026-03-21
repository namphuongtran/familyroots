"""Domain event base class and dispatcher protocol.

Domain events are immutable records of something that happened within the
domain. They carry the data needed for side-effects (audit logging,
notifications, etc.) but contain no framework-specific dependencies.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class DomainEvent:
    """Base class for all domain events."""

    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    event_id: uuid.UUID = field(default_factory=uuid.uuid4)


# ── Audit-relevant mixin ─────────────────────────────────────────


@dataclass(frozen=True)
class AuditableEvent(DomainEvent):
    """A domain event that should produce an audit log entry.

    All subclasses are automatically picked up by the ``AuditLogHandler``.
    """

    clan_id: uuid.UUID = field(default_factory=uuid.uuid4)
    actor_id: uuid.UUID = field(default_factory=uuid.uuid4)
    actor_role: str = ""
    action: str = ""
    resource_type: str = ""
    resource_id: uuid.UUID | None = None
    old_value: dict[str, Any] | None = None
    new_value: dict[str, Any] | None = None


# ── Dispatcher protocol ──────────────────────────────────────────

EventHandler = Callable[[DomainEvent], Coroutine[Any, Any, None]]


class EventDispatcher(Protocol):
    """Dispatches domain events to registered handlers."""

    def register(
        self,
        event_type: type[DomainEvent],
        handler: EventHandler,
    ) -> None: ...

    async def dispatch(self, events: list[DomainEvent]) -> None: ...
