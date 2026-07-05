"""Query port protocol and read models for the Platform Admin bounded context.

The read side returns typed frozen-dataclass views instead of ``dict[str, Any]``
(mirrors the ``me`` context's ``ClanMembershipView``): the port contract is a
real type, the infra adapter maps rows → views, and the handler owns wire
serialization. Keeping these framework-agnostic (stdlib only) preserves domain
purity — no Pydantic/SQLAlchemy leaks across the seam.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class PageMeta:
    """Cursor-pagination metadata carried alongside a page of read models."""

    cursor: str | None
    has_more: bool
    limit: int


@dataclass(frozen=True)
class Page[T]:
    """A single page of typed read models plus its pagination metadata."""

    data: list[T]
    meta: PageMeta


@dataclass(frozen=True)
class ClanSummaryView:
    """One clan row in the platform-wide clan listing."""

    id: uuid.UUID
    name: str
    slug: str
    is_active: bool
    created_at: datetime | None = None


@dataclass(frozen=True)
class ClanStatsView:
    """Aggregate membership counts for a single clan."""

    total_members: int
    total_users: int


@dataclass(frozen=True)
class ClanDetailView:
    """Detail projection for a single clan, with aggregate stats."""

    id: uuid.UUID
    name: str
    slug: str
    is_active: bool
    description: str | None
    origin_place: str | None
    stats: ClanStatsView
    created_at: datetime | None = None


@dataclass(frozen=True)
class PlatformMetricsView:
    """Platform-wide adoption metrics."""

    total_clans: int
    active_clans: int
    suspended_clans: int
    total_members: int
    total_users: int


@dataclass(frozen=True)
class AuditLogEntryView:
    """One entry in the cross-clan audit log."""

    id: uuid.UUID
    # audit_logs.clan_id is nullable at the DB level (platform-level events); the
    # app always writes it via the event path, but the read model reflects the truth.
    clan_id: uuid.UUID | None
    actor_id: uuid.UUID
    actor_role: str
    action: str
    resource_type: str
    resource_id: uuid.UUID | None = None
    created_at: datetime | None = None


class PlatformAdminQueryPort(Protocol):
    """Abstract persistence contract for Platform Admin read operations."""

    async def list_clans(self, cursor: str | None, limit: int) -> Page[ClanSummaryView]:
        """List all clans with cursor pagination."""
        ...

    async def get_clan_detail(self, clan_id: uuid.UUID) -> ClanDetailView:
        """Get detail and metrics for a specific clan."""
        ...

    async def get_metrics(self) -> PlatformMetricsView:
        """Get global platform adoption metrics."""
        ...

    async def get_audit_log(
        self,
        clan_id: uuid.UUID | None,
        action: str | None,
        cursor: str | None,
        limit: int,
    ) -> Page[AuditLogEntryView]:
        """Get recent audit logs across the platform, cursor-paginated."""
        ...
