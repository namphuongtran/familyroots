"""FCM push-token registration handler."""

from __future__ import annotations

from app.domain.auth.repository import FCMTokenRepository
from app.domain.shared.unit_of_work import UnitOfWork


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
