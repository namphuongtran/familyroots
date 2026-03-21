"""Query port protocols for Platform Admin bounded context."""

from __future__ import annotations

import uuid
from typing import Any, Protocol


class PlatformAdminQueryPort(Protocol):
    """Abstract persistence contract for Platform Admin read operations."""

    async def list_clans(self, cursor: str | None, limit: int) -> dict[str, Any]:
        """List all clans with pagination."""
        ...

    async def get_clan_detail(self, clan_id: uuid.UUID) -> dict[str, Any]:
        """Get detail and metrics for a specific clan."""
        ...

    async def get_metrics(self) -> dict[str, Any]:
        """Get global platform adoption metrics."""
        ...

    async def get_audit_log(
        self,
        clan_id: uuid.UUID | None,
        action: str | None,
        cursor: str | None,
        limit: int,
    ) -> dict[str, Any]:
        """Get recent audit logs across the platform."""
        ...
