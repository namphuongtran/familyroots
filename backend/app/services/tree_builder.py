"""Recursive family tree construction service.

Assembles the flat SQL result from get_family_tree_flat()
into a nested JSON structure suitable for Flutter tree rendering.

Output format::

    {
      "id": "uuid",
      "full_name": "Nguyễn Văn A",
      "gender": "male",
      "birth_date": {"date": "1920-01-15", "precision": "exact", "display": null, "lunar": null},
      "death_date": {"date": "1985-03-20", "precision": "exact", "display": null, "lunar": null},
      "generation": 1,
      "avatar_url": "https://...",
      "is_founder": true,
      "membership_role": "blood",
      "posthumous_name": "...",
      "spouses": [
        {
          "id": "uuid",
          "full_name": "Trần Thị B",
          "status": "married",
          "marriage_date": "1945-02-10",
          "divorce_date": null,
          "spouse_order": 1
        }
      ],
      "children": [
        {
          "id": "uuid",
          "full_name": "Nguyễn Văn C",
          "relationship_type": "biological",
          "spouses": [...],
          "children": [...]   # recursive
        }
      ]
    }
"""

import datetime
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.schemas.historical_date import to_historical_date

_MAX_TREE_NODES = 50_000


def _historical_date_dict(
    row: Any, field_name: str, *, lunar_field: str | None = None
) -> dict[str, Any]:
    """Build a `HistoricalDate.model_dump()` dict from a flat SQL row's
    ``<field_name>``/``<field_name>_precision``/``<field_name>_display`` (+ optional
    lunar) columns."""
    lunar = row.get(lunar_field) if lunar_field else None
    return to_historical_date(
        row[field_name],
        row.get(f"{field_name}_precision"),
        row.get(f"{field_name}_display"),
        lunar,
    ).model_dump()


def _sortable_date(historical_date: dict[str, Any] | None) -> str:
    """Sort key for a nested HistoricalDate dict: the underlying date (ISO string) if
    set, else a sentinel that sorts after every real date (mirrors the pre-HistoricalDate
    behavior where a missing birth_date sorted last)."""
    value = historical_date.get("date") if historical_date else None
    if isinstance(value, datetime.date):
        return value.isoformat()
    return "9999"


@dataclass
class TreeNode:
    id: uuid.UUID
    full_name: str
    birth_name: str | None
    posthumous_name: str | None
    gender: str
    birth_date: dict[str, Any]
    death_date: dict[str, Any]
    birth_place: str | None
    generation: int | None
    avatar_url: str | None
    membership_role: str | None
    is_founder: bool
    parent_id: uuid.UUID | None
    depth: int
    spouses: list[dict[str, Any]] = field(default_factory=list)
    children: list[TreeNode] = field(default_factory=list)


