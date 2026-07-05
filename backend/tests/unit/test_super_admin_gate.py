"""The platform super-admin gate must reject non-super-admins.

platform_admin had zero coverage (2026-06-28 review); get_super_admin is a pure
function of the resolved profile, so it's unit-testable without a DB. Account
deactivation (is_active) is enforced upstream in ensure_user_profile — which
get_super_admin depends on — so it is tested in test_account_deactivation.py, not here.
"""

from types import SimpleNamespace

import pytest

from app.core.exceptions import ForbiddenError
from app.core.security import get_super_admin

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


def _profile(platform_role: str | None) -> SimpleNamespace:
    # is_active is guaranteed True by ensure_user_profile before get_super_admin runs.
    return SimpleNamespace(platform_role=platform_role, is_active=True)


async def test_active_super_admin_allowed() -> None:
    p = _profile("super_admin")
    result = await get_super_admin(p)  # type: ignore[arg-type]
    assert result is p  # type: ignore[comparison-overlap]


async def test_non_super_admin_rejected() -> None:
    with pytest.raises(ForbiddenError):
        await get_super_admin(_profile(None))  # type: ignore[arg-type]
