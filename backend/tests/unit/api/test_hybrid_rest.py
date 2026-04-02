"""Unit tests for Hybrid REST API features: sparse fieldsets and compound documents."""

import uuid
from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest

from app.api.v1.persons import (
    _dedupe_person_ids,
    _fetch_included_data,
    _filter_list_by_fields,
    _serialize_person_by_profile,
)

# ── _filter_list_by_fields helper ────────────────────────────────


class TestFilterListByFields:
    """Tests for the sparse fieldsets helper function."""

    def test_none_fields_returns_original(self) -> None:
        items = [{"id": "1", "name": "A", "age": 30}]
        result = _filter_list_by_fields(items, None)
        assert result == items

    def test_empty_items_returns_empty(self) -> None:
        result = _filter_list_by_fields([], "id,name")
        assert result == []

    def test_filters_to_requested_fields(self) -> None:
        items = [
            {
                "id": "1",
                "full_name": "Test",
                "gender": "male",
                "birth_date": "2000-01-01",
                "avatar_url": None,
            },
            {
                "id": "2",
                "full_name": "Other",
                "gender": "female",
                "birth_date": "1990-05-15",
                "avatar_url": "url",
            },
        ]
        result = _filter_list_by_fields(items, "id,full_name")
        assert result == [
            {"id": "1", "full_name": "Test"},
            {"id": "2", "full_name": "Other"},
        ]

    def test_nonexistent_fields_are_silently_ignored(self) -> None:
        items = [{"id": "1", "name": "Test"}]
        result = _filter_list_by_fields(items, "id,nonexistent")
        assert result == [{"id": "1"}]

    def test_whitespace_in_fields_is_trimmed(self) -> None:
        items = [{"id": "1", "name": "Test", "age": 25}]
        result = _filter_list_by_fields(items, " id , name ")
        assert result == [{"id": "1", "name": "Test"}]

    def test_single_field(self) -> None:
        items = [{"id": "1", "name": "Test", "age": 25}]
        result = _filter_list_by_fields(items, "id")
        assert result == [{"id": "1"}]


# ── _fetch_included_data helper ─────────────────────────────────


class TestFetchIncludedData:
    """Tests for the compound document helper function."""

    @pytest.mark.asyncio
    async def test_no_includes_returns_empty_dict(self) -> None:
        handler = AsyncMock()
        result = await _fetch_included_data(handler, uuid.uuid4(), uuid.uuid4(), [])
        assert result == {}

    @pytest.mark.asyncio
    async def test_marriages_include_calls_handler(self) -> None:
        handler = AsyncMock()
        handler.get_marriages.return_value = [{"marriage_id": "m1"}]

        clan_id = uuid.uuid4()
        person_id = uuid.uuid4()
        result = await _fetch_included_data(handler, clan_id, person_id, ["marriages"])

        assert "marriages" in result
        assert result["marriages"] == [{"marriage_id": "m1"}]
        handler.get_marriages.assert_awaited_once_with(person_id)

    @pytest.mark.asyncio
    async def test_multiple_includes_fetched_in_parallel(self) -> None:
        handler = AsyncMock()
        handler.get_marriages.return_value = [{"id": "m1"}]
        handler.get_parent_child.return_value = [{"id": "pc1"}]
        handler.get_timeline.return_value = [{"id": "t1"}]

        clan_id = uuid.uuid4()
        person_id = uuid.uuid4()
        result = await _fetch_included_data(
            handler, clan_id, person_id, ["marriages", "parent_child", "timeline"]
        )

        assert "marriages" in result
        assert "parent_child" in result
        assert "timeline" in result

    @pytest.mark.asyncio
    async def test_exception_in_include_returns_empty_list(self) -> None:
        handler = AsyncMock()
        handler.get_marriages.side_effect = Exception("DB error")

        result = await _fetch_included_data(handler, uuid.uuid4(), uuid.uuid4(), ["marriages"])
        assert result["marriages"] == []

    @pytest.mark.asyncio
    async def test_unknown_include_is_ignored(self) -> None:
        handler = AsyncMock()
        result = await _fetch_included_data(
            handler, uuid.uuid4(), uuid.uuid4(), ["unknown_resource"]
        )
        assert result == {}


# ── PersonSummary / PersonDetail profile schemas ─────────────────


class TestPersonProfileSchemas:
    """Tests that profile schemas correctly narrow fields."""

    def test_summary_excludes_biography(self) -> None:
        from app.schemas.person import PersonSummary

        data = PersonSummary(
            id=uuid.uuid4(),
            full_name="Test",
            gender="male",
        )
        dumped = data.model_dump(exclude_unset=True)
        assert "biography" not in dumped
        assert "full_name" in dumped

    def test_detail_includes_birth_place(self) -> None:
        from app.schemas.person import PersonDetail

        data = PersonDetail(
            id=uuid.uuid4(),
            full_name="Test",
            gender="male",
            birth_place="Hanoi",
        )
        dumped = data.model_dump(exclude_unset=True)
        assert dumped["birth_place"] == "Hanoi"
        assert "biography" not in dumped


@dataclass
class _FakePerson:
    id: uuid.UUID
    full_name: str
    gender: str
    biography: str | None = None

    def model_dump(self) -> dict[str, object]:
        return {
            "id": self.id,
            "full_name": self.full_name,
            "gender": self.gender,
            "biography": self.biography,
        }


class TestPersonHelperUtilities:
    def test_serialize_summary_profile_filters_extra_fields(self) -> None:
        person = _FakePerson(
            id=uuid.uuid4(),
            full_name="Test",
            gender="male",
            biography="hidden",
        )

        payload = _serialize_person_by_profile(person, "summary")

        assert payload["full_name"] == "Test"
        assert "biography" not in payload

    def test_serialize_full_profile_uses_model_dump(self) -> None:
        person = _FakePerson(
            id=uuid.uuid4(),
            full_name="Test",
            gender="male",
            biography="visible",
        )

        payload = _serialize_person_by_profile(person, "full")

        assert payload["biography"] == "visible"

    def test_dedupe_person_ids_preserves_order(self) -> None:
        id1 = uuid.uuid4()
        id2 = uuid.uuid4()

        deduped = _dedupe_person_ids([id1, id2, id1, id2, id1])

        assert deduped == [id1, id2]
