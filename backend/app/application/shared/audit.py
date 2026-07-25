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
from app.domain.shared.unit_of_work import UnitOfWork
from app.domain.shared.value_objects import ActorInfo


@dataclass(frozen=True)
class CrudAuditEvent(AuditableEvent):
    """Generic auditable event for CRUD operations."""

    changes: dict[str, Any] = field(default_factory=dict)


def track_audit_event(
    uow: UnitOfWork,
    *,
    action: str,
    resource_type: str,
    resource_id: uuid.UUID | None,
    actor: ActorInfo,
    clan_id: uuid.UUID | None,
    old_value: dict[str, Any] | None = None,
    new_value: dict[str, Any] | None = None,
) -> None:
    """Buffer a CrudAuditEvent on a tracked aggregate WITHOUT committing.

    The caller commits (dispatching it through the fail-closed ``AuditLogHandler``,
    which enriches ip/user_agent from the request-scoped ``RequestMeta``) as part of
    its own write transaction. This is the buffer half of ``emit_audit_event``, split
    out so handlers that already own a commit (e.g. the claim handlers) can fold the
    audit row into their existing transaction instead of committing twice.
    """
    agg = AggregateRoot()
    agg.add_event(
        CrudAuditEvent(
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            # AuditableEvent types clan_id as required (an actor/tenant footgun guard),
            # but audit_logs.clan_id is nullable and some system-adjacent actions carry
            # no controlling clan (e.g. cancelling a claim on a person whose origin clan
            # was cleared). track_audit_event deliberately accepts None and passes it
            # through; the AuditLogHandler and column both tolerate it.
            clan_id=clan_id,  # type: ignore[arg-type]
            actor_id=actor.user_id,
            actor_role=actor.role,
            old_value=old_value,
            new_value=new_value,
        )
    )
    uow.track(agg)


async def emit_audit_event(
    uow: UnitOfWork,
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
    track_audit_event(
        uow,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        actor=actor,
        clan_id=clan_id,
        old_value=old_value,
        new_value=new_value,
    )
    await uow.commit()
