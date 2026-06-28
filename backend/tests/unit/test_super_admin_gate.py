"""The platform super-admin gate must reject non-super-admins and inactive profiles.

platform_admin had zero coverage (2026-06-28 review); get_super_admin is a pure
function of the resolved profile, so it's unit-testable without a DB.
"""

from types import SimpleNamespace

import pytest

from app.core.exceptions import ForbiddenError
from app.core.security import get_super_admin

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


def _profile(platform_role: str | None, is_active: bool) -> SimpleNamespace:
    return SimpleNamespace(platform_role=platform_role, is_active=is_active)


async def test_active_super_admin_allowed() -> None:
    p = _profile("super_admin", True)
    result = await get_super_admin(p)  # type: ignore[arg-type]
    assert result is p  # type: ignore[comparison-overlap]


async def test_non_super_admin_rejected() -> None:
    with pytest.raises(ForbiddenError):
        await get_super_admin(_profile(None, True))  # type: ignore[arg-type]


async def test_inactive_super_admin_rejected() -> None:
    with pytest.raises(ForbiddenError):
        await get_super_admin(_profile("super_admin", False))  # type: ignore[arg-type]
