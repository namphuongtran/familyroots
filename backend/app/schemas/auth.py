"""Pydantic v2 schemas for Auth requests and responses."""

import uuid
from typing import Annotated, Any, Literal

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.core.exceptions import ValidationError
from app.domain.auth.platform_role import PlatformRole

# Slugs land in URLs and in the export Content-Disposition header (latin-1
# only), so restrict them at the door: lowercase ASCII alphanumerics and
# single hyphens, no leading/trailing hyphen.
#
# And at least two characters, the ``min_length`` in ``_ClanCode`` below, because
# the database has never held a shorter code: ``ck_clans_clans_slug_format``
# refused one from migration 001 on, and since migration 040 it enforces this
# whole shape (#190). Without the minimum, a one-character create code reached
# ``create_user`` and then broke the CHECK, so a fresh email got a 500 where an
# existing one got a 201 -- the ADR-021 oracle. The minimum stays a length beside
# the pattern rather than folded into it, so this text remains the pattern
# ADR-057, the contract, the web and the CHECK all quote.
_SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"

# ``clan_code`` (join) and ``clan_slug`` (create) are the same shape and the same
# column, ``clans.slug``, approached from opposite directions: create claims a new
# one, join names an existing one. They stay two fields because their failure modes
# are opposites -- ``auth.clan_slug_taken`` is a create error and ``clan_not_found``
# is a join error -- and one field would have to answer both.
#
# That one shape is declared once, here, and all four fields on the two request
# bodies below carry it, so the join field and the create field cannot drift apart.
_ClanCode = Annotated[str, Field(min_length=2, max_length=100, pattern=_SLUG_PATTERN)]


# The fields that name a clan. ``POST /auth/register`` refuses all of them (ADR-075
# amendment): a clan is created or joined only in onboarding, after the email is
# confirmed. The set is named once so the refusal cannot drift from the field list.
_CLAN_FIELDS = ("clan_action", "clan_code", "clan_id", "clan_name", "clan_slug")


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: str = Field(..., min_length=1, max_length=255)

    @model_validator(mode="before")
    @classmethod
    def _refuse_clan_fields(cls, data: Any) -> Any:
        """A body carrying any clan field is a 422 ``auth.register_names_no_clan``.

        Refused rather than ignored: a client that names a clan and gets a clanless
        account would believe it holds a membership it does not, and which clan a
        membership lands on is the one boundary this product cannot get wrong.

        This lives in the schema, so it runs before the route body and cannot
        consult the identity provider: it answers identically for a registered and
        an unregistered email (ADR-021). An ``AppError`` is not a ``ValueError``,
        so Pydantic lets it through to the application error handler, which is how
        the code reaches the client instead of the generic ``validation_error``.
        """
        if isinstance(data, dict):
            named = [f for f in _CLAN_FIELDS if f in data]
            if named:
                raise ValidationError("auth.register_names_no_clan", {"fields": named})
        return data


class AuthenticatedOnboardingRequest(BaseModel):
    # STILL REQUIRED here, unlike ``RegisterRequest`` above, and ADR-058 section 3
    # holds the reason: this route exists only to attach an already-authenticated
    # user to a clan, and its response ``RegisterResponse`` types ``clan_id`` as
    # non-optional. A clanless onboard would be a no-op that cannot answer in its
    # own response shape.
    clan_action: Literal["join", "create"]
    clan_code: _ClanCode | None = None
    # DEPRECATED for one release, exactly as on ``RegisterRequest`` above.
    clan_id: uuid.UUID | None = None
    clan_name: str | None = Field(None, max_length=255)
    clan_slug: _ClanCode | None = None


class RegisterResponse(BaseModel):
    """Onboard-only now (ADR-021): POST /auth/register is non-enumerating and
    returns a uniform ``{"message": ...}`` body built by the route, not this
    schema. POST /auth/onboard (already-authenticated users attaching to a
    clan) still returns this full shape via ``_assign_clan_membership``."""

    user_id: uuid.UUID
    email: str
    full_name: str
    clan_id: uuid.UUID
    is_approved: bool
    message: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserProfile(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    clan_id: uuid.UUID | None = None
    clan_name: str | None = None
    role: str | None = None
    is_approved: bool = False
    has_pending_membership: bool = False
    person_id: uuid.UUID | None = None
    preferred_locale: str = "vi"
    platform_role: PlatformRole


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    user: UserProfile


class UserUpdateRequest(BaseModel):
    full_name: str | None = Field(None, min_length=1, max_length=255)
    preferred_locale: str | None = Field(None, pattern="^(vi|en|zh|fr)$")


class FCMTokenRequest(BaseModel):
    token: str = Field(..., max_length=500)
    device_platform: Literal["android", "ios", "web"]


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenRefreshResponse(BaseModel):
    """POST /auth/refresh — a refreshed token pair (no user profile)."""

    access_token: str
    refresh_token: str
    expires_in: int


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResendVerificationRequest(BaseModel):
    email: EmailStr
