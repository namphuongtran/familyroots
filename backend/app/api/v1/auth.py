"""Auth API routes — register, login, logout, refresh, profile, FCM tokens."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from supabase import create_client

from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.security import get_current_user
from app.models.clan import Clan
from app.models.user_clan_role import UserClanRole
from app.schemas.auth import (
    FCMTokenRequest,
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    UserProfile,
    UserUpdateRequest,
)
from app.services.translator import t

router = APIRouter()


def _supabase_admin() -> Any:
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


@router.post("/register", status_code=201)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)) -> RegisterResponse:
    """Register a new user — either create a new clan or join an existing one."""
    # Validate clan_action requirements
    if body.clan_action == "join" and not body.clan_id:
        raise ValidationError("auth.clan_id_required_for_join")
    if body.clan_action == "create" and (not body.clan_name or not body.clan_slug):
        raise ValidationError("auth.clan_name_required_for_create")

    # Create Supabase Auth user
    sb = _supabase_admin()
    try:
        auth_resp = sb.auth.admin.create_user(
            {"email": body.email, "password": body.password, "email_confirm": True}
        )
    except Exception as e:
        if "already" in str(e).lower():
            raise ConflictError("auth.email_already_exists") from e
        raise HTTPException(status_code=400, detail=str(e)) from e

    user_id = uuid.UUID(auth_resp.user.id)

    if body.clan_action == "create":
        # Check slug uniqueness
        existing = await db.execute(select(Clan).where(Clan.slug == body.clan_slug))
        if existing.scalar_one_or_none():
            raise ConflictError("auth.clan_slug_taken")

        clan = Clan(name=body.clan_name, slug=body.clan_slug)
        db.add(clan)
        await db.flush()

        role = UserClanRole(clan_id=clan.id, user_id=user_id, role="admin", is_approved=True)
        db.add(role)
        await db.commit()

        return RegisterResponse(
            user_id=user_id,
            email=body.email,
            full_name=body.full_name,
            clan_id=clan.id,
            is_approved=True,
            message=t("auth.clan_created"),
        )
    else:
        # Join existing clan
        clan_or_none = await db.get(Clan, body.clan_id)
        if not clan_or_none:
            raise NotFoundError("clan_not_found")
        clan = clan_or_none

        role = UserClanRole(clan_id=clan.id, user_id=user_id, role="viewer", is_approved=False)
        db.add(role)
        await db.commit()

        return RegisterResponse(
            user_id=user_id,
            email=body.email,
            full_name=body.full_name,
            clan_id=clan.id,
            is_approved=False,
            message=t("auth.registration_pending"),
        )


@router.post("/login")
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> LoginResponse:
    """Authenticate a user via Supabase Auth and return tokens + profile."""
    sb = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
    try:
        auth_resp = sb.auth.sign_in_with_password({"email": body.email, "password": body.password})
    except Exception as exc:
        raise HTTPException(status_code=401, detail=t("auth.invalid_credentials")) from exc

    session = auth_resp.session
    if session is None:
        raise HTTPException(status_code=401, detail=t("auth.invalid_credentials"))
    user = auth_resp.user
    if user is None:
        raise HTTPException(status_code=401, detail=t("auth.invalid_credentials"))
    user_id = uuid.UUID(user.id)

    # Fetch clan membership
    result = await db.execute(
        select(UserClanRole, Clan)
        .join(Clan, UserClanRole.clan_id == Clan.id)
        .where(UserClanRole.user_id == user_id)
        .limit(1)
    )
    row = result.first()

    clan_id = row.UserClanRole.clan_id if row else None
    clan_name = row.Clan.name if row else None
    role = row.UserClanRole.role if row and row.UserClanRole.is_approved else None
    is_approved = row.UserClanRole.is_approved if row else False
    member_id = row.UserClanRole.member_id if row else None

    return LoginResponse(
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        expires_in=session.expires_in,
        user=UserProfile(
            id=user_id,
            email=body.email,
            full_name=user.user_metadata.get("full_name", ""),
            clan_id=clan_id,
            clan_name=clan_name,
            role=role,
            is_approved=is_approved,
            member_id=member_id,
        ),
    )


@router.post("/logout")
async def logout(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """Invalidate the current session on Supabase Auth."""
    return {"message": t("auth.logged_out")}


@router.post("/refresh")
async def refresh_token(body: RefreshRequest) -> dict[str, Any]:
    """Exchange a refresh token for a new access token."""
    sb = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
    try:
        resp = sb.auth.refresh_session(body.refresh_token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail=t("auth.invalid_refresh_token")) from exc

    if not resp.session:
        raise HTTPException(status_code=401, detail=t("auth.invalid_refresh_token"))

    return {
        "access_token": resp.session.access_token,
        "refresh_token": resp.session.refresh_token,
        "expires_in": resp.session.expires_in,
    }


@router.get("/me")
async def get_me(
    current_user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return the authenticated user's profile."""
    user_id = uuid.UUID(current_user["sub"])

    result = await db.execute(
        select(UserClanRole, Clan)
        .join(Clan, UserClanRole.clan_id == Clan.id)
        .where(UserClanRole.user_id == user_id, UserClanRole.is_approved.is_(True))
        .limit(1)
    )
    row = result.first()

    return {
        "data": UserProfile(
            id=user_id,
            email=current_user.get("email", ""),
            full_name=current_user.get("user_metadata", {}).get("full_name", ""),
            clan_id=row.UserClanRole.clan_id if row else None,
            clan_name=row.Clan.name if row else None,
            role=row.UserClanRole.role if row else None,
            is_approved=bool(row),
            member_id=row.UserClanRole.member_id if row else None,
        ).model_dump()
    }


@router.patch("/me")
async def update_me(
    body: UserUpdateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Update the authenticated user's profile on Supabase Auth."""
    sb = _supabase_admin()
    update_data = {}
    if body.full_name is not None:
        update_data["user_metadata"] = {"full_name": body.full_name}
    if body.preferred_locale is not None:
        update_data.setdefault("user_metadata", {})["preferred_locale"] = body.preferred_locale

    if update_data:
        sb.auth.admin.update_user_by_id(current_user["sub"], update_data)

    return {"data": {"message": t("auth.profile_updated")}}


@router.post("/me/fcm-token")
async def register_fcm_token(
    body: FCMTokenRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Register or update an FCM push token for the current user's device."""
    user_id = current_user["sub"]
    await db.execute(
        text("""
            INSERT INTO public.user_fcm_tokens (user_id, token, device_platform)
            VALUES (:user_id, :token, :platform)
            ON CONFLICT (token) DO UPDATE
            SET user_id = :user_id, device_platform = :platform, updated_at = NOW()
        """),
        {"user_id": user_id, "token": body.token, "platform": body.device_platform},
    )
    await db.commit()
    return {"data": {"message": t("auth.fcm_token_registered")}}


@router.delete("/me/fcm-token")
async def remove_fcm_token(
    body: FCMTokenRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Remove an FCM token (e.g. on logout)."""
    user_id = current_user["sub"]
    await db.execute(
        text("DELETE FROM public.user_fcm_tokens WHERE user_id = :user_id AND token = :token"),
        {"user_id": user_id, "token": body.token},
    )
    await db.commit()
    return {"data": {"message": t("auth.fcm_token_removed")}}
