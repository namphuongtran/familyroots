"""list_clan_claims must reject a path clan that differs from the caller's active clan."""

import uuid
from typing import Any

import pytest
from fastapi import HTTPException

from app.api.v1 import claims


class _FakeHandler:
    async def list_clan_claims(
        self, *, clan_id: uuid.UUID, status: str | None, cursor: str | None, limit: int
    ) -> dict[str, Any]:
        return {"data": [], "meta": {"cursor": None, "has_more": False, "limit": limit}}


class _FakeHandlerWithData:
    async def list_clan_claims(
        self, *, clan_id: uuid.UUID, status: str | None, cursor: str | None, limit: int
    ) -> dict[str, Any]:
        return {
            "data": [{"id": "1", "status": "PENDING", "user_id": "u1"}],
            "meta": {"cursor": None, "has_more": False, "limit": limit},
        }


@pytest.mark.asyncio
async def test_list_clan_claims_rejects_path_clan_mismatch() -> None:
    path_clan = uuid.uuid4()
    active_clan = uuid.uuid4()  # different → caller is not acting in the path clan
    with pytest.raises(HTTPException) as exc:
        await claims.list_clan_claims(
            clan_id=path_clan,
            status=None,
            cursor=None,
            limit=20,
            active_clan_id=active_clan,
            user=object(),  # type: ignore[arg-type]
            handler=_FakeHandler(),  # type: ignore[arg-type]
            fields=None,
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_list_clan_claims_allows_matching_clan() -> None:
    clan = uuid.uuid4()
    result = await claims.list_clan_claims(
        clan_id=clan,
        status=None,
        cursor=None,
        limit=20,
        active_clan_id=clan,
        user=object(),  # type: ignore[arg-type]
        handler=_FakeHandler(),  # type: ignore[arg-type]
        fields=None,
    )
    assert result == {"data": [], "meta": {"cursor": None, "has_more": False, "limit": 20}}


@pytest.mark.asyncio
async def test_list_clan_claims_filters_fields() -> None:
    clan = uuid.uuid4()
    result = await claims.list_clan_claims(
        clan_id=clan,
        status=None,
        cursor=None,
        limit=20,
        active_clan_id=clan,
        user=object(),  # type: ignore[arg-type]
        handler=_FakeHandlerWithData(),  # type: ignore[arg-type]
        fields="id,status",
    )
    assert result["data"] == [{"id": "1", "status": "PENDING"}]
    assert result["meta"] == {"cursor": None, "has_more": False, "limit": 20}
