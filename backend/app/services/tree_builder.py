"""Recursive family tree construction service.

Assembles the flat SQL result from get_family_tree_flat()
into a nested JSON structure suitable for Flutter tree rendering.

Output format::

    {
      "id": "uuid",
      "full_name": "Nguyễn Văn A",
      "gender": "male",
      "birth_date": "1920-01-15",
      "death_date": "1985-03-20",
      "generation": 1,
      "avatar_url": "https://...",
      "is_clan_founder": true,
      "spouses": [
        {
          "id": "uuid",
          "full_name": "Trần Thị B",
          "relation_subtype": "married",
          "start_date": "1945-02-10",
          "end_date": null,
          "is_primary": true
        }
      ],
      "children": [
        {
          "id": "uuid",
          "full_name": "Nguyễn Văn C",
          "relation_subtype": "biological",
          "spouses": [...],
          "children": [...]   # recursive
        }
      ]
    }
"""

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError

_MAX_TREE_NODES = 50_000


@dataclass
class TreeNode:
    id: uuid.UUID
    full_name: str
    birth_name: str | None
    gender: str
    birth_date: str | None
    birth_date_approx: bool
    death_date: str | None
    death_date_approx: bool
    birth_place: str | None
    generation: int | None
    avatar_url: str | None
    is_clan_member: bool
    is_clan_founder: bool
    parent_id: uuid.UUID | None
    depth: int
    spouses: list[dict[str, Any]] = field(default_factory=list)
    children: list[TreeNode] = field(default_factory=list)


async def build_descendants_tree(
    db: AsyncSession,
    root_id: uuid.UUID,
    clan_id: uuid.UUID,
    max_generations: int = 10,
) -> dict[str, Any]:
    """Call get_family_tree_flat() SQL function, fetch spouses for each node,
    then assemble into nested dict for JSON response.
    """
    # Step 1: Get all descendants as flat list
    flat_result = await db.execute(
        text("SELECT * FROM public.get_family_tree_flat(:root_id, :clan_id, :max_generations)"),
        {"root_id": root_id, "clan_id": clan_id, "max_generations": max_generations},
    )
    rows = flat_result.mappings().all()

    if not rows:
        return {}

    if len(rows) > _MAX_TREE_NODES:
        raise ValidationError(
            "tree_too_large",
            {"max_nodes": _MAX_TREE_NODES, "actual_nodes": len(rows)},
        )

    # Step 2: Build node dict indexed by member_id
    nodes: dict[uuid.UUID, TreeNode] = {}
    for row in rows:
        node = TreeNode(
            id=row["member_id"],
            full_name=row["full_name"],
            birth_name=row["birth_name"],
            gender=row["gender"],
            birth_date=row["birth_date"].isoformat() if row["birth_date"] else None,
            birth_date_approx=row["birth_date_approx"],
            death_date=row["death_date"].isoformat() if row["death_date"] else None,
            death_date_approx=row["death_date_approx"],
            birth_place=row["birth_place"],
            generation=row["generation"],
            avatar_url=row["avatar_url"],
            is_clan_member=row["is_clan_member"],
            is_clan_founder=row["is_clan_founder"],
            parent_id=row["parent_id"],
            depth=row["depth"],
        )
        nodes[node.id] = node

    # Step 3: Fetch spouses for all nodes in one query (avoid N+1)
    member_ids = list(nodes.keys())
    spouse_result = await db.execute(
        text(
            "SELECT "
            "CASE WHEN r.member_id = ANY(:ids) THEN r.member_id "
            "     ELSE r.related_id END AS for_member_id, "
            "CASE WHEN r.member_id = ANY(:ids) THEN r.related_id "
            "     ELSE r.member_id END AS spouse_id, "
            "m.full_name, m.gender, m.birth_date, m.death_date, m.avatar_url, "
            "r.relation_subtype, r.start_date, r.end_date, r.is_primary "
            "FROM public.relationships r "
            "JOIN public.members m "
            "    ON m.id = CASE WHEN r.member_id = ANY(:ids) "
            "                   THEN r.related_id ELSE r.member_id END "
            "WHERE r.clan_id = :clan_id "
            "  AND r.relation_type = 'spouse' "
            "  AND (r.member_id = ANY(:ids) OR r.related_id = ANY(:ids))"
        ),
        {"ids": member_ids, "clan_id": clan_id},
    )
    for row in spouse_result.mappings().all():
        for_id = row["for_member_id"]
        if for_id in nodes:
            nodes[for_id].spouses.append(
                {
                    "id": str(row["spouse_id"]),
                    "full_name": row["full_name"],
                    "gender": row["gender"],
                    "birth_date": (row["birth_date"].isoformat() if row["birth_date"] else None),
                    "death_date": (row["death_date"].isoformat() if row["death_date"] else None),
                    "avatar_url": row["avatar_url"],
                    "relation_subtype": row["relation_subtype"],
                    "start_date": (row["start_date"].isoformat() if row["start_date"] else None),
                    "end_date": (row["end_date"].isoformat() if row["end_date"] else None),
                    "is_primary": row["is_primary"],
                }
            )

    # Step 4: Wire children into parent nodes
    root_node = None
    for node in nodes.values():
        if node.parent_id is None:
            root_node = node
        elif node.parent_id in nodes:
            nodes[node.parent_id].children.append(node)

    if root_node is None:
        return {}

    # Step 5: Sort children by birth_date, then name
    def sort_children(node: TreeNode) -> None:
        node.children.sort(key=lambda c: (c.birth_date or "9999", c.full_name))
        for child in node.children:
            sort_children(child)

    sort_children(root_node)

    # Step 6: Serialize to dict
    def node_to_dict(node: TreeNode) -> dict[str, Any]:
        return {
            "id": str(node.id),
            "full_name": node.full_name,
            "birth_name": node.birth_name,
            "gender": node.gender,
            "birth_date": node.birth_date,
            "birth_date_approx": node.birth_date_approx,
            "death_date": node.death_date,
            "death_date_approx": node.death_date_approx,
            "birth_place": node.birth_place,
            "generation": node.generation,
            "avatar_url": node.avatar_url,
            "is_clan_member": node.is_clan_member,
            "is_clan_founder": node.is_clan_founder,
            "depth": node.depth,
            "spouses": node.spouses,
            "children": [node_to_dict(c) for c in node.children],
        }

    return node_to_dict(root_node)


async def find_clan_founder(
    db: AsyncSession,
    clan_id: uuid.UUID,
) -> uuid.UUID | None:
    """Return the id of the clan founder (root of the tree)."""
    result = await db.execute(
        text(
            "SELECT id FROM public.members "
            "WHERE clan_id = :clan_id "
            "  AND is_clan_founder = true "
            "  AND is_deleted = false "
            "LIMIT 1"
        ),
        {"clan_id": clan_id},
    )
    row = result.first()
    return row[0] if row else None
