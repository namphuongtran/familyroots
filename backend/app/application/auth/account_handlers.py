"""Account deletion: a signed-in user deletes their own account (ADR-079, #333)."""

from __future__ import annotations

import logging
import uuid

from app.application.shared.audit import track_audit_event
from app.domain.auth.identity_provider import IdentityProvider
from app.domain.auth.repository import AccountRepository
from app.domain.shared.exceptions import ForbiddenError
from app.domain.shared.unit_of_work import UnitOfWork
from app.domain.shared.value_objects import ActorInfo

logger = logging.getLogger(__name__)

ACCOUNT_DELETE_ACTION = "account.delete"


class AccountCommandHandler:
    """Deletes the caller's own account.

    Order (ADR-028, ADR-079): the database step runs and commits first, then the
    identity provider is called with no transaction open. A provider failure after the
    commit leaves a scrubbed, deactivated account, and the same request again finishes
    the job — the reverse order would strand personal data with no way to retry.
    """

    def __init__(
        self, repo: AccountRepository, uow: UnitOfWork, identity: IdentityProvider
    ) -> None:
        self._repo = repo
        self._uow = uow
        self._identity = identity

    async def delete_account(self, *, user_id: uuid.UUID) -> None:
        blocked = await self._repo.lock_clans_where_last_admin(user_id)
        if blocked:
            await self._uow.rollback()
            raise ForbiddenError(
                "account.last_admin_transfer_first",
                {"clan_ids": [str(clan_id) for clan_id in blocked]},
            )

        removed = await self._repo.remove_roles(user_id)
        await self._repo.remove_claims_and_push_tokens(user_id)
        cleared = await self._repo.tombstone_profile(user_id)

        if removed or cleared:
            for role in removed:
                track_audit_event(
                    self._uow,
                    action=ACCOUNT_DELETE_ACTION,
                    resource_type="user",
                    resource_id=user_id,
                    actor=ActorInfo(user_id=user_id, role=role.role),
                    clan_id=role.clan_id,
                    new_value={"role": role.role},
                )
            track_audit_event(
                self._uow,
                action=ACCOUNT_DELETE_ACTION,
                resource_type="user",
                resource_id=user_id,
                actor=ActorInfo(user_id=user_id, role="user"),
                clan_id=None,
                new_value={"clans_left": [str(role.clan_id) for role in removed]},
            )
        await self._uow.commit()

        # No connection is held from here on (ADR-028).
        await self._identity.delete_user(str(user_id))
