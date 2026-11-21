"""Delete your own account (ADR-079).

A signed-in user removes their sign-in account at the identity provider, their clan
memberships and roles, their push tokens and their profile row. The persons in a clan's
tree are clan data and stay, including one this account was linked to; a clan admin
anonymises a person separately (``PersonCommandHandler.anonymise``).

Refused while the user is the only approved admin of any clan, so no clan is left with
nobody to run it: the user transfers the admin role first.
"""

from __future__ import annotations

import uuid

from app.application.shared.audit import track_audit_event
from app.domain.auth.identity_provider import IdentityProvider
from app.domain.auth.repository import AccountRepository
from app.domain.shared.exceptions import ConflictError
from app.domain.shared.unit_of_work import UnitOfWork
from app.domain.shared.value_objects import ActorInfo

# The actor role on the audit row. The action is the account's own, not one taken
# under a clan role.
_ACCOUNT_ACTOR_ROLE = "user"


class AccountDeletionHandler:
    """The one use case: delete the caller's own account."""

    def __init__(
        self, repo: AccountRepository, uow: UnitOfWork, identity: IdentityProvider
    ) -> None:
        self._repo = repo
        self._uow = uow
        self._identity = identity

    async def delete_own_account(self, *, user_id: uuid.UUID) -> None:
        """Delete the account whose id is ``user_id`` (the JWT ``sub``).

        Order matters, and it is chosen so a failure leaves the account whole:

        1. Lock and check the admin sets. Refusal writes nothing.
        2. Delete the rows, and buffer the audit row, inside the open transaction.
        3. Delete the provider account. If that raises, nothing has been committed,
           the transaction rolls back with the session, and the person can retry.
        4. Commit (dispatching the audit row in the same transaction).

        The one window left is a commit that fails after step 3: the sign-in account
        is gone and the rows remain. A retry then finds the provider account already
        deleted, which the adapter treats as done, and completes the row deletion.
        """
        sole = await self._repo.lock_clans_where_sole_admin(user_id)
        if sole:
            raise ConflictError(
                "account.last_admin_transfer_first",
                {"clans": [{"clan_id": str(c.clan_id), "clan_name": c.clan_name} for c in sole]},
            )

        removed = await self._repo.delete_account_rows(user_id)
        # Ids and counts only. The email and the name are the data being erased, and
        # the audit trail is append-only, so they must not be copied into it.
        track_audit_event(
            self._uow,
            action="account.delete",
            resource_type="user",
            resource_id=user_id,
            actor=ActorInfo(user_id=user_id, role=_ACCOUNT_ACTOR_ROLE),
            clan_id=None,
            new_value={
                "profile_removed": removed.profile_removed,
                "clan_ids": [str(c) for c in removed.clan_ids],
            },
        )
        await self._uow.flush()

        await self._identity.delete_user(str(user_id))
        await self._uow.commit()
