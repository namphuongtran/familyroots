"""Unit tests for ClanCommandHandler."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.clan.commands import (
    ApproveUser,
    ChangeUserRole,
    RemoveUser,
    UpdateClan,
)
from app.application.clan.handlers import ClanCommandHandler
from app.domain.shared.exceptions import (
    BusinessRuleViolation,
    ConflictError,
    EntityNotFoundError,
    ForbiddenError,
)
from app.domain.shared.value_objects import ActorInfo


def _make_handler(**repo_overrides: object) -> ClanCommandHandler:
    repo = AsyncMock()
    # Default: clan exists
    repo.get_clan = AsyncMock(return_value=MagicMock())
    for k, v in repo_overrides.items():
        setattr(repo, k, AsyncMock(return_value=v))
    uow = AsyncMock()
    uow.track = lambda agg: None
    return ClanCommandHandler(repo, uow)


def _actor() -> ActorInfo:
    return ActorInfo(user_id=uuid.uuid4(), role="admin")


class TestClanUpdate:
    @pytest.mark.asyncio
    async def test_update_clan_not_found(self) -> None:
        h = _make_handler(get_clan=None)
        with pytest.raises(EntityNotFoundError):
            await h.update_clan(
                UpdateClan(clan_id=uuid.uuid4(), actor=_actor(), changes={"name": "x"})
            )


class TestApproveUser:
    @pytest.mark.asyncio
    async def test_already_approved_raises(self) -> None:
        ucr = MagicMock(is_approved=True, id=uuid.uuid4())
        h = _make_handler(get_user_clan_role=ucr)
        with pytest.raises(ConflictError, match="already_approved"):
            await h.approve_user(
                ApproveUser(clan_id=uuid.uuid4(), target_user_id=uuid.uuid4(), actor=_actor())
            )

    @pytest.mark.asyncio
    async def test_user_not_found_raises(self) -> None:
        h = _make_handler(get_user_clan_role=None)
        with pytest.raises(EntityNotFoundError):
            await h.approve_user(
                ApproveUser(clan_id=uuid.uuid4(), target_user_id=uuid.uuid4(), actor=_actor())
            )


class TestChangeRole:
    @pytest.mark.asyncio
    async def test_invalid_role_raises(self) -> None:
        h = _make_handler()
        with pytest.raises(BusinessRuleViolation, match="invalid_role"):
            await h.change_role(
                ChangeUserRole(
                    clan_id=uuid.uuid4(),
                    target_user_id=uuid.uuid4(),
                    new_role="superadmin",
                    actor=_actor(),
                )
            )

    @pytest.mark.asyncio
    async def test_last_admin_cannot_demote_self(self) -> None:
        actor = _actor()
        ucr = MagicMock(role="admin", id=uuid.uuid4())
        h = _make_handler(get_user_clan_role=ucr, count_admins=1)
        with pytest.raises(ForbiddenError, match="last_admin"):
            await h.change_role(
                ChangeUserRole(
                    clan_id=uuid.uuid4(),
                    target_user_id=actor.user_id,
                    new_role="viewer",
                    actor=actor,
                )
            )


class TestRemoveUser:
    @pytest.mark.asyncio
    async def test_cannot_remove_self(self) -> None:
        actor = _actor()
        h = _make_handler()
        with pytest.raises(ForbiddenError, match="cannot_remove_self"):
            await h.remove_user(
                RemoveUser(clan_id=uuid.uuid4(), target_user_id=actor.user_id, actor=actor)
            )

    @pytest.mark.asyncio
    async def test_user_not_found_raises(self) -> None:
        h = _make_handler(get_user_clan_role=None)
        with pytest.raises(EntityNotFoundError):
            await h.remove_user(
                RemoveUser(clan_id=uuid.uuid4(), target_user_id=uuid.uuid4(), actor=_actor())
            )
