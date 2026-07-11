"""Task 3 (HistoricalDate contract): person/event/marriage RESPONSE schemas nest each
date field into `{date, precision, display, lunar}` instead of a scalar + top-level
`_approx`/`lunar_*` fields.

Covers the two real serialization shapes these schemas are validated from in production:
- a domain aggregate (`Person`/`Marriage`/`Event`) that does NOT yet carry
  `<field>_precision`/`<field>_display` (Task 5 wires that) — precision/display must
  gracefully default to "exact"/None rather than erroring.
- an ORM-row-like object that DOES carry the flat `<field>_precision`/`<field>_display`
  (+ lunar) columns added by migration 012 — these must flow into the nested object.
Also covers re-validating a narrower profile (PersonSummary/PersonMini/PersonDetail) from
an already-built PersonResponse, which must pass the nested HistoricalDate through
unchanged rather than re-deriving it (and losing precision/display/lunar in the process).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime

import pytest

from app.domain.event.entity import Event
from app.domain.person.entity import Person
from app.domain.relationship.entities import Marriage
from app.schemas.event import EventResponse, TimelineEvent, UpcomingEvent
from app.schemas.historical_date import HistoricalDate
from app.schemas.marriage import MarriageResponse
from app.schemas.person import (
    PersonDetail,
    PersonDetailComposite,
    PersonMini,
    PersonResponse,
    PersonSummary,
)

pytestmark = pytest.mark.unit


# ── PersonResponse family ─────────────────────────────────────────


def _person() -> Person:
    return Person(
        full_name="Nguyễn Văn A",
        gender="male",
        birth_date=date(1950, 3, 1),
        birth_date_precision="circa",
        birth_date_display="khoảng 1950",
        lunar_birth_date="15/2 Canh Dần",
        death_date=None,
        nationality="VN",
        created_by=uuid.uuid4(),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def test_person_response_nests_birth_and_death_date() -> None:
    resp = PersonResponse.model_validate(_person())

    assert isinstance(resp.birth_date, HistoricalDate)
    assert resp.birth_date.date == date(1950, 3, 1)
    assert resp.birth_date.lunar == "15/2 Canh Dần"
    # Task 5 wired precision/display onto the domain entity — the response must
    # carry the entity's real values through, not default them to "exact"/None.
    assert resp.birth_date.precision == "circa"
    assert resp.birth_date.display == "khoảng 1950"

    assert resp.death_date == HistoricalDate(date=None, precision="exact", display=None, lunar=None)


def test_person_response_drops_top_level_approx_and_lunar_fields() -> None:
    dumped = PersonResponse.model_validate(_person()).model_dump()

    for legacy_field in (
        "birth_date_approx",
        "death_date_approx",
        "lunar_birth_date",
        "lunar_death_date",
    ):
        assert legacy_field not in dumped
        assert legacy_field not in PersonResponse.model_fields
    assert dumped["birth_date"] == {
        "date": date(1950, 3, 1),
        "precision": "circa",
        "display": "khoảng 1950",
        "lunar": "15/2 Canh Dần",
    }


@dataclass
class _PersonOrmRow:
    """Stand-in for the ORM row: carries the flat precision/display columns."""

    birth_date: date | None
    birth_date_precision: str
    birth_date_display: str | None
    death_date: date | None
    death_date_precision: str
    death_date_display: str | None
    lunar_birth_date: str | None = None
    lunar_death_date: str | None = None


def test_person_mini_builds_historical_date_from_flat_orm_columns() -> None:
    row = _PersonOrmRow(
        birth_date=date(1750, 1, 1),
        birth_date_precision="circa",
        birth_date_display="khoảng 1750",
        death_date=date(1820, 6, 1),
        death_date_precision="year",
        death_date_display="1820",
        lunar_birth_date="Canh Ngọ",
        lunar_death_date="Canh Thìn",
    )
    mini = PersonMini.model_validate(
        {**row.__dict__, "id": uuid.uuid4(), "full_name": "Cụ Tổ", "gender": "male"}
    )

    assert mini.birth_date == HistoricalDate(
        date=date(1750, 1, 1), precision="circa", display="khoảng 1750", lunar="Canh Ngọ"
    )
    assert mini.death_date == HistoricalDate(
        date=date(1820, 6, 1), precision="year", display="1820", lunar="Canh Thìn"
    )


@pytest.mark.parametrize("profile_cls", [PersonSummary, PersonDetail])
def test_profile_schema_passes_through_nested_date_from_person_response(
    profile_cls: type[PersonSummary],
) -> None:
    """PersonSummary/PersonDetail re-validated from a PersonResponse must NOT re-derive
    precision/display/lunar from (nonexistent) flat attributes on the response model —
    they must pass the already-nested HistoricalDate through unchanged."""
    full = PersonResponse.model_validate(_person())

    narrowed = profile_cls.model_validate(full)

    assert narrowed.birth_date == full.birth_date
    assert narrowed.birth_date.lunar == "15/2 Canh Dần"


def test_person_detail_composite_nests_dates_like_person_response() -> None:
    composite = PersonDetailComposite.model_validate(_person())
    assert composite.birth_date.date == date(1950, 3, 1)
    assert composite.marriages is None


# ── EventResponse family ──────────────────────────────────────────


def _event() -> Event:
    return Event(
        clan_id=uuid.uuid4(),
        event_type="death_anniversary",
        title="Giỗ tổ",
        event_date=date(2024, 4, 10),
        is_lunar_calendar=True,
        created_by=uuid.uuid4(),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def test_event_response_nests_event_date_keeps_is_lunar_calendar_separate() -> None:
    resp = EventResponse.model_validate(_event())

    assert resp.event_date == HistoricalDate(
        date=date(2024, 4, 10), precision="exact", display=None, lunar=None
    )
    assert resp.is_lunar_calendar is True
    assert "event_date_precision" not in EventResponse.model_fields


@dataclass
class _EventOrmRow:
    id: uuid.UUID
    clan_id: uuid.UUID
    event_type: str
    title: str
    event_date: date
    event_date_precision: str
    event_date_display: str | None
    is_lunar_calendar: bool
    is_recurring: bool
    notify_days_before: int
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    person_id: uuid.UUID | None = None
    description: str | None = None


def test_event_response_reads_precision_display_from_orm_row() -> None:
    row = _EventOrmRow(
        id=uuid.uuid4(),
        clan_id=uuid.uuid4(),
        event_type="custom",
        title="Ceremony",
        event_date=date(1900, 1, 1),
        event_date_precision="unknown",
        event_date_display="đầu thế kỷ 20",
        is_lunar_calendar=False,
        is_recurring=True,
        notify_days_before=7,
        created_by=uuid.uuid4(),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    resp = EventResponse.model_validate(row)

    assert resp.event_date == HistoricalDate(
        date=date(1900, 1, 1), precision="unknown", display="đầu thế kỷ 20", lunar=None
    )


def test_upcoming_event_nests_event_date_next_occurrence_stays_scalar() -> None:
    upcoming = UpcomingEvent(
        id=uuid.uuid4(),
        event_type="birthday",
        title="Sinh nhật",
        event_date=date(1990, 5, 5),
        next_occurrence=date(2026, 5, 5),
        days_until=10,
        is_lunar_calendar=False,
    )

    assert upcoming.event_date == HistoricalDate(
        date=date(1990, 5, 5), precision="exact", display=None, lunar=None
    )
    assert upcoming.next_occurrence == date(2026, 5, 5)


def test_timeline_event_nests_event_date_and_has_no_legacy_approx_field() -> None:
    """Task 5 retired the redundant `date_approx` boolean — precision (nested inside
    `event_date`) is now the single source of truth for "how well is this date known"."""
    entry = TimelineEvent(event_date=date(1950, 3, 1), event_type="birth", title="x")

    assert entry.event_date == HistoricalDate(
        date=date(1950, 3, 1), precision="exact", display=None, lunar=None
    )
    assert "date_approx" not in TimelineEvent.model_fields


def test_timeline_event_accepts_an_already_built_historical_date() -> None:
    hd = HistoricalDate(date=date(1900, 1, 1), precision="circa", display="khoảng 1900", lunar=None)
    entry = TimelineEvent(event_date=hd, event_type="birth", title="x")

    assert entry.event_date == hd


# ── MarriageResponse ──────────────────────────────────────────────


def _marriage() -> Marriage:
    return Marriage(
        person1_id=uuid.uuid4(),
        person2_id=uuid.uuid4(),
        created_by_clan_id=uuid.uuid4(),
        marriage_date=date(1975, 4, 30),
        divorce_date=None,
        created_by=uuid.uuid4(),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def test_marriage_response_nests_marriage_and_divorce_date_lunar_always_none() -> None:
    resp = MarriageResponse.model_validate(_marriage())

    assert resp.marriage_date == HistoricalDate(
        date=date(1975, 4, 30), precision="exact", display=None, lunar=None
    )
    assert resp.divorce_date == HistoricalDate(
        date=None, precision="exact", display=None, lunar=None
    )


@dataclass
class _MarriageOrmRow:
    id: uuid.UUID
    person1_id: uuid.UUID
    person2_id: uuid.UUID
    created_by_clan_id: uuid.UUID
    marriage_date: date | None
    marriage_date_precision: str
    marriage_date_display: str | None
    divorce_date: date | None
    divorce_date_precision: str
    divorce_date_display: str | None
    status: str
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    marriage_place: str | None = None
    spouse_order: int | None = None
    notes: str | None = None
    updated_by: uuid.UUID | None = None
    is_deleted: bool = False
    deleted_at: datetime | None = None
    deleted_by: uuid.UUID | None = None


def test_marriage_response_reads_precision_display_from_orm_row() -> None:
    row = _MarriageOrmRow(
        id=uuid.uuid4(),
        person1_id=uuid.uuid4(),
        person2_id=uuid.uuid4(),
        created_by_clan_id=uuid.uuid4(),
        marriage_date=date(1945, 2, 10),
        marriage_date_precision="year",
        marriage_date_display="1945",
        divorce_date=date(1960, 1, 1),
        divorce_date_precision="circa",
        divorce_date_display="khoảng 1960",
        status="divorced",
        created_by=uuid.uuid4(),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    resp = MarriageResponse.model_validate(row)

    assert resp.marriage_date == HistoricalDate(
        date=date(1945, 2, 10), precision="year", display="1945", lunar=None
    )
    assert resp.divorce_date == HistoricalDate(
        date=date(1960, 1, 1), precision="circa", display="khoảng 1960", lunar=None
    )
