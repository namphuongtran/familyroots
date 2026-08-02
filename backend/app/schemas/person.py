"""Pydantic v2 schemas for Person requests and responses."""

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.historical_date import HistoricalDate, coerce_response_dates

_PERSON_DATE_FIELDS = {"birth_date": "lunar_birth_date", "death_date": "lunar_death_date"}

# ADR-036: avatar_url is server-managed. It is declared on the write schemas (so the
# rejection is discoverable in OpenAPI and the 422 names the offending field) but
# `exclude=True` keeps it out of model_dump(), so it can never reach a command DTO.
_AVATAR_URL_REJECTED = (
    "avatar_url is server-managed and cannot be set directly. "
    "Use PATCH /documents/{document_id}/set-avatar, which publishes the image to the "
    "public avatars bucket and stamps the resulting permanent URL."
)
_AVATAR_URL_FIELD = Field(
    None,
    max_length=500,
    exclude=True,
    description=f"Read-only. {_AVATAR_URL_REJECTED}",
)


class PersonCreateRequest(BaseModel):
    """Request body for creating a new person."""

    full_name: str = Field(..., min_length=1, max_length=255)
    birth_name: str | None = Field(None, max_length=255)
    courtesy_name: str | None = Field(None, max_length=255)
    posthumous_name: str | None = Field(None, max_length=255)
    alias_name: str | None = Field(None, max_length=255)
    gender: str = Field("unknown", pattern="^(male|female|unknown)$")

    birth_date: date | None = None
    birth_date_precision: str = Field("exact", pattern="^(exact|year|month|circa|unknown)$")
    birth_date_display: str | None = None
    death_date: date | None = None
    death_date_precision: str = Field("exact", pattern="^(exact|year|month|circa|unknown)$")
    death_date_display: str | None = None
    lunar_birth_date: str | None = Field(None, max_length=30)
    lunar_death_date: str | None = Field(None, max_length=30)

    birth_place: str | None = Field(None, max_length=255)
    death_place: str | None = Field(None, max_length=255)
    burial_place: str | None = Field(None, max_length=255)
    tomb_location: str | None = Field(None, max_length=500)
    residence_place: str | None = Field(None, max_length=255)

    religion: str | None = Field(None, max_length=100)
    nationality: str = Field("VN", max_length=100)
    occupation: str | None = Field(None, max_length=255)
    education_level: str | None = Field(None, max_length=255)
    title_rank: str | None = Field(None, max_length=255)
    phone: str | None = Field(None, max_length=50)
    email: str | None = Field(None, max_length=255)

    biography: str | None = None
    avatar_url: str | None = _AVATAR_URL_FIELD
    notes: str | None = None

    @field_validator("avatar_url")
    @classmethod
    def _reject_client_avatar_url(cls, value: str | None) -> str | None:
        raise ValueError(_AVATAR_URL_REJECTED)

    # created_by_clan_id is provenance, not client-settable: the handler always
    # stamps it from the active clan (X-Current-Clan-Id). Accepting it from the
    # body let a caller assign a person to an arbitrary clan.
    #
    # The death_date >= birth_date cross-field invariant is enforced in the Person
    # DOMAIN entity (single source of truth → consistent error and coverage of partial
    # PATCH updates the schema can't see); the schema only validates individual fields.


