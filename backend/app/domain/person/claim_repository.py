"""Repository protocol for Identity Claims operations."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Protocol


class ClaimRepository(Protocol):
    """Abstract persistence contract for Identity Claims write operations."""

    async def get_user_profile(self, user_id: uuid.UUID) -> Any | None:
        """Get the user profile."""
        ...

    async def get_person(self, person_id: uuid.UUID) -> Any | None:
        """Get the person, regardless of soft-delete state.

        Used only where the person reference is ALREADY established (cancel_claim's
        non-gating audit lookup, unlink_identity's resolution of an existing link) —
        never to admit a NEW claim/prelink. See get_live_person for that."""
        ...

    async def get_live_person(self, person_id: uuid.UUID) -> Any | None:
        """Get the person, or None if it doesn't exist OR is soft-deleted.

        Used to resolve the CLAIM TARGET at the two claim-creation sites
        (submit_claim, prelink_identity): a soft-deleted person must be invisible
        to a new claim, the same as every other write guard (M3)."""
        ...

    async def get_claim(self, claim_id: uuid.UUID, load_person: bool = False) -> Any | None:
        """Get an identity claim by ID."""
        ...

    async def lock_person(self, person_id: uuid.UUID) -> None:
        """Take a row lock on the person for the current transaction.

        Serializes concurrent identity-linking operations for the same person so the
        loser observes ``is_person_linked() is True`` and fails with a clean
        ``ConflictError`` instead of racing to the ``user_profiles.person_id`` unique
        index (which would otherwise raise a raw IntegrityError → 500)."""
        ...

    async def is_person_linked(self, person_id: uuid.UUID) -> bool:
        """Check if a person is already linked to any user."""
        ...

    async def has_pending_claims(self, user_id: uuid.UUID) -> bool:
        """Check if the user has any pending claims."""
        ...

    async def get_role(self, user_id: uuid.UUID, clan_id: uuid.UUID) -> str | None:
        """Get the user's role in a specific clan."""
        ...

    async def get_last_approved_claim(self, user_id: uuid.UUID, person_id: uuid.UUID) -> Any | None:
        """Get the user's most recent approved claim for a person."""
        ...

    async def create_claim(
        self,
        *,
        user_id: uuid.UUID,
        person_id: uuid.UUID,
        status: str,
        requester_note: str | None = None,
        reviewer_note: str | None = None,
        reviewed_by: uuid.UUID | None = None,
        reviewed_at: datetime | None = None,
    ) -> Any:
        """Create an identity_claims row, flush, and return it (id populated).

        Builds the ORM row inside the adapter so the application layer never imports
        ``app.models``."""
        ...

    def add_role(
        self,
        *,
        user_id: uuid.UUID,
        clan_id: uuid.UUID,
        role: str,
        is_approved: bool,
        approved_by: uuid.UUID | None = None,
        approved_at: datetime | None = None,
    ) -> None:
        """Stage a user_clan_roles row (ORM built in the adapter)."""
        ...

    async def auto_reject_other_pending_claims(
        self,
        person_id: uuid.UUID,
        exclude_claim_id: uuid.UUID,
        admin_id: uuid.UUID,
        reviewer_note: str,
    ) -> None:
        """Auto-reject pending claims for the person except the approved one."""
        ...

    async def auto_reject_all_pending_claims(
        self,
        user_id: uuid.UUID,
        person_id: uuid.UUID,
        admin_id: uuid.UUID,
        reviewer_note: str,
    ) -> None:
        """Auto-reject orphan pending claims for a user or person."""
        ...


class ClaimQueryPort(Protocol):
    """Abstract persistence contract for Identity Claims read operations."""

    async def list_clan_claims(
        self,
        clan_id: uuid.UUID,
        status: str | None,
        cursor: str | None,
        limit: int,
    ) -> list[Any]:
        """List claims linked to persons created by the given clan."""
        ...

    async def list_user_claims(
        self,
        user_id: uuid.UUID,
        status: str | None,
        cursor: str | None,
        limit: int,
    ) -> list[Any]:
        """List claims submitted by the given user, across all clans."""
        ...
