"""Shared UserProfile provisioning — idempotent, race-safe upsert.

The one writer of a new ``user_profiles`` row. The repos' ``ensure_profile``
(register, onboard, invitation accept) and ``ensure_user_profile`` in
``app/core/security.py`` (first authenticated request) all call it.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.user_profile import UserProfile

logger = logging.getLogger(__name__)

# RFC 2606 reserves `.invalid`: no address under it can ever be delivered to. Response
# schemas type the profile email as `str`, not `EmailStr`, so the placeholder is safe
# to read back.
RELEASED_EMAIL_DOMAIN = "released.invalid"


async def _release_email_held_by_another_profile(
    session: AsyncSession, user_id: uuid.UUID, email: str
) -> None:
    """Free ``email`` from a row the provider no longer gives it to (ADR-078).

    ``user_profiles.id`` has no foreign key to ``auth.users``, so a row outlives its
    Supabase account. Supabase holds one live account per email at a time, and the
    caller's ``user_id`` arrived with that email from the provider, so any other row
    still holding it is stale. That row keeps its id, roles, person link and history;
    only its email becomes ``<id>@released.invalid``. Nothing moves to ``user_id``.

    Runs only when ``user_id`` has no row yet, so it fires on the insert that would
    otherwise violate ``uq_user_profiles_email``. An empty email is never released:
    the provider guarantees nothing about it, and two live accounts may both lack one.
    """
    if not email:
        return
    own_row = aliased(UserProfile)
    stmt = (
        sa.update(UserProfile)
        .where(
            UserProfile.email == email,
            UserProfile.id != user_id,
            ~sa.exists().where(own_row.id == user_id),
        )
        .values(email=sa.cast(UserProfile.id, sa.Text) + f"@{RELEASED_EMAIL_DOMAIN}")
        .returning(UserProfile.id)
    )
    released = (await session.execute(stmt)).scalars().all()
    for former_id in released:
        # Ids only: the email is personal data and stays out of the logs.
        logger.warning(
            "user_profiles: released the email of former account %s to new account %s",
            former_id,
            user_id,
        )


async def ensure_profile_row(
    session: AsyncSession,
    user_id: uuid.UUID,
    email: str,
    display_name: str | None,
    *,
    language: str | None = None,
    last_login_at: datetime | None = None,
) -> None:
    """Provision the local UserProfile row if absent.

    ON CONFLICT DO NOTHING on the PK makes a concurrent duplicate insert a no-op
    (no IntegrityError, no clobber — the first writer's row and display_name win).
    An email still held by a former account's row is released first, see
    ``_release_email_held_by_another_profile``.
    Flushes (not commits): the caller's handler/UoW owns the transaction.
    """
    await _release_email_held_by_another_profile(session, user_id, email)
    values: dict[str, Any] = {
        "id": user_id,
        "email": email,
        "display_name": display_name or email.split("@")[0],
    }
    if language is not None:
        values["language"] = language
    if last_login_at is not None:
        values["last_login_at"] = last_login_at
    stmt = pg_insert(UserProfile).values(**values).on_conflict_do_nothing(index_elements=["id"])
    await session.execute(stmt)
    await session.flush()
