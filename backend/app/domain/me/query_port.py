"""Query port and read models for the Me bounded context."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class ClanMembershipView:
    """One approved clan membership of the current user (typed read model —
    replaces the raw SQLAlchemy ``Row`` that used to cross this seam)."""

    clan_id: uuid.UUID
    clan_name: str
    clan_slug: str
    role: str
    joined_at: datetime | None = None


class MeQueryPort(Protocol):
    """Abstract persistence contract for Me read operations."""

    async def list_clans(self, user_id: str) -> list[ClanMembershipView]:
        """All approved clan memberships for the user, oldest first."""
        ...

    async def get_clan_membership(
        self, user_id: str, clan_id: uuid.UUID
    ) -> ClanMembershipView | None:
        """The user's approved membership in a specific clan, if any."""
        ...
