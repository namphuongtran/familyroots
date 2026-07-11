"""_fetch_included_data must propagate a failing include sub-query, not swallow it to []."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.api.v1.persons import _fetch_included_data

pytestmark = pytest.mark.asyncio


class _FakeHandler:
    """Stand-in PersonQueryHandler: timeline raises, the rest return lists."""

    async def get_marriages(self, clan_id: uuid.UUID, person_id: uuid.UUID) -> list[Any]:
        return [{"marriage_id": "m1"}]

    async def get_parent_child(self, clan_id: uuid.UUID, person_id: uuid.UUID) -> list[Any]:
        return [{"relation_id": "pc1"}]

    async def get_timeline(self, clan_id: uuid.UUID, person_id: uuid.UUID) -> list[Any]:
        raise RuntimeError("timeline query blew up")

    async def get_documents(self, clan_id: uuid.UUID, person_id: uuid.UUID) -> list[Any]:
        return [{"document_id": "d1"}]


async def test_failing_include_propagates_not_swallowed() -> None:
    with pytest.raises(RuntimeError, match="timeline query blew up"):
        await _fetch_included_data(
            _FakeHandler(),  # type: ignore[arg-type]
            uuid.uuid4(),
            uuid.uuid4(),
            ["marriages", "timeline"],
        )


async def test_happy_path_returns_all_lists() -> None:
    result = await _fetch_included_data(
        _FakeHandler(),  # type: ignore[arg-type]
        uuid.uuid4(),
        uuid.uuid4(),
        ["marriages", "parent_child", "documents"],
    )
    assert result == {
        "marriages": [{"marriage_id": "m1"}],
        "parent_child": [{"relation_id": "pc1"}],
        "documents": [{"document_id": "d1"}],
    }
