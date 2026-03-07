"""Tree API routes — family tree retrieval and visualization."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import NotFoundError, ValidationError
from app.core.permissions import ClanRole, RequireViewer
from app.core.security import get_current_clan_id, get_current_user
from app.models.member import Member
from app.services.relationship_descriptor import describe_relationship
from app.services.tree_builder import build_descendants_tree, find_clan_founder

router = APIRouter()


@router.get("")
async def get_full_tree(
    root_member_id: uuid.UUID | None = Query(None),
    max_generations: int = Query(10, ge=1, le=10),
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """Return the full family tree rooted at a member (or clan founder)."""
    root_id = root_member_id
    if root_id is None:
        root_id = await find_clan_founder(db, clan_id)
        if root_id is None:
            raise NotFoundError("clan_founder_not_found")
    else:
        # Validate root_member_id belongs to this clan
        result = await db.execute(
            select(Member).where(
                Member.id == root_id,
                Member.clan_id == clan_id,
                Member.is_deleted.is_(False),
            )
        )
        if not result.scalar_one_or_none():
            raise NotFoundError("member_not_found", {"member_id": str(root_id)})

    tree = await build_descendants_tree(db, root_id, clan_id, max_generations)
    if not tree:
        raise NotFoundError("tree_empty")

    # Compute totals
    total_members = _count_nodes(tree)
    total_generations = _max_depth(tree) + 1

    return {
        "data": {
            "tree": tree,
            "total_members": total_members,
            "total_generations": total_generations,
        }
    }


@router.get("/subtree/{member_id}")
async def get_subtree(
    member_id: uuid.UUID,
    max_generations: int = Query(5, ge=1, le=10),
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """Return a subtree rooted at a specific member."""
    result = await db.execute(
        select(Member).where(
            Member.id == member_id,
            Member.clan_id == clan_id,
            Member.is_deleted.is_(False),
        )
    )
    if not result.scalar_one_or_none():
        raise NotFoundError("member_not_found")

    tree = await build_descendants_tree(db, member_id, clan_id, max_generations)
    if not tree:
        raise NotFoundError("tree_empty")

    return {
        "data": {
            "tree": tree,
            "total_members": _count_nodes(tree),
            "total_generations": _max_depth(tree) + 1,
        }
    }


@router.get("/ancestors/{member_id}")
async def get_ancestors(
    member_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """Return the ancestor chain from a member up to the root."""
    result = await db.execute(
        select(Member).where(
            Member.id == member_id,
            Member.clan_id == clan_id,
            Member.is_deleted.is_(False),
        )
    )
    if not result.scalar_one_or_none():
        raise NotFoundError("member_not_found")

    ancestors_result = await db.execute(
        text(
            "WITH RECURSIVE ancestors AS ("
            "  SELECT m.id, m.full_name, m.gender, m.birth_date, m.death_date, "
            "         m.avatar_url, m.generation, r.member_id AS parent_id, 0 AS depth "
            "  FROM public.members m "
            "  LEFT JOIN public.relationships r "
            "    ON r.related_id = m.id "
            "    AND r.relation_type = 'parent' "
            "    AND r.clan_id = :clan_id "
            "  WHERE m.id = :member_id AND m.clan_id = :clan_id "
            "  UNION ALL "
            "  SELECT m.id, m.full_name, m.gender, m.birth_date, m.death_date, "
            "         m.avatar_url, m.generation, r.member_id AS parent_id, a.depth + 1 "
            "  FROM ancestors a "
            "  JOIN public.members m ON m.id = a.parent_id "
            "  LEFT JOIN public.relationships r "
            "    ON r.related_id = m.id "
            "    AND r.relation_type = 'parent' "
            "    AND r.clan_id = :clan_id "
            "  WHERE m.clan_id = :clan_id AND m.is_deleted = false "
            "    AND a.depth < 50 "
            ") "
            "SELECT id, full_name, gender, birth_date, death_date, "
            "       avatar_url, generation, parent_id, depth "
            "FROM ancestors ORDER BY depth ASC"
        ),
        {"member_id": member_id, "clan_id": clan_id},
    )
    rows = ancestors_result.mappings().all()

    ancestors = [
        {
            "id": str(row["id"]),
            "full_name": row["full_name"],
            "gender": row["gender"],
            "birth_date": row["birth_date"].isoformat() if row["birth_date"] else None,
            "death_date": row["death_date"].isoformat() if row["death_date"] else None,
            "avatar_url": row["avatar_url"],
            "generation": row["generation"],
            "depth": row["depth"],
        }
        for row in rows
    ]
    return {"data": ancestors}


@router.get("/path")
async def find_path(
    from_id: uuid.UUID = Query(...),
    to_id: uuid.UUID = Query(...),
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """Find the relationship path between two members and describe it."""
    if from_id == to_id:
        raise ValidationError("same_member_path")

    # Verify both members exist in the clan
    for mid in [from_id, to_id]:
        result = await db.execute(
            select(Member).where(
                Member.id == mid,
                Member.clan_id == clan_id,
Member.is_deleted.is_(False),
            )
        )
        if not result.scalar_one_or_none():
            raise NotFoundError("member_not_found", {"member_id": str(mid)})

    # Use find_relationship_path SQL function
    path_result = await db.execute(
        text(
            "SELECT * FROM public.find_relationship_path("
            ":from_id, :to_id, :clan_id)"
        ),
        {"from_id": from_id, "to_id": to_id, "clan_id": clan_id},
    )
    rows = path_result.mappings().all()

    if not rows:
        return {
            "data": {
                "path": [],
                "description": None,
                "found": False,
            }
        }

    path = [
        {
            "member_id": str(row["member_id"]),
            "full_name": row["full_name"],
            "gender": row.get("gender", "unknown"),
            "edge_type": row.get("edge_type"),
        }
        for row in rows
    ]

    # Get genders for descriptor
    from_gender = path[0]["gender"] if path else "unknown"
    to_gender = path[-1]["gender"] if path else "unknown"

    description = describe_relationship(path, from_gender, to_gender)

    return {
        "data": {
            "path": path,
            "description": description,
            "found": True,
        }
    }


def _count_nodes(tree: dict[str, Any]) -> int:
    """Recursively count all nodes in the tree."""
    count = 1
    for child in tree.get("children", []):
        count += _count_nodes(child)
    return count


def _max_depth(tree: dict[str, Any]) -> int:
    """Recursively compute max depth of the tree."""
    children = tree.get("children", [])
    if not children:
        return 0
    return 1 + max(_max_depth(c) for c in children)
