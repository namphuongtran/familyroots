"""Platform admin API routes — super admin only.

All routes in this module are protected by the ``get_super_admin`` dependency
and require the caller to be the platform super admin.
"""

from fastapi import APIRouter, Depends

from app.core.security import get_super_admin

router = APIRouter(prefix="/platform", tags=["Platform Admin"])


@router.get("/clans", dependencies=[Depends(get_super_admin)])
async def list_all_clans():
    """List all clans on the platform."""
    # TODO: implement in Prompt 2
    return {"clans": []}


@router.post("/clans/{clan_id}/suspend", dependencies=[Depends(get_super_admin)])
async def suspend_clan(clan_id: str):
    """Suspend a clan."""
    # TODO: implement in Prompt 2
    return {"status": "suspended", "clan_id": clan_id}


@router.post("/clans/{clan_id}/reactivate", dependencies=[Depends(get_super_admin)])
async def reactivate_clan(clan_id: str):
    """Reactivate a suspended clan."""
    # TODO: implement in Prompt 2
    return {"status": "active", "clan_id": clan_id}


@router.get("/metrics", dependencies=[Depends(get_super_admin)])
async def platform_metrics():
    """Platform-wide usage metrics."""
    # TODO: implement in Prompt 2
    return {"metrics": {}}


@router.get("/audit-log", dependencies=[Depends(get_super_admin)])
async def audit_log():
    """Cross-clan audit log."""
    # TODO: implement in Prompt 2
    return {"entries": []}


@router.post(
    "/clans/{clan_id}/admin/promote", dependencies=[Depends(get_super_admin)]
)
async def promote_clan_admin(clan_id: str):
    """Promote a user to clan admin."""
    # TODO: implement in Prompt 2
    return {"status": "promoted", "clan_id": clan_id}
