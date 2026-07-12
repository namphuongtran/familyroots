"""Unit tests for the pure clan-export serializer (no I/O, no database)."""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime

import pytest

from app.services.clan_export import build_clan_export, to_json_bytes

pytestmark = pytest.mark.unit


def _clan(clan_id: uuid.UUID) -> dict[str, object]:
    return {"id": clan_id, "name": "Họ Nguyễn", "slug": "ho-nguyen"}


def _person_row(person_id: uuid.UUID, **overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "id": person_id,
        "full_name": "Cụ Thủy Tổ",
        "birth_date": date(1920, 1, 1),
        "birth_date_precision": "year",
        "is_deleted": False,
        "membership_role": "blood",
        "stored_generation": 1,
        "is_founder": True,
        "branch_id": None,
        "membership_id": uuid.uuid4(),
        "joined_at": datetime(2020, 1, 1),
        "membership_created_at": datetime(2020, 1, 1),
        "membership_updated_at": datetime(2020, 1, 2),
    }
    row.update(overrides)
    return row


def test_build_clan_export_has_exact_top_level_keys() -> None:
    clan_id = uuid.uuid4()
    person_id = uuid.uuid4()
    payload = build_clan_export(
        clan=_clan(clan_id),
        persons=[_person_row(person_id)],
        branches=[{"id": uuid.uuid4(), "name": "Chi Hai"}],
        marriages=[{"id": uuid.uuid4(), "spouse_order": 1, "is_deleted": False}],
        parent_child=[{"id": uuid.uuid4(), "relationship_type": "adopted"}],
        events=[{"id": uuid.uuid4(), "is_lunar_calendar": True}],
        documents_manifest=[{"id": uuid.uuid4(), "download_url": "https://x/y"}],
        generation_map={person_id: 1},
        exported_at=datetime(2026, 7, 12).isoformat(),
    )
    assert set(payload.keys()) == {
        "format",
        "format_version",
        "exported_at",
        "clan",
        "persons",
        "clan_memberships",
        "branches",
        "marriages",
        "parent_child",
        "events",
        "documents_manifest",
    }
    assert payload["format"] == "familyroots-clan-export"
    assert payload["format_version"] == 1


def test_build_clan_export_injects_generation_and_splits_membership() -> None:
    clan_id = uuid.uuid4()
    person_id = uuid.uuid4()
    unmapped_person_id = uuid.uuid4()
    payload = build_clan_export(
        clan=_clan(clan_id),
        persons=[
            _person_row(person_id),
            _person_row(unmapped_person_id, full_name="Không Rõ Đời", is_founder=False),
        ],
        branches=[],
        marriages=[],
        parent_child=[],
        events=[],
        documents_manifest=[],
        generation_map={person_id: 1},
        exported_at=datetime(2026, 7, 12).isoformat(),
    )
    persons = {p["full_name"]: p for p in payload["persons"]}
    assert persons["Cụ Thủy Tổ"]["generation"] == 1
    assert persons["Không Rõ Đời"]["generation"] is None
    # Membership fields must NOT leak onto the person record...
    for key in (
        "membership_role",
        "stored_generation",
        "is_founder",
        "branch_id",
        "membership_id",
        "joined_at",
        "membership_created_at",
        "membership_updated_at",
    ):
        assert key not in persons["Cụ Thủy Tổ"]
    # ...but must be present, split out, on clan_memberships — lossless: id,
    # joined_at, and both timestamps travel with the membership, not just
    # role/generation/founder/branch.
    membership = next(m for m in payload["clan_memberships"] if m["person_id"] == person_id)
    assert membership["role"] == "blood"
    assert membership["is_founder"] is True
    assert set(membership.keys()) == {
        "membership_id",
        "person_id",
        "role",
        "stored_generation",
        "is_founder",
        "branch_id",
        "joined_at",
        "created_at",
        "updated_at",
    }


def test_to_json_bytes_round_trips_and_serializes_non_json_native_types() -> None:
    clan_id = uuid.uuid4()
    person_id = uuid.uuid4()
    payload = build_clan_export(
        clan=_clan(clan_id),
        persons=[_person_row(person_id)],
        branches=[],
        marriages=[],
        parent_child=[],
        events=[],
        documents_manifest=[],
        generation_map={person_id: 1},
        exported_at=datetime(2026, 7, 12, 3, 4, 5).isoformat(),
    )
    body = to_json_bytes(payload)
    assert isinstance(body, bytes)
    decoded = json.loads(body.decode("utf-8"))
    assert decoded["clan"]["id"] == str(clan_id)
    assert decoded["persons"][0]["id"] == str(person_id)
    assert decoded["persons"][0]["birth_date"] == "1920-01-01"
    # Vietnamese diacritics must survive un-escaped (ensure_ascii=False).
    assert "Cụ Thủy Tổ" in body.decode("utf-8")
