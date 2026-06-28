"""Auth use-case handlers.

Orchestrate Supabase Auth integration and clan membership.

Architecture:
- ``SupabaseAuthService`` — DB-free, talks to Supabase Auth only.
- ``AuthCommandHandler`` — DB-bound, orchestrates registration/login.
- ``AuthQueryHandler``  — read-only profile queries.
- ``FCMTokenHandler``   — push-token registration (raw SQL).
"""

from __future__ import annotations

import uuid
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.domain.auth.repository import AuthQueryPort, AuthRepository, FCMTokenRepository
from app.domain.shared.exceptions import AuthenticationError
from app.infrastructure.supabase_client import get_anon_client, get_service_client
from app.models.clan import Clan
from app.models.user_clan_role import UserClanRole
from app.schemas.auth import (
    LoginResponse,
    RegisterResponse,
    UserProfile,
)
from app.services.translator import t


def _supabase_admin() -> Any:
    return get_service_client()


def _supabase_anon() -> Any:
    return get_anon_client()


# ── DB-free Supabase service ────────────────────────────────────


class SupabaseAuthService:
    """Pure Supabase operations that do NOT require a database session.

    This class exists so that route handlers do not need to hack
    around ``AuthCommandHandler.__new__`` to call DB-free methods.
    """

    async def refresh_token(self, *, refresh_token: str) -> dict[str, Any]:
        """Exchange a refresh token for a new access token."""
        sb = _supabase_anon()
        try:
            resp = sb.auth.refresh_session(refresh_token)
        except Exception as exc:
            raise AuthenticationError("auth.invalid_refresh_token") from exc

        if not resp.session:
            raise AuthenticationError("auth.invalid_refresh_token")

        return {
            "access_token": resp.session.access_token,
            "refresh_token": resp.session.refresh_token,
            "expires_in": resp.session.expires_in,
        }

    async def logout(self, *, access_token: str) -> None:
        """Revoke the user's Supabase session (refresh tokens).

        The stateless access token remains valid until its short expiry; this
        prevents the session from being renewed.
        """
        sb = _supabase_admin()
        try:
            sb.auth.admin.sign_out(access_token, "global")
        except Exception:
            return

    async def update_profile(
        self, *, user_sub: str, full_name: str | None, preferred_locale: str | None
    ) -> None:
        """Update user profile on Supabase Auth."""
        sb = _supabase_admin()
        update_data: dict[str, Any] = {}
        if full_name is not None:
            update_data["user_metadata"] = {"full_name": full_name}
        if preferred_locale is not None:
            update_data.setdefault("user_metadata", {})["preferred_locale"] = preferred_locale

        if update_data:
            sb.auth.admin.update_user_by_id(user_sub, update_data)


# ── DB-bound handlers ───────────────────────────────────────────


_INVALID_CREDENTIALS = "auth.invalid_credentials"


class AuthCommandHandler:
    """Handles Auth write operations."""

    def __init__(self, repo: AuthRepository, uow: Any) -> None:
        self._repo = repo
        self._uow = uow

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

            clan = Clan(name=clan_name, slug=clan_slug)
            self._repo.add_clan(clan)
            await self._uow.flush()  # INSERT the clan first so the role FK resolves

            role = UserClanRole(
                clan_id=clan.id,
                user_id=user_id,
                role="admin",
                is_approved=True,
                approved_by=user_id,
                approved_at=datetime.now(UTC),
            )
            self._repo.add_user_role(role)
            await self._uow.commit()

            return RegisterResponse(
                user_id=user_id,
                email=email,
                full_name=full_name,
                clan_id=clan.id,
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
        role = UserClanRole(clan_id=clan.id, user_id=user_id, role="viewer", is_approved=False)
        self._repo.add_user_role(role)
        await self._uow.commit()

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
        sb = _supabase_admin()
        try:
            auth_resp = sb.auth.admin.create_user(
                {"email": email, "password": password, "email_confirm": True}
            )
        except Exception as e:
            if "already" in str(e).lower():
                raise ConflictError("auth.email_already_exists") from e
            raise ValidationError("auth.registration_failed", {"detail": str(e)}) from e

        user_id = uuid.UUID(auth_resp.user.id)
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
                _supabase_admin().auth.admin.delete_user(str(user_id))
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
        """Authenticate via Supabase and return tokens + profile."""
        sb = _supabase_anon()
        try:
            auth_resp = sb.auth.sign_in_with_password({"email": email, "password": password})
        except Exception as exc:
            raise AuthenticationError(_INVALID_CREDENTIALS) from exc

        session = auth_resp.session
        if session is None:
            raise AuthenticationError(_INVALID_CREDENTIALS)
        user = auth_resp.user
        if user is None:
            raise AuthenticationError(_INVALID_CREDENTIALS)

        user_id = uuid.UUID(user.id)
        row = await self._repo.get_login_profile(user_id)

        return LoginResponse(
            access_token=session.access_token,
            refresh_token=session.refresh_token,
            expires_in=session.expires_in,
            user=UserProfile(
                id=user_id,
                email=email,
                full_name=user.user_metadata.get("full_name", ""),
                clan_id=row.UserClanRole.clan_id if row and row.UserClanRole else None,
                clan_name=row.Clan.name if row and row.Clan else None,
                role=row.UserClanRole.role
                if row and row.UserClanRole and row.UserClanRole.is_approved
                else None,
                is_approved=row.UserClanRole.is_approved if row and row.UserClanRole else False,
                person_id=row.UserProfileModel.person_id if row else None,
            ),
        )


class AuthQueryHandler:
    """Read-only handler for auth queries."""

    def __init__(self, query_port: AuthQueryPort) -> None:
        self._query_port = query_port

    async def get_profile(self, *, user_id: uuid.UUID, email: str, full_name: str) -> UserProfile:
        """Return the authenticated user's profile."""
        row = await self._query_port.get_profile(user_id)
        has_pending_membership = await self._query_port.has_pending_membership(user_id)

        return UserProfile(
            id=user_id,
            email=email,
            full_name=full_name,
            clan_id=row.UserClanRole.clan_id if row and row.UserClanRole else None,
            clan_name=row.Clan.name if row and row.Clan else None,
            role=row.UserClanRole.role if row and row.UserClanRole else None,
            is_approved=bool(row and row.UserClanRole),
            has_pending_membership=has_pending_membership,
            person_id=row.UserProfileModel.person_id if row else None,
        )


class FCMTokenHandler:
    """Handles FCM push token registration."""

    def __init__(self, repo: FCMTokenRepository) -> None:
        self._repo = repo

    async def register_token(self, *, user_id: str, token: str, device_platform: str) -> None:
        await self._repo.register_token(user_id, token, device_platform)

    async def remove_token(self, *, user_id: str, token: str) -> None:
        await self._repo.remove_token(user_id, token)
