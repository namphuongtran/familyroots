"""Auth use-case handlers.

Orchestrate identity-provider integration (via the IdentityProvider port) and
clan membership.

Architecture:
- ``AuthSessionService`` — DB-free; refresh/logout/profile via the IdentityProvider port.
- ``AuthCommandHandler`` — DB-bound, orchestrates registration/login.
- ``AuthQueryHandler``  — read-only profile queries.
- ``FCMTokenHandler``   — push-token registration (raw SQL).
"""

from __future__ import annotations

import uuid
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

from app.application.shared.audit import emit_audit_event
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.domain.auth.identity_provider import (
    IdentityAuthError,
    IdentityError,
    IdentityProvider,
    IdentityUnavailableError,
    IdentityUserExistsError,
)
from app.domain.auth.repository import AuthQueryPort, AuthRepository, FCMTokenRepository
from app.domain.shared.exceptions import AuthenticationError
from app.domain.shared.unit_of_work import UnitOfWork
from app.domain.shared.value_objects import ActorInfo
from app.schemas.auth import (
    LoginResponse,
    RegisterResponse,
    UserProfile,
)
from app.services.translator import t

# ── DB-free auth-session service ────────────────────────────────


class AuthSessionService:
    """Auth operations that do NOT require a database session — refresh, logout,
    profile metadata. Depends only on the IdentityProvider port (no SDK import)."""

    def __init__(self, identity: IdentityProvider) -> None:
        self._identity = identity

    async def refresh_token(self, *, refresh_token: str) -> dict[str, Any]:
        """Exchange a refresh token for a new access token."""
        try:
            tokens = await self._identity.refresh(refresh_token=refresh_token)
        except IdentityAuthError as exc:
            raise AuthenticationError("auth.invalid_refresh_token") from exc
        return {
            "access_token": tokens.access_token,
            "refresh_token": tokens.refresh_token,
            "expires_in": tokens.expires_in,
        }

    async def logout(self, *, access_token: str) -> None:
        """Revoke the user's session (best-effort; the stateless access token
        remains valid until its short expiry)."""
        await self._identity.sign_out(access_token=access_token)

    async def update_profile(
        self, *, user_sub: str, full_name: str | None, preferred_locale: str | None
    ) -> None:
        """Update provider-side user metadata."""
        await self._identity.update_user(
            user_id=user_sub, full_name=full_name, preferred_locale=preferred_locale
        )


# ── DB-bound handlers ───────────────────────────────────────────


_INVALID_CREDENTIALS = "auth.invalid_credentials"