async def build_descendants_tree(
    db: AsyncSession,
    root_id: uuid.UUID,
    clan_id: uuid.UUID,
    max_generations: int = 10,
    base_generation: int | None = None,
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

    # Step 2: Build node dict indexed by person_id
    nodes: dict[uuid.UUID, TreeNode] = {}
    for row in rows:
        node = TreeNode(
            id=row["person_id"],
            full_name=row["full_name"],
            birth_name=row.get("birth_name"),
            posthumous_name=row.get("posthumous_name"),
            gender=row["gender"],
            birth_date=_historical_date_dict(row, "birth_date"),
            death_date=_historical_date_dict(row, "death_date"),
            birth_place=row.get("birth_place"),
            generation=row.get("generation"),
            avatar_url=row.get("avatar_url"),
            membership_role=row.get("membership_role"),
            is_founder=row.get("is_founder", False),
            parent_id=row.get("parent_id"),
            depth=row["depth"],
        )
        nodes[node.id] = node

    # Step 3: Fetch spouses for all nodes in one query (avoid N+1)
    person_ids = list(nodes.keys())
    spouse_order_map: dict[tuple[uuid.UUID, uuid.UUID], int | None] = {}
    spouse_result = await db.execute(
        text(
            "SELECT "
            "CASE WHEN m.person1_id = ANY(:ids) THEN m.person1_id "
            "     ELSE m.person2_id END AS for_person_id, "
            "CASE WHEN m.person1_id = ANY(:ids) THEN m.person2_id "
            "     ELSE m.person1_id END AS spouse_id, "
            "p.full_name, p.gender, p.birth_date, p.birth_date_precision, p.birth_date_display, "
            "p.death_date, p.death_date_precision, p.death_date_display, "
            "p.lunar_birth_date, p.lunar_death_date, p.avatar_url, "
            "p.posthumous_name, "
            "m.status, m.marriage_date, m.divorce_date, m.spouse_order, "
            "cm.role AS membership_role "
            "FROM public.marriages m "
            "JOIN public.persons p "
            "    ON p.id = CASE WHEN m.person1_id = ANY(:ids) "
            "                   THEN m.person2_id ELSE m.person1_id END "
            "LEFT JOIN public.clan_memberships cm "
            "    ON cm.person_id = p.id AND cm.clan_id = :clan_id "
            "WHERE (m.person1_id = ANY(:ids) OR m.person2_id = ANY(:ids))"
            "  AND m.is_deleted = false"
            # A soft-deleted spouse must not render in spouses[] (the marriage
            # edge survives, but the person is hidden everywhere else).
            "  AND p.is_deleted = false"
            # Clan isolation: only traverse marriage edges this clan owns, so a
            # spouse recorded by another clan is never surfaced (C6).
            "  AND m.created_by_clan_id = :clan_id"
        ),
        {"ids": person_ids, "clan_id": clan_id},
    )
    for row in spouse_result.mappings().all():
        for_id = row["for_person_id"]
        if for_id in nodes:
            nodes[for_id].spouses.append(
                {
                    "id": str(row["spouse_id"]),
                    "full_name": row["full_name"],
                    "gender": row["gender"],
                    "birth_date": _historical_date_dict(
                        row, "birth_date", lunar_field="lunar_birth_date"
                    ),
                    "death_date": _historical_date_dict(
                        row, "death_date", lunar_field="lunar_death_date"
                    ),
                    "avatar_url": row["avatar_url"],
                    "posthumous_name": row["posthumous_name"],
                    "status": row["status"],
                    "marriage_date": (
                        row["marriage_date"].isoformat() if row["marriage_date"] else None
                    ),
                    "divorce_date": (
                        row["divorce_date"].isoformat() if row["divorce_date"] else None
                    ),
                    "spouse_order": row["spouse_order"],
                    "membership_role": row["membership_role"],
                }
            )
            spouse_order_map[(for_id, row["spouse_id"])] = row["spouse_order"]

    # Step 3b: Derive each child's mother (đa thê "con của bà nào") — clan-scoped.
    mothers = await _mother_map(db, list(nodes.keys()), clan_id)

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
        node.children.sort(key=lambda c: (_sortable_date(c.birth_date), c.full_name))
        for child in node.children:
            sort_children(child)

    sort_children(root_node)

    # Step 6: Serialize to dict
    def node_to_dict(node: TreeNode) -> dict[str, Any]:
        return {
            "id": str(node.id),
            "full_name": node.full_name,
            "birth_name": node.birth_name,
            "posthumous_name": node.posthumous_name,
            "gender": node.gender,
            "birth_date": node.birth_date,
            "death_date": node.death_date,
            "birth_place": node.birth_place,
            "generation": (base_generation + node.depth if base_generation is not None else None),
            "avatar_url": node.avatar_url,
            "membership_role": node.membership_role,
            "is_founder": node.is_founder,
            "depth": node.depth,
            "mother_id": (str(mothers[node.id]) if node.id in mothers else None),
            "mother_spouse_order": (
                spouse_order_map.get((node.parent_id, mothers[node.id]))
                if node.id in mothers and node.parent_id is not None
                else None
            ),
            "spouses": node.spouses,
            "children": [node_to_dict(c) for c in node.children],
        }

    return node_to_dict(root_node)


async def find_clan_founder(
    db: AsyncSession,
    clan_id: uuid.UUID,
) -> uuid.UUID | None:
    """Return the id of the clan founder (root of the tree).

    Deterministic even on legacy data with more than one live ``is_founder``
    row for a clan (pre-023 databases, or any row this migration's index
    didn't retroactively repair): ordered by earliest ``joined_at`` (NULLs
    last), then ``person_id`` as a stable tiebreaker, so repeated calls
    always pick the same row. Migration 023's partial unique index on
    ``clan_memberships (clan_id) WHERE is_founder = true`` makes >1 live
    founder impossible going forward — this ordering only matters for
    already-corrupt legacy rows.
    """
    result = await db.execute(
        text(
            "SELECT cm.person_id FROM public.clan_memberships cm "
            "JOIN public.persons p ON p.id = cm.person_id "
            "WHERE cm.clan_id = :clan_id "
            "  AND cm.is_founder = true "
            "  AND p.is_deleted = false "
            "ORDER BY cm.joined_at ASC NULLS LAST, cm.person_id "
            "LIMIT 1"
        ),
        {"clan_id": clan_id},
    )
    row = result.first()
    return row[0] if row else None


_BIRTH_ORDER_LAST = 32767  # SmallInteger max — NULL birth_order sorts after all set values


async def _mother_map(
    db: AsyncSession, child_ids: list[uuid.UUID], clan_id: uuid.UUID
) -> dict[uuid.UUID, uuid.UUID]:
    """child_id → female-parent (mother) id, via this clan's parent_child edges."""
    if not child_ids:
        return {}
    result = await db.execute(
        text(
            "SELECT pc.child_id, p.id AS mother_id "
            "FROM public.parent_child pc "
            "JOIN public.persons p ON p.id = pc.parent_id "
            "  AND p.gender = 'female' AND p.is_deleted = false "
            "WHERE pc.child_id = ANY(:ids) AND pc.created_by_clan_id = :clan_id "
            "  AND pc.is_deleted = false"
        ),
        {"ids": child_ids, "clan_id": clan_id},
    )
    # One mother per child (a child has at most one female parent in practice); if data
    # records more than one, the last row wins — acceptable for this read-model.
    return {row["child_id"]: row["mother_id"] for row in result.mappings().all()}


async def _branch_map(
    db: AsyncSession, person_ids: list[uuid.UUID], clan_id: uuid.UUID
) -> dict[uuid.UUID, dict[str, Any]]:
    """Chi/branch per member (clan-scoped). Members with no branch are simply absent."""
    if not person_ids:
        return {}
    result = await db.execute(
        text(
            "SELECT cm.person_id, b.id AS branch_id, b.name, b.branch_order "
            "FROM public.clan_memberships cm "
            "JOIN public.branches b ON b.id = cm.branch_id AND b.clan_id = :clan_id "
            "WHERE cm.person_id = ANY(:ids) AND cm.clan_id = :clan_id"
        ),
        {"ids": person_ids, "clan_id": clan_id},
    )
    return {
        row["person_id"]: {
            "id": str(row["branch_id"]),
            "name": row["name"],
            "order": row["branch_order"],
        }
        for row in result.mappings().all()
    }


async def _birth_order_map(
    db: AsyncSession, person_ids: list[uuid.UUID], clan_id: uuid.UUID
) -> dict[uuid.UUID, int]:
    """Smallest set birth_order per child among this clan's blood edges (NULLs ignored)."""
    if not person_ids:
        return {}
    result = await db.execute(
        text(
            "SELECT pc.child_id, MIN(pc.birth_order) AS birth_order "
            "FROM public.parent_child pc "
            "WHERE pc.child_id = ANY(:ids) AND pc.created_by_clan_id = :clan_id "
            "  AND pc.is_deleted = false AND pc.birth_order IS NOT NULL "
            "GROUP BY pc.child_id"
        ),
        {"ids": person_ids, "clan_id": clan_id},
    )
    return {row["child_id"]: row["birth_order"] for row in result.mappings().all()}


async def _persons_with_children(
    db: AsyncSession, person_ids: list[uuid.UUID], clan_id: uuid.UUID
) -> set[uuid.UUID]:
    """Subset of ``person_ids`` that have at least one non-deleted child via a clan-owned edge."""
    if not person_ids:
        return set()
    result = await db.execute(
        text(
            "SELECT DISTINCT pc.parent_id "
            "FROM public.parent_child pc "
            "JOIN public.persons ch ON ch.id = pc.child_id AND ch.is_deleted = false "
            "WHERE pc.parent_id = ANY(:ids) AND pc.created_by_clan_id = :clan_id "
            "  AND pc.is_deleted = false"
        ),
        {"ids": person_ids, "clan_id": clan_id},
    )
    return {row["parent_id"] for row in result.mappings().all()}


async def build_focus_view(
    db: AsyncSession,
    focus_id: uuid.UUID,
    clan_id: uuid.UUID,
    descendant_depth: int,
    base_generation: int | None,
) -> dict[str, Any]:
    """Focus subtree (focus + ``descendant_depth`` generations below), enriched with computed
    đời, chi/branch, birth_order sibling order, and a has-more-descendants drill flag."""
    subtree = await build_descendants_tree(db, focus_id, clan_id, descendant_depth, base_generation)
    if not subtree:
        return {}

    node_ids: list[uuid.UUID] = []
    boundary_ids: list[uuid.UUID] = []

    def collect(node: dict[str, Any]) -> None:
        pid = uuid.UUID(node["id"])
        node_ids.append(pid)
        if node["depth"] == descendant_depth:
            boundary_ids.append(pid)
        for child in node["children"]:
            collect(child)

    collect(subtree)

    branches = await _branch_map(db, node_ids, clan_id)
    birth_orders = await _birth_order_map(db, node_ids, clan_id)
    have_children = await _persons_with_children(db, boundary_ids, clan_id)

    def enrich(node: dict[str, Any]) -> None:
        pid = uuid.UUID(node["id"])
        branch = branches.get(pid)
        node["branch_id"] = branch["id"] if branch else None
        node["branch_name"] = branch["name"] if branch else None
        node["branch_order"] = branch["order"] if branch else None
        node["has_more_descendants"] = pid in have_children
        node["children"].sort(
            key=lambda c: (
                birth_orders.get(uuid.UUID(c["id"]), _BIRTH_ORDER_LAST),
                _sortable_date(c["birth_date"]),
                c["full_name"],
            )
        )
        for child in node["children"]:
            enrich(child)

    enrich(subtree)
    return subtree
