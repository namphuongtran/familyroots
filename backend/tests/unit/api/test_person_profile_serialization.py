"""profile=summary|detail must have deterministic, honest field sets.

PersonSummary declared generation/is_founder/membership_role but list/get
serialize from PersonResponse instances that carry none of them, and
exclude_unset=True silently dropped the keys — so the same resource had two
key-presence grammars depending on ?profile=. Fix policy:

- The phantom membership fields are REMOVED from the schema (đời/generation
  is graph-computed on tree endpoints; clan_memberships.generation is a
  deprecated display source — resurfacing it here would be worse than
  omitting it). Search keeps its own hand-rolled payload.
- Serialization emits every declared key, always — a client can rely on key
  presence regardless of which fields happen to be set.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.api.v1.persons import _serialize_person_by_profile
from app.schemas.person import PersonDetail, PersonResponse, PersonSummary


def _person() -> PersonResponse:
    now = datetime.now(UTC)
    return PersonResponse(
        id=uuid.uuid4(),
        full_name="Nguyễn Văn A",
        gender="male",
        nationality="VN",
        is_deleted=False,
        created_by=uuid.uuid4(),
        created_at=now,
        updated_at=now,
    )


def test_summary_declares_no_phantom_membership_fields() -> None:
    phantom = {"generation", "is_founder", "membership_role"}
    assert not (phantom & set(PersonSummary.model_fields))
    assert not (phantom & set(PersonDetail.model_fields))


def test_summary_profile_emits_every_declared_key() -> None:
    out = _serialize_person_by_profile(_person(), "summary")
    assert set(out) == set(PersonSummary.model_fields)


def test_detail_profile_emits_every_declared_key() -> None:
    out = _serialize_person_by_profile(_person(), "detail")
    assert set(out) == set(PersonDetail.model_fields)
