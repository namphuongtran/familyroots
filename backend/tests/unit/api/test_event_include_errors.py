"""The event include=person sub-query must not mask faults as person: null.

`except Exception: data["person"] = None` converted any DB fault into a
silent null — a client would believe the event has no linked person and clear
its cache. Policy (same as persons includes): only a genuinely missing person
(EntityNotFoundError — e.g. soft-deleted after the event was created) is
null; every other failure propagates so the standard error envelope is
produced.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.api.v1.events import _included_person
from app.domain.shared.exceptions import EntityNotFoundError

pytestmark = pytest.mark.asyncio


class _Person:
    id = uuid.uuid4()
    full_name = "Nguyễn Văn A"
    gender = "male"
    avatar_url = None


class _OkHandler:
    async def get(self, query: Any) -> _Person:
        return _Person()


class _MissingHandler:
    async def get(self, query: Any) -> _Person:
        raise EntityNotFoundError("person_not_found")


class _FaultyHandler:
    async def get(self, query: Any) -> _Person:
        raise RuntimeError("db connection lost")


async def test_found_person_is_summarized() -> None:
    out = await _included_person(_OkHandler(), uuid.uuid4(), uuid.uuid4())  # type: ignore[arg-type]
    assert out == {
        "id": str(_Person.id),
        "full_name": "Nguyễn Văn A",
        "gender": "male",
        "avatar_url": None,
    }


async def test_missing_person_is_null() -> None:
    out = await _included_person(_MissingHandler(), uuid.uuid4(), uuid.uuid4())  # type: ignore[arg-type]
    assert out is None


async def test_faults_propagate_not_swallowed() -> None:
    with pytest.raises(RuntimeError, match="db connection lost"):
        await _included_person(_FaultyHandler(), uuid.uuid4(), uuid.uuid4())  # type: ignore[arg-type]