class PersonChangeFields(BaseModel):
    """Every client-settable person field, all optional — the shape of an edit.

    Shared by ``PersonUpdateRequest`` (which adds the required OCC token) and by the
    change-request payload, so a proposed edit is validated and normalized by exactly
    the same field definitions as a direct PATCH. Keeping one declaration is the
    point: a field added here is immediately proposable and immediately updatable,
    with identical bounds, rather than drifting between two copies.
    """

    full_name: str | None = Field(None, min_length=1, max_length=255)
    birth_name: str | None = Field(None, max_length=255)
    courtesy_name: str | None = Field(None, max_length=255)
    posthumous_name: str | None = Field(None, max_length=255)
    alias_name: str | None = Field(None, max_length=255)
    gender: str | None = Field(None, pattern="^(male|female|unknown)$")

    birth_date: date | None = None
    birth_date_precision: str | None = Field(None, pattern="^(exact|year|month|circa|unknown)$")
    birth_date_display: str | None = None
    death_date: date | None = None
    death_date_precision: str | None = Field(None, pattern="^(exact|year|month|circa|unknown)$")
    death_date_display: str | None = None
    lunar_birth_date: str | None = Field(None, max_length=30)
    lunar_death_date: str | None = Field(None, max_length=30)

    birth_place: str | None = Field(None, max_length=255)
    death_place: str | None = Field(None, max_length=255)
    burial_place: str | None = Field(None, max_length=255)
    tomb_location: str | None = Field(None, max_length=500)
    residence_place: str | None = Field(None, max_length=255)

    religion: str | None = Field(None, max_length=100)
    nationality: str | None = Field(None, max_length=100)
    occupation: str | None = Field(None, max_length=255)
    education_level: str | None = Field(None, max_length=255)
    title_rank: str | None = Field(None, max_length=255)
    phone: str | None = Field(None, max_length=50)
    email: str | None = Field(None, max_length=255)

    biography: str | None = None
    avatar_url: str | None = _AVATAR_URL_FIELD
    notes: str | None = None

    @field_validator("avatar_url")
    @classmethod
    def _reject_client_avatar_url(cls, value: str | None) -> str | None:
        # Fires only when the client actually sends the key (Pydantic does not run
        # field validators for unset defaults), so an ordinary PATCH is unaffected
        # and a PATCH that tries to write an avatar gets a 422 naming the field —
        # rather than the pre-ADR-036 behaviour of accepting a URL nothing maintains.
        #
        # Living on PersonChangeFields rather than on PersonUpdateRequest is
        # deliberate: the change-request payload validates against the same base, so
        # ADR-036's rejection covers a proposed edit too, with no second rule to keep
        # in step.
        raise ValueError(_AVATAR_URL_REJECTED)

    # created_by_clan_id is provenance and is NOT settable here — reassigning it
    # would transfer claim-review control of the person to another clan.
    # (death_date >= birth_date is enforced in the Person domain entity — see the note
    # on PersonCreateRequest.)


class PersonUpdateRequest(PersonChangeFields):
    """Request body for updating a person. All content fields optional."""

    # Optimistic concurrency (ADR-017): required so a stale client can't silently
    # clobber a concurrent edit. The route pops this out of `changes` before it
    # reaches the aggregate — it is never itself a client-updatable field.
    expected_version: int = Field(..., ge=1)


class PersonBatchGetRequest(BaseModel):
    """Request body for fetching multiple persons in one read operation."""

    ids: list[uuid.UUID] = Field(..., min_length=1, max_length=100)
    profile: str = Field("full", pattern="^(summary|detail|full)$")
    include: str | None = Field(
        None,
        description=(
            "Global comma-separated embedded resources. "
            "Supported: stats,marriages,parent_child,timeline,documents"
        ),
    )
    fields: str | None = Field(
        None,
        description="Comma-separated sparse fields. Example: id,full_name,stats",
    )
    include_by_id: dict[uuid.UUID, str] | None = Field(
        None,
        description=(
            "Per-person embedded resources keyed by person id. "
            "Values are comma-separated include tokens with same support as include."
        ),
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "ids": [
                        "11111111-1111-1111-1111-111111111111",
                        "22222222-2222-2222-2222-222222222222",
                    ],
                    "profile": "summary",
                    "include": "stats",
                    "fields": "id,full_name,stats",
                    "include_by_id": {
                        "11111111-1111-1111-1111-111111111111": "marriages,parent_child"
                    },
                }
            ]
        }
    }


