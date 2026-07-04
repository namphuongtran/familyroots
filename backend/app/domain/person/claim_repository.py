"""Repository protocol for Identity Claims operations."""

from __future__ import annotations

import uuid
from typing import Any, Protocol


class ClaimRepository(Protocol):
    """Abstract persistence contract for Identity Claims write operations."""

    async def get_user_profile(self, user_id: uuid.UUID) -> Any | None:
        """Get the user profile."""
        ...

    async def get_person(self, person_id: uuid.UUID) -> Any | None:
        """Get the person."""
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

    def add_claim(self, claim: Any) -> None:
        """Persist a new claim."""
        ...

    def add_audit(self, audit: Any) -> None:
        """Persist an audit log entry."""
        ...

    def add_role(self, role: Any) -> None:
        """Persist a new user clan role."""
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
        page: int,
        page_size: int,
    ) -> tuple[list[Any], int]:
        """List claims linked to persons created by the given clan."""
        ...
