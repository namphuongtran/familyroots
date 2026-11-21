"""Read-only auth query handler."""

from __future__ import annotations

import uuid

from app.domain.auth.repository import AuthQueryPort
from app.schemas.auth import UserProfile


class AuthQueryHandler:
    """Read-only handler for auth queries."""

    def __init__(self, query_port: AuthQueryPort) -> None:
        self._query_port = query_port

    async def get_profile(
        self,
        *,
        user_id: uuid.UUID,
        email: str,
        full_name: str,
        preferred_locale: str | None = None,
    ) -> UserProfile:
        """Return the authenticated user's profile."""
        # get_profile joins approved memberships only, so a membership present in
        # the view is by definition approved.
        view = await self._query_port.get_profile(user_id)
        has_pending_membership = await self._query_port.has_pending_membership(user_id)

        return UserProfile(
            id=user_id,
            email=email,
            full_name=full_name,
            preferred_locale=preferred_locale or "vi",
            clan_id=view.clan_id if view else None,
            clan_name=view.clan_name if view else None,
            role=view.role if view else None,
            is_approved=view.is_approved if view else False,
            has_pending_membership=has_pending_membership,
            person_id=view.person_id if view else None,
            platform_role=view.platform_role if view else "user",
        )
