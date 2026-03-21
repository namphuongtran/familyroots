"""Lightweight audit event helper for modules that don't need full DDD aggregates.

Used by documents, events, branches, and other CRUD-heavy modules
that don't warrant full domain entities but still benefit from
automated audit logging via the event dispatcher.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from app.domain.shared.entity import AggregateRoot
from app.domain.shared.events import AuditableEvent
from app.domain.shared.value_objects import ActorInfo
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork


@dataclass(frozen=True)
class CrudAuditEvent(AuditableEvent):
    """Generic auditable event for CRUD operations."""

    changes: dict[str, Any] = field(default_factory=dict)


async def emit_audit_event(
    uow: SqlAlchemyUnitOfWork,
    *,
    action: str,
    resource_type: str,
    resource_id: uuid.UUID,
    actor: ActorInfo,
    clan_id: uuid.UUID,
    old_value: dict[str, Any] | None = None,
    new_value: dict[str, Any] | None = None,
) -> None:
    """Emit a CRUD audit event through the UoW event dispatcher.

    This is the lightweight alternative to building full domain aggregates
    for simple CRUD modules.
    """
    agg = AggregateRoot()
    agg.add_event(
        CrudAuditEvent(
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            clan_id=clan_id,
            actor_id=actor.user_id,
            actor_role=actor.role,
            old_value=old_value,
            new_value=new_value,
        )
    )
    uow.track(agg)
    await uow.commit()
