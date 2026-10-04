"""The platform role, stored in ``user_profiles.platform_role``."""

from __future__ import annotations

from typing import Literal

PlatformRole = Literal["user", "super_admin"]


def platform_role_of(stored: str | None) -> PlatformRole:
    """Read a stored ``platform_role``.

    The column has no CHECK constraint, so only the exact string ``super_admin`` names the
    platform super admin, and any other value, or none, is a plain user. ``get_super_admin``
    and ``GET /auth/me`` both read the column through this, so a client is never told a user
    is the super admin when the platform routes would refuse them.
    """
    return "super_admin" if stored == "super_admin" else "user"
