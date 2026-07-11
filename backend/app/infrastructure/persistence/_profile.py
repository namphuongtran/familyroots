"""Shared UserProfile provisioning — idempotent, race-safe upsert.

Extracted from the two identical repo `ensure_profile` bodies; mirrors the
`ON CONFLICT DO NOTHING` idiom already used in `app/core/security.py`.
"""

from __future__ import annotations

import uuid

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_profile import UserProfile


async def ensure_profile_row(
    session: AsyncSession, user_id: uuid.UUID, email: str, display_name: str | None
) -> None:
    """Provision the local UserProfile row if absent.

    ON CONFLICT DO NOTHING on the PK makes a concurrent duplicate insert a no-op
    (no IntegrityError, no clobber — the first writer's row and display_name win).
    Flushes (not commits): the caller's handler/UoW owns the transaction.
    """
    stmt = (
        pg_insert(UserProfile)
        .values(
            id=user_id,
            email=email,
            display_name=display_name or email.split("@")[0],
        )
        .on_conflict_do_nothing(index_elements=["id"])
    )
    await session.execute(stmt)
    await session.flush()
