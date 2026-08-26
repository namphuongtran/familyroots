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

import logging
import uuid
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

from app.application.shared.audit import emit_audit_event
from app.domain.auth.identity_provider import (
    IdentityAuthError,
    IdentityError,
    IdentityProvider,
    IdentityUnavailableError,
    IdentityUserExistsError,
    IdentityWeakPasswordError,
)
from app.domain.auth.repository import AuthQueryPort, AuthRepository, FCMTokenRepository
from app.domain.shared.exceptions import (
    AuthenticationError,
    ConflictError,
    EntityNotFoundError,
    ForbiddenError,
    ValidationError,
)
from app.domain.shared.unit_of_work import UnitOfWork
from app.domain.shared.value_objects import ActorInfo
from app.schemas.auth import (
    LoginResponse,
    RegisterResponse,
    UserProfile,
)
from app.services.translator import t

logger = logging.getLogger(__name__)

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

    async def send_password_reset(self, *, email: str) -> None:
        """Trigger a provider password-reset email (best-effort)."""
        await self._identity.send_password_reset(email=email)

    async def send_verification_email(self, *, email: str) -> None:
        """Trigger a provider email-verification (best-effort)."""
        await self._identity.send_verification_email(email=email)


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

    async def _resolve_join_target(
        self, *, clan_code: str | None, clan_id: uuid.UUID | None
    ) -> Any:
        """Resolve the clan a join request names, by code or by the deprecated id.

        ADR-057 section 2 made the typed join identifier the clan **code**, which is
        the clan's ``slug``, resolved through the ``get_clan_by_slug`` lookup that
        already existed at every layer. ``clan_id`` is still accepted for one
        release; ``docs/contracts/rest-auth-api.md`` owns that window and the reason
        for it.

        Two identifiers that can disagree are never reconciled here. A request
        carrying both is refused, because picking one silently would let a caller
        name clan A and join clan B -- and which clan a membership lands on is the
        one boundary this product cannot get wrong.

        ``auth.clan_id_required_for_join`` keeps its historical name for the
        neither-was-supplied case: spec section 7.1b names that code and
        ``docs/contracts/error-codes.md`` documents it, so renaming it would be a
        second breaking change for no gain.
        """
        if clan_code and clan_id:
            raise ValidationError("auth.clan_code_and_id_both_given")
        if clan_code:
            clan = await self._repo.get_clan_by_slug(clan_code)
        elif clan_id:
            clan = await self._repo.get_clan_by_id(clan_id)
        else:
            raise ValidationError("auth.clan_id_required_for_join")
        if not clan:
            raise EntityNotFoundError("clan_not_found")
        return clan

    async def _provision_clanless_account(
        self, *, user_id: uuid.UUID, email: str, full_name: str
    ) -> None:
        """Provision the local profile for an account that joins no clan (ADR-058).

        The whole write is one ``user_profiles`` row. The name matters: it is the
        only place the name typed at registration is kept. ``create_user`` on the
        identity port takes ``email`` and ``password`` only
        (``app/domain/auth/identity_provider.py``), so nothing carries
        ``full_name`` to the provider, and ``ensure_profile_row`` is
        ``ON CONFLICT DO NOTHING`` on the primary key -- so the row written here
        survives the later ``ensure_profile`` call inside invitation accept
        (``app/application/invitation/handlers.py:93``), which only has the JWT's
        (empty) ``user_metadata.full_name`` to offer.

        **No domain event is emitted, and that is deliberate.** Two reasons, both
        read at source on 2026-08-26. First, ``ensure_profile`` is audited nowhere
        else either: the create path of ``_assign_clan_membership`` audits
        ``clan.create`` and its join path audits ``clan.join_request`` -- both are
        about the clan, and this account has none. Second, ``audit_logs.clan_id`` is
        nullable (``app/models/audit_log.py:37-39``) but every reader of that
        table is clan-keyed -- the policy ``audit_logs_sel USING (clan_id = <GUC>)``
        (ADR-043) and the application-layer filter -- so a NULL-clan row would be
        written and never read by anything except the super-admin log. Adding a
        row nobody can read is the ``clan_settings`` mistake in miniature
        (ADR-054): a write guarded for a reader that cannot arrive.

        The commit still goes through the Unit of Work, which is the rule that is
        not relaxed. ``FCMTokenHandler.register_token`` below is the standing
        precedent for a UoW commit with no event.
        """
        await self._repo.ensure_profile(user_id, email, full_name)
        await self._uow.commit()

    async def _assign_clan_membership(
        self,
        *,
        user_id: uuid.UUID,
        email: str,
        full_name: str,
        clan_action: str,
        clan_code: str | None = None,
        clan_id: uuid.UUID | None = None,
        clan_name: str | None = None,
        clan_slug: str | None = None,
    ) -> RegisterResponse:
        if clan_action == "create" and (not clan_name or not clan_slug):
            raise ValidationError("auth.clan_name_required_for_create")

        if clan_action == "create":
            # Guaranteed non-None by the validation above; assert so the str-typed repo
            # call is provably safe (auth.handlers currently has arg-type disabled).
            assert clan_name is not None and clan_slug is not None
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

        clan = await self._resolve_join_target(clan_code=clan_code, clan_id=clan_id)

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
        clan_action: str | None = None,
        clan_code: str | None = None,
        clan_id: uuid.UUID | None = None,
        clan_name: str | None = None,
        clan_slug: str | None = None,
    ) -> None:
        """Register a new user — create a clan, join a clan, or neither.

        ``clan_action=None`` is the third case, added by ADR-058: the account is
        created with **no clan membership at all**. It exists for the invitee in
        ADR-057's primary join path. That person holds an invitation token, has no
        clan code to type and no clan to found, and
        ``POST /invitations/{token}/accept`` requires them to be signed in first
        (``app/api/v1/invitations.py:95-99``) — so without this case the
        invitation flow has no reachable first step. The membership arrives from
        accept, on the session ADR-048 put it on.

        Clan-INPUT validation runs unconditionally, before ``create_user``, so a
        bad clan_code/clan_slug fails identically whether or not the email already
        has an account (ADR-021 non-enumeration). Without this, an existing email
        short-circuits before ever reaching ``_assign_clan_membership``'s checks
        while a fresh email hits them — a status-code oracle for account
        enumeration. The join half of that validation is ``_resolve_join_target``,
        the same method ``_assign_clan_membership`` uses, so the two cannot drift
        apart the way two hand-copied checks could; the resolution is deliberately
        run twice rather than carried, because the row must be re-read on the
        session that will write the membership.

        The ``clan_action=None`` case does not weaken that property, because it
        adds **no** error code and no branch that can answer differently for a
        registered and an unregistered email: it validates nothing, so both emails
        reach ``create_user`` and both get the same 201. The one body that could
        have leaked — a clan named with no ``clan_action`` — is refused by
        ``RegisterRequest``'s own validator, before this method runs and before the
        identity provider is touched at all.
        """
        if clan_action == "create" and (not clan_name or not clan_slug):
            raise ValidationError("auth.clan_name_required_for_create")

        if clan_action == "create":
            # Guaranteed non-None by the validation above.
            assert clan_name is not None and clan_slug is not None
            existing_clan = await self._repo.get_clan_by_slug(clan_slug)
            if existing_clan:
                raise ConflictError("auth.clan_slug_taken")
        elif clan_action == "join":
            await self._resolve_join_target(clan_code=clan_code, clan_id=clan_id)
        # clan_action is None: nothing to validate. RegisterRequest has already
        # refused any body that names a clan without naming an action.

        try:
            user_id_str = await self._identity.create_user(email=email, password=password)
        except IdentityUserExistsError:
            # Non-enumerating register (ADR-021): an existing account gets a silent
            # recovery-email nudge; the caller sees the same 201 as a fresh signup.
            try:
                await self._identity.send_password_reset(email=email)
            except Exception:  # nudge is best-effort by design
                logger.warning("register nudge: password-reset send failed", exc_info=True)
            return
        except IdentityUnavailableError:
            # Provider outage/misconfiguration is not a validation failure — let the
            # dedicated 503 handler surface it truthfully.
            raise
        except IdentityWeakPasswordError as e:
            # Provider rejected the password as too weak — a client error (422) with a
            # specific message, not the generic registration_failed.
            raise ValidationError("auth.password_too_weak", {"detail": str(e)}) from e
        except IdentityError as e:
            raise ValidationError("auth.registration_failed", {"detail": str(e)}) from e

        user_id = uuid.UUID(user_id_str)
        try:
            if clan_action is None:
                await self._provision_clanless_account(
                    user_id=user_id, email=email, full_name=full_name
                )
            else:
                await self._assign_clan_membership(
                    user_id=user_id,
                    email=email,
                    full_name=full_name,
                    clan_action=clan_action,
                    clan_code=clan_code,
                    clan_id=clan_id,
                    clan_name=clan_name,
                    clan_slug=clan_slug,
                )
        except Exception:
            # Compensate: the auth user exists but DB membership failed — delete the
            # orphan so the email can be reused. No verification email was sent.
            with suppress(Exception):
                await self._identity.delete_user(str(user_id))
            raise

        # Registration succeeded — send the email-verification link best-effort. A
        # transient SMTP failure must not fail the registration; the user can
        # re-trigger via POST /auth/resend-verification.
        with suppress(Exception):
            await self._identity.send_verification_email(email=email)

    async def onboard_authenticated_user(
        self,
        *,
        user_id: uuid.UUID,
        email: str,
        full_name: str,
        clan_action: str,
        clan_code: str | None = None,
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
            clan_code=clan_code,
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

        # H1 chokepoint parity: login returns fresh tokens plus profile/clan data —
        # a deactivated account gets neither. Only an explicit False blocks (a
        # missing profile row is a brand-new account). /auth/refresh is intentionally
        # NOT gated: AuthSessionService is DB-free by design and refreshed tokens are
        # inert against the API (get_current_user 403s every authenticated request).
        if await self._query_port.is_account_active(user_id) is False:
            raise ForbiddenError("account_deactivated")

        view = await self._query_port.get_login_profile(user_id)
        # Same source /auth/me uses — login and /me must agree for the same user.
        has_pending_membership = await self._query_port.has_pending_membership(user_id)

        return LoginResponse(
            access_token=identity.tokens.access_token,
            refresh_token=identity.tokens.refresh_token,
            expires_in=identity.tokens.expires_in,
            user=UserProfile(
                id=user_id,
                email=email,
                full_name=identity.full_name,
                preferred_locale=identity.preferred_locale or "vi",
                clan_id=view.clan_id if view else None,
                clan_name=view.clan_name if view else None,
                # A pending membership carries a role but grants nothing yet.
                role=view.role if view and view.is_approved else None,
                is_approved=view.is_approved if view else False,
                has_pending_membership=has_pending_membership,
                person_id=view.person_id if view else None,
            ),
        )


class AuthQueryHandler:
    """Read-only handler for auth queries."""

    def __init__(self, query_port: AuthQueryPort) -> None:
        self._query_port = query_port

    async def get_profile(
        self,
        *,
        user_id: uuid.UUID,
        email: str,
        full_name: str,
        preferred_locale: str | None = None,
    ) -> UserProfile:
        """Return the authenticated user's profile."""
        # get_profile joins approved memberships only, so a membership present in
        # the view is by definition approved.
        view = await self._query_port.get_profile(user_id)
        has_pending_membership = await self._query_port.has_pending_membership(user_id)

        return UserProfile(
            id=user_id,
            email=email,
            full_name=full_name,
            preferred_locale=preferred_locale or "vi",
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
