"""Aggregate all v1 API route includes."""

from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.branches import router as branches_router
from app.api.v1.change_requests import router as change_requests_router
from app.api.v1.claims import admin_claims_router, user_claims_router
from app.api.v1.clans import router as clans_router
from app.api.v1.documents import router as documents_router
from app.api.v1.events import router as events_router
from app.api.v1.exports import router as exports_router
from app.api.v1.invitations import admin_invitations_router, user_invitations_router
from app.api.v1.me import router as me_router
from app.api.v1.persons import router as persons_router
from app.api.v1.platform_admin import router as platform_admin_router
from app.api.v1.relationships import router as relationships_router
from app.api.v1.tree import router as tree_router
from app.schemas.envelope import DEFAULT_ERROR_RESPONSES

api_v1_router = APIRouter(responses=DEFAULT_ERROR_RESPONSES)

api_v1_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_v1_router.include_router(branches_router, prefix="/branches", tags=["branches"])
api_v1_router.include_router(clans_router, prefix="/clans", tags=["clans"])
api_v1_router.include_router(me_router, prefix="/me", tags=["me"])
api_v1_router.include_router(persons_router, prefix="/persons", tags=["persons"])
api_v1_router.include_router(relationships_router, prefix="/relationships", tags=["relationships"])
api_v1_router.include_router(documents_router, prefix="/documents", tags=["documents"])
api_v1_router.include_router(events_router, prefix="/events", tags=["events"])
api_v1_router.include_router(tree_router, prefix="/tree", tags=["tree"])
api_v1_router.include_router(exports_router, prefix="/exports", tags=["exports"])
api_v1_router.include_router(
    change_requests_router, prefix="/change-requests", tags=["change-requests"]
)

# Claims
api_v1_router.include_router(user_claims_router, prefix="/claims", tags=["claims"])
api_v1_router.include_router(admin_claims_router, prefix="/clans/{clan_id}/claims", tags=["claims"])

# Invitations
api_v1_router.include_router(
    admin_invitations_router, prefix="/clans/{clan_id}/invitations", tags=["invitations"]
)
api_v1_router.include_router(user_invitations_router, prefix="/invitations", tags=["invitations"])

api_v1_router.include_router(platform_admin_router)