class AuthCommandHandler:
    """Handles Auth write operations.

    Loads/persists via ``repo`` + ``uow``; projection reads (the login profile)
    go through the ``query_port`` — the CQRS seam rule."""

    def __init__(
        self,
        repo: AuthRepository,
        uow: UnitOfWork,
        identity: IdentityProvider,
        query_port: AuthQueryPort,
    ) -> None:
        self._repo = repo
        self._uow = uow
        self._identity = identity
        self._query_port = query_port

    async def _assign_clan_membership(
        self,
        *,
        user_id: uuid.UUID,
        email: str,
        full_name: str,
        clan_action: str,
        clan_id: uuid.UUID | None = None,
        clan_name: str | None = None,
        clan_slug: str | None = None,
    ) -> RegisterResponse:
        if clan_action == "join" and not clan_id:
            raise ValidationError("auth.clan_id_required_for_join")
        if clan_action == "create" and (not clan_name or not clan_slug):
            raise ValidationError("auth.clan_name_required_for_create")

        if clan_action == "create":
            existing = await self._repo.get_clan_by_slug(clan_slug)
            if existing:
                raise ConflictError("auth.clan_slug_taken")

            await self._repo.ensure_profile(user_id, email, full_name)

            new_clan_id = await self._repo.create_clan(name=clan_name, slug=clan_slug)
            self._repo.add_membership(
                clan_id=new_clan_id,
                user_id=user_id,
                role="admin",
                is_approved=True,
                approved_by=user_id,
                approved_at=datetime.now(UTC),
            )
            # Audit clan creation + self-granted admin (commits clan + role + audit
            # in one transaction).
            await emit_audit_event(
                self._uow,
                action="clan.create",
                resource_type="clan",
                resource_id=new_clan_id,
                actor=ActorInfo(user_id=user_id, role="admin"),
                clan_id=new_clan_id,
                new_value={"clan_name": clan_name, "clan_slug": clan_slug, "role": "admin"},
            )

            return RegisterResponse(
                user_id=user_id,
                email=email,
                full_name=full_name,
                clan_id=new_clan_id,
                is_approved=True,
                message=t("auth.clan_created"),
            )

        clan_or_none = await self._repo.get_clan_by_id(clan_id)
        if not clan_or_none:
            raise NotFoundError("clan_not_found")
        clan = clan_or_none

        existing_role = await self._repo.get_user_role(user_id, clan.id)
        if existing_role:
            if existing_role.is_approved:
                raise ConflictError("auth.already_joined_clan")
            raise ConflictError("auth.membership_already_pending")

        await self._repo.ensure_profile(user_id, email, full_name)
        self._repo.add_membership(
            clan_id=clan.id, user_id=user_id, role="viewer", is_approved=False
        )
        # Audit the pending join request (role grant is not yet approved).
        await emit_audit_event(
            self._uow,
            action="clan.join_request",
            resource_type="user_clan_role",
            resource_id=clan.id,
            actor=ActorInfo(user_id=user_id, role="viewer"),
            clan_id=clan.id,
            new_value={"role": "viewer", "is_approved": False},
        )

        return RegisterResponse(
            user_id=user_id,
            email=email,
            full_name=full_name,
            clan_id=clan.id,
            is_approved=False,
            message=t("auth.registration_pending"),
        )

    async def register(
        self,
        *,
        email: str,
        password: str,
        full_name: str,
        clan_action: str,
        clan_id: uuid.UUID | None = None,
        clan_name: str | None = None,
        clan_slug: str | None = None,
    ) -> RegisterResponse:
        """Register a new user — create or join a clan."""
        try:
            user_id_str = await self._identity.create_user(email=email, password=password)
        except IdentityUserExistsError as e:
            raise ConflictError("auth.email_already_exists") from e
        except IdentityUnavailableError:
            # Provider outage/misconfiguration is not a validation failure — let the
            # dedicated 503 handler surface it truthfully.
            raise
        except IdentityError as e:
            raise ValidationError("auth.registration_failed", {"detail": str(e)}) from e

        user_id = uuid.UUID(user_id_str)
        try:
            return await self._assign_clan_membership(
                user_id=user_id,
                email=email,
                full_name=full_name,
                clan_action=clan_action,
                clan_id=clan_id,
                clan_name=clan_name,
                clan_slug=clan_slug,
            )
        except Exception:
            # Compensate: the Supabase auth user exists but the DB membership
            # failed — delete the orphan so the email can be reused.
            # Registration is all-or-nothing: any failure rolls back the just-created
            # auth user so the email can be reused on retry.
            with suppress(Exception):
                await self._identity.delete_user(str(user_id))
            raise

    async def onboard_authenticated_user(
        self,
        *,
        user_id: uuid.UUID,
        email: str,
        full_name: str,
        clan_action: str,
        clan_id: uuid.UUID | None = None,
        clan_name: str | None = None,
        clan_slug: str | None = None,
    ) -> RegisterResponse:
        """Attach the current authenticated user to a clan without creating a new Supabase user."""
        return await self._assign_clan_membership(
            user_id=user_id,
            email=email,
            full_name=full_name,
            clan_action=clan_action,
            clan_id=clan_id,
            clan_name=clan_name,
            clan_slug=clan_slug,
        )

    async def login(self, *, email: str, password: str) -> LoginResponse:
        """Authenticate via the identity provider and return tokens + profile."""
        try:
            identity = await self._identity.sign_in(email=email, password=password)
        except IdentityAuthError as exc:
            raise AuthenticationError(_INVALID_CREDENTIALS) from exc

        user_id = uuid.UUID(identity.user_id)
        view = await self._query_port.get_login_profile(user_id)

        return LoginResponse(
            access_token=identity.tokens.access_token,
            refresh_token=identity.tokens.refresh_token,
            expires_in=identity.tokens.expires_in,
            user=UserProfile(
                id=user_id,
                email=email,
                full_name=identity.full_name,
                clan_id=view.clan_id if view else None,
                clan_name=view.clan_name if view else None,
                # A pending membership carries a role but grants nothing yet.
                role=view.role if view and view.is_approved else None,
                is_approved=view.is_approved if view else False,
                person_id=view.person_id if view else None,
            ),
        )


class AuthQueryHandler:
    """Read-only handler for auth queries."""

    def __init__(self, query_port: AuthQueryPort) -> None:
        self._query_port = query_port

    async def get_profile(self, *, user_id: uuid.UUID, email: str, full_name: str) -> UserProfile:
        """Return the authenticated user's profile."""
        # get_profile joins approved memberships only, so a membership present in
        # the view is by definition approved.
        view = await self._query_port.get_profile(user_id)
        has_pending_membership = await self._query_port.has_pending_membership(user_id)

        return UserProfile(
            id=user_id,
            email=email,
            full_name=full_name,
            clan_id=view.clan_id if view else None,
            clan_name=view.clan_name if view else None,
            role=view.role if view else None,
            is_approved=view.is_approved if view else False,
            has_pending_membership=has_pending_membership,
            person_id=view.person_id if view else None,
        )


class FCMTokenHandler:
    """Handles FCM push token registration.

    Writes commit through the UoW like every other command handler — device
    tokens emit no domain events, but the commit discipline is what guarantees
    the write survives the request (C1, seam-review-2026-07-04)."""

    def __init__(self, repo: FCMTokenRepository, uow: UnitOfWork) -> None:
        self._repo = repo
        self._uow = uow

    async def register_token(self, *, user_id: str, token: str, device_platform: str) -> None:
        await self._repo.register_token(user_id, token, device_platform)
        await self._uow.commit()

    async def remove_token(self, *, user_id: str, token: str) -> None:
        await self._repo.remove_token(user_id, token)
        await self._uow.commit()
