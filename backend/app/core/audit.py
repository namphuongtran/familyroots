"""Audit log decorator for automatic write-action logging.

Usage::

    @audit("member.create", "member")
    async def create_member(self, data, *, actor_id, clan_id, db):
        ...
        return new_member
"""

import functools
from collections.abc import Callable
from typing import Any

from app.models.audit_log import AuditLog


def audit(action: str, resource_type: str) -> Callable[..., Callable[..., Any]]:
    """Decorator that logs a write operation to the audit_logs table.

    Expects the wrapped function to receive ``db``, ``actor_id``, and
    ``clan_id`` as keyword arguments. The commit is left to the calling
    route handler — this decorator only adds the AuditLog row to the
    session.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            db = kwargs.get("db")
            actor_id = kwargs.get("actor_id")
            clan_id = kwargs.get("clan_id")

            # Allow callers to pass snapshot of old value for updates/deletes
            old_value = kwargs.pop("_old_value", None)

            result = await func(*args, **kwargs)

            # Build new_value snapshot from the returned ORM object
            new_value = None
            resource_id = None
            if result and hasattr(result, "id"):
                resource_id = result.id
                if hasattr(result, "__table__"):
                    new_value = {
                        c.name: getattr(result, c.name)
                        for c in result.__table__.columns
                        if c.name not in ("created_at", "updated_at")
                    }

            log = AuditLog(
                clan_id=clan_id,
                actor_id=actor_id,
                actor_role=kwargs.get("actor_role", "unknown"),
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                old_value=old_value,
                new_value=new_value,
            )
            if db is not None:
                db.add(log)

            return result

        return wrapper

    return decorator
