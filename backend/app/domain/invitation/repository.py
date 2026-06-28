"""Repository protocol for the clan invitation feature."""

from __future__ import annotations

import uuid
from typing import Any, Protocol


class InvitationRepository(Protocol):
    async def get_pending_by_email(self, clan_id: uuid.UUID, email: str) -> Any | None:
        """Return a pending invitation for (clan_id, email), if any."""
        ...

    async def get_by_token(self, token: str) -> Any | None:
        """Return the invitation with this token, if any."""
        ...

    def add_invitation(self, invitation: Any) -> None:
        """Stage a new invitation row."""
        ...

    async def list_by_clan(self, clan_id: uuid.UUID) -> list[Any]:
        """List a clan's invitations, newest first."""
        ...

    async def ensure_profile(
        self, user_id: uuid.UUID, email: str, display_name: str | None
    ) -> None:
        """Idempotently ensure a user_profiles row exists."""
        ...

    async def get_user_role(self, user_id: uuid.UUID, clan_id: uuid.UUID) -> Any | None:
        """Existing membership for a user in a clan, if any."""
        ...

    def add_user_role(self, role: Any) -> None:
        """Stage a new user_clan_roles row."""
        ...
