"""list_clan_claims must reject a path clan that differs from the caller's active clan."""

import uuid

import pytest
from fastapi import HTTPException

from app.api.v1 import claims


class _FakeHandler:
    async def list_clan_claims(self, *, clan_id, status, page, page_size):
        from types import SimpleNamespace

        return SimpleNamespace(model_dump=lambda: {"claims": [], "total": 0})


@pytest.mark.asyncio
async def test_list_clan_claims_rejects_path_clan_mismatch():
    path_clan = uuid.uuid4()
    active_clan = uuid.uuid4()  # different → caller is not acting in the path clan
    with pytest.raises(HTTPException) as exc:
        await claims.list_clan_claims(
            clan_id=path_clan,
            status=None,
            page=1,
            page_size=20,
            active_clan_id=active_clan,
            user=object(),
            handler=_FakeHandler(),
            fields=None,
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_list_clan_claims_allows_matching_clan():
    clan = uuid.uuid4()
    result = await claims.list_clan_claims(
        clan_id=clan,
        status=None,
        page=1,
        page_size=20,
        active_clan_id=clan,
        user=object(),
        handler=_FakeHandler(),
        fields=None,
    )
    assert result == {"claims": [], "total": 0}