class PersonResponse(BaseModel):
    """Response schema for a single person."""

    id: uuid.UUID
    created_by_clan_id: uuid.UUID | None = None

    full_name: str
    birth_name: str | None = None
    courtesy_name: str | None = None
    posthumous_name: str | None = None
    alias_name: str | None = None
    gender: str

    birth_date: HistoricalDate = Field(default_factory=HistoricalDate)
    death_date: HistoricalDate = Field(default_factory=HistoricalDate)

    birth_place: str | None = None
    death_place: str | None = None
    burial_place: str | None = None
    tomb_location: str | None = None
    residence_place: str | None = None

    religion: str | None = None
    nationality: str
    occupation: str | None = None
    education_level: str | None = None
    title_rank: str | None = None
    phone: str | None = None
    email: str | None = None

    biography: str | None = None
    avatar_url: str | None = None
    notes: str | None = None

    is_deleted: bool
    created_by: uuid.UUID
    updated_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    # Optimistic concurrency (ADR-017). Default shields legacy dict read-paths;
    # entity/ORM-backed responses always carry the real stored value.
    version: int = 1

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def _nest_dates(cls, data: Any) -> Any:
        return coerce_response_dates(cls, data, _PERSON_DATE_FIELDS)


class PersonMini(BaseModel):
    """Minimal representation of a person for embedded relationships."""

    id: uuid.UUID
    full_name: str
    gender: str
    avatar_url: str | None = None
    birth_date: HistoricalDate = Field(default_factory=HistoricalDate)
    death_date: HistoricalDate = Field(default_factory=HistoricalDate)

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def _nest_dates(cls, data: Any) -> Any:
        return coerce_response_dates(cls, data, _PERSON_DATE_FIELDS)


class PersonSummary(BaseModel):
    """Summary profile for list views."""

    id: uuid.UUID
    full_name: str
    gender: str
    avatar_url: str | None = None
    birth_date: HistoricalDate = Field(default_factory=HistoricalDate)
    death_date: HistoricalDate = Field(default_factory=HistoricalDate)
    # NOTE: no generation/is_founder/membership_role here — list/get serialize
    # from PersonResponse, which carries no membership data, and đời is
    # graph-computed on tree endpoints (clan_memberships.generation is a
    # deprecated display source). Search's payload carries them separately.
    # Optimistic concurrency (ADR-017); see PersonResponse.version.
    version: int = 1

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def _nest_dates(cls, data: Any) -> Any:
        return coerce_response_dates(cls, data, _PERSON_DATE_FIELDS)


class PersonDetail(PersonSummary):
    """Detailed profile with most biographical data, but without audit fields."""

    birth_name: str | None = None
    birth_place: str | None = None
    death_place: str | None = None
    occupation: str | None = None
    religion: str | None = None
    notes: str | None = None


class PersonStats(BaseModel):
    """Additional statistics for a person."""

    spouse_count: int
    child_count: int


class PersonDetailComposite(PersonResponse):
    """Includes optional sub-resources when requested via ?include="""

    marriages: list[Any] | None = None
    parent_child: list[Any] | None = None
    timeline: list[Any] | None = None
    documents: list[Any] | None = None


class PersonSearchResult(BaseModel):
    """One row of GET /persons/search (a lean, search-specific person projection)."""

    id: str
    full_name: str
    gender: str
    birth_date: HistoricalDate
    avatar_url: str | None = None
    version: int
    generation: int | None = None
    membership_role: str | None = None
    is_founder: bool


class BatchError(BaseModel):
    """One per-id failure in a batch fetch."""

    id: str
    code: str


class PersonBatchMeta(BaseModel):
    """meta for POST /persons/batch — the sanctioned `errors` adjunct (CLAUDE.md)."""

    errors: list[BatchError] = []


class PersonBatchEnvelope(BaseModel):
    """POST /persons/batch: {data: [<person>], meta: {errors: [...]}}.

    `data` items are the same dynamic person projection as GET /persons/{id}
    (documented as the full PersonResponse; sparse `fields=`/`include=` are subsets).
    """

    data: list[PersonResponse]
    meta: PersonBatchMeta
