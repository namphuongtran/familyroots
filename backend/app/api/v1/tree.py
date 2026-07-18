"""Tree API routes — thin controller delegating to Tree query handler."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.application.tree.handlers import TreeQueryHandler
from app.application.tree.queries import (
    FindPath,
    GetAncestors,
    GetFocusView,
    GetFullTree,
    GetSubtree,
)
from app.core.permissions import ClanRole, RequireViewer
from app.core.security import get_current_clan_id, get_current_user
from app.infrastructure.dependencies import get_tree_query_handler
from app.schemas.envelope import ok, ok_list
from app.schemas.tree import (
    FocusView,
    RelationshipPathResponse,
    TreeNodeDetail,
    TreeNodeSummary,
    TreeResponse,
)

router = APIRouter()


@router.get("", responses=ok(TreeResponse))
async def get_full_tree(
    root_person_id: uuid.UUID | None = Query(None),
    max_generations: int = Query(10, ge=1, le=50),
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: TreeQueryHandler = Depends(get_tree_query_handler),
    _role: ClanRole = RequireViewer,
    profile: str = Query("full", pattern="^(summary|detail|full)$"),
) -> dict[str, Any]:
    """Return the full family tree rooted at a person (or clan founder)."""
    result = await handler.get_full_tree(
        GetFullTree(
            clan_id=clan_id,
            root_person_id=root_person_id,
            max_generations=max_generations,
        )
    )
    if profile == "summary":
        result["tree"] = TreeNodeSummary.model_validate(result["tree"]).model_dump(
            exclude_unset=True
        )
    elif profile == "detail":
        result["tree"] = TreeNodeDetail.model_validate(result["tree"]).model_dump(
            exclude_unset=True
        )
    return {"data": result}


@router.get("/subtree/{person_id}", responses=ok(TreeResponse))
async def get_subtree(
    person_id: uuid.UUID,
    max_generations: int = Query(5, ge=1, le=50),
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: TreeQueryHandler = Depends(get_tree_query_handler),
    _role: ClanRole = RequireViewer,
    profile: str = Query("full", pattern="^(summary|detail|full)$"),
) -> dict[str, Any]:
    """Return a subtree rooted at a specific person."""
    result = await handler.get_subtree(
        GetSubtree(
            person_id=person_id,
            clan_id=clan_id,
            max_generations=max_generations,
        )
    )
    if profile == "summary":
        result["tree"] = TreeNodeSummary.model_validate(result["tree"]).model_dump(
            exclude_unset=True
        )
    elif profile == "detail":
        result["tree"] = TreeNodeDetail.model_validate(result["tree"]).model_dump(
            exclude_unset=True
        )
    return {"data": result}


@router.get("/ancestors/{person_id}", responses=ok_list(TreeNodeDetail))
async def get_ancestors(
    person_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: TreeQueryHandler = Depends(get_tree_query_handler),
    _role: ClanRole = RequireViewer,
    profile: str = Query("full", pattern="^(summary|detail|full)$"),
) -> dict[str, Any]:
    """Return the ancestor chain from a person up to the root."""
    ancestors = await handler.get_ancestors(GetAncestors(person_id=person_id, clan_id=clan_id))

    if profile == "summary":
        ancestors = [
            TreeNodeSummary.model_validate(a).model_dump(exclude_unset=True) for a in ancestors
        ]
    elif profile == "detail":
        ancestors = [
            TreeNodeDetail.model_validate(a).model_dump(exclude_unset=True) for a in ancestors
        ]

    return {"data": ancestors}


@router.get("/focus/{person_id}", responses=ok(FocusView))
async def get_focus(
    person_id: uuid.UUID,
    descendants: int = Query(2, ge=1, le=6),
    ancestors: int = Query(50, ge=0, le=50),
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: TreeQueryHandler = Depends(get_tree_query_handler),
    _role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """Focus view: breadcrumb ancestors + focus + descendant window, with computed đời."""
    result = await handler.get_focus_view(
        GetFocusView(
            person_id=person_id,
            clan_id=clan_id,
            ancestor_depth=ancestors,
            descendant_depth=descendants,
        )
    )
    # Validate/normalize the handler output against the published contract before returning.
    return {"data": FocusView.model_validate(result).model_dump()}


@router.get("/path", responses=ok(RelationshipPathResponse))
async def find_path(
    from_id: uuid.UUID = Query(...),
    to_id: uuid.UUID = Query(...),
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: TreeQueryHandler = Depends(get_tree_query_handler),
    _role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """Find the relationship path between two persons."""
    result = await handler.find_path(FindPath(from_id=from_id, to_id=to_id, clan_id=clan_id))
    return {"data": result}
