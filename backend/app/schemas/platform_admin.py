"""Pydantic v2 response schemas for platform-admin routes — OpenAPI docs only.

These mirror the exact JSON wire shapes emitted by ``PlatformAdminQueryHandler``
(``app/application/platform_admin/handlers.py``): UUIDs and datetimes are already
serialized to strings there, so these are typed to the wire (``str``), NOT to the
domain read-model dataclasses (which carry ``uuid.UUID``/``datetime``). Declared
via each route's documentation-only ``responses=`` — never ``response_model=``.
"""

from __future__ import annotations

from pydantic import BaseModel


class ClanSummaryResponse(BaseModel):
    """One clan row in the platform-wide clan listing."""

    id: str
    name: str
    slug: str
    is_active: bool
    created_at: str | None = None


class ClanStatsResponse(BaseModel):
    """Aggregate membership counts for a single clan."""

    total_members: int
    total_users: int


class ClanDetailResponse(BaseModel):
    """Detail projection for a single clan, with aggregate stats."""

    id: str
    name: str
    slug: str
    is_active: bool
    description: str | None = None
    origin_place: str | None = None
    stats: ClanStatsResponse
    created_at: str | None = None


class ClanStatusResponse(BaseModel):
    """Acknowledgement body for suspend/reactivate."""

    is_active: bool
    clan_id: str


class PlatformMetricsResponse(BaseModel):
    """Platform-wide adoption metrics."""

    total_clans: int
    active_clans: int
    suspended_clans: int
    total_members: int
    total_users: int


class AuditLogEntryResponse(BaseModel):
    """One entry in the cross-clan audit log."""

    id: str
    clan_id: str | None = None
    actor_id: str
    actor_role: str
    action: str
    resource_type: str
    resource_id: str | None = None
    created_at: str | None = None
