"""Pydantic v2 schemas for Auth requests and responses."""

import uuid
from typing import Literal, Self

from pydantic import BaseModel, EmailStr, Field, model_validator

# Slugs land in URLs and in the export Content-Disposition header (latin-1
# only), so restrict them at the door: lowercase ASCII alphanumerics and
# single hyphens, no leading/trailing hyphen.
_SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"

# ``clan_code`` (join) and ``clan_slug`` (create) are the same shape and the same
# column, ``clans.slug``, approached from opposite directions: create claims a new
# one, join names an existing one. They stay two fields because their failure modes
# are opposites -- ``auth.clan_slug_taken`` is a create error and ``clan_not_found``
# is a join error -- and one field would have to answer both.


# The four fields that name a clan on this surface. Named once so the
# "no clan action, no clan fields" rule below cannot drift from the field list.
_CLAN_FIELDS = ("clan_code", "clan_id", "clan_name", "clan_slug")


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: str = Field(..., min_length=1, max_length=255)
    # OPTIONAL since ADR-058. Omitting it registers an account with no clan
    # membership, which is what an invitee holding an invitation token has to be
    # able to do: they have no code to type and no clan to found, and
    # ``POST /invitations/{token}/accept`` requires them to be signed in already
    # (``app/api/v1/invitations.py:95-99``). The membership arrives from accept.
    clan_action: Literal["join", "create"] | None = None
    # The join identifier (ADR-057 section 2). A human-readable clan code, which is
    # the clan's slug.
    clan_code: str | None = Field(None, max_length=100, pattern=_SLUG_PATTERN)
    # DEPRECATED, accepted for one release beside ``clan_code`` -- see the
    # deprecation window in docs/contracts/rest-auth-api.md. Sending both is a
    # 422 ``auth.clan_code_and_id_both_given``, never a silent reconciliation.
    clan_id: uuid.UUID | None = None
    clan_name: str | None = Field(None, max_length=255)
    clan_slug: str | None = Field(None, max_length=100, pattern=_SLUG_PATTERN)

    @model_validator(mode="after")
    def _clan_fields_need_a_clan_action(self) -> Self:
        """A body that names a clan but no ``clan_action`` is refused.

        Without this, a client that names a clan and forgets ``clan_action``
        would silently get a clanless account instead of the membership it asked
        for -- and which clan a membership lands on is the one boundary this
        product cannot get wrong (root ``CLAUDE.md``).

        This lives in Pydantic rather than in the handler on purpose.
        ``POST /auth/register`` is non-enumerating (ADR-021), and a schema
        validator runs before the route body executes, so it cannot consult the
        identity provider and therefore cannot answer differently for a
        registered and an unregistered email. It also reuses the existing
        ``validation_error`` code instead of adding a new one to this route,
        which is the way an enumeration oracle gets built.
        """
        if self.clan_action is None:
            named = [f for f in _CLAN_FIELDS if getattr(self, f) is not None]
            if named:
                raise ValueError(
                    "clan_action is required when the body names a clan "
                    f"({', '.join(named)}); omit both to register with no clan"
                )
        return self


class AuthenticatedOnboardingRequest(BaseModel):
    # STILL REQUIRED here, unlike ``RegisterRequest`` above, and ADR-058 section 3
    # holds the reason: this route exists only to attach an already-authenticated
    # user to a clan, and its response ``RegisterResponse`` types ``clan_id`` as
    # non-optional. A clanless onboard would be a no-op that cannot answer in its
    # own response shape.
    clan_action: Literal["join", "create"]
    clan_code: str | None = Field(None, max_length=100, pattern=_SLUG_PATTERN)
    # DEPRECATED for one release, exactly as on ``RegisterRequest`` above.
    clan_id: uuid.UUID | None = None
    clan_name: str | None = Field(None, max_length=255)
    clan_slug: str | None = Field(None, max_length=100, pattern=_SLUG_PATTERN)


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
