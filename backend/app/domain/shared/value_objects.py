"""Reusable value objects shared across bounded contexts."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ActorInfo:
    """Identifies who is performing an action and with what role.

    Used by domain methods that need to record authorship (audit logs,
    ``created_by`` / ``updated_by`` fields, etc.).
    """

    user_id: uuid.UUID
    role: str  # "admin" | "editor" | "viewer" | "super_admin"

    @classmethod
    def from_jwt(cls, jwt_payload: dict[str, Any], role: str) -> ActorInfo:
        """Construct from a decoded Supabase JWT payload."""
        return cls(user_id=uuid.UUID(jwt_payload["sub"]), role=role)


@dataclass(frozen=True)
class ClanScope:
    """Represents the active clan context for a request.

    Wraps a raw ``clan_id`` UUID to give it semantic meaning and
    prevent mixing up plain UUID parameters.
    """

    clan_id: uuid.UUID
