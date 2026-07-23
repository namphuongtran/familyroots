"""Tree query handlers.

Orchestrate tree repository and relationship descriptor service.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.application.tree.queries import (
    FindPath,
    GetAncestors,
    GetFocusView,
    GetFullTree,
    GetSubtree,
)
from app.domain.shared.exceptions import BusinessRuleViolation, EntityNotFoundError
from app.domain.tree.repository import TreeRepository
from app.services.relationship_descriptor import describe_relationship


class TreeQueryHandler:
    """Read-only handler for family tree queries."""

    def __init__(self, repo: TreeRepository) -> None:
        self._repo = repo

    async def get_full_tree(self, query: GetFullTree) -> dict[str, Any]:
        """Return the full family tree."""
        root_id = query.root_person_id
        if root_id is None:
            root_id = await self._repo.find_clan_founder(query.clan_id)
            if root_id is None:
                raise EntityNotFoundError("clan_founder_not_found")
        else:
            if not await self._repo.person_in_clan(root_id, query.clan_id):
                raise EntityNotFoundError("person_not_found")

        doi = await self._repo.get_generation_map(query.clan_id)
        tree = await self._repo.build_descendants_tree(
            root_id, query.clan_id, query.max_generations, doi_map=doi
        )
        if not tree:
            raise EntityNotFoundError("tree_empty")

        return {
            "tree": tree,
            "total_persons": _count_nodes(tree),
            "total_generations": _max_depth(tree) + 1,
        }

    async def get_subtree(self, query: GetSubtree) -> dict[str, Any]:
        """Return a subtree rooted at a specific person."""
        if not await self._repo.person_in_clan(query.person_id, query.clan_id):
            raise EntityNotFoundError("person_not_found")

        doi = await self._repo.get_generation_map(query.clan_id)
        tree = await self._repo.build_descendants_tree(
            query.person_id, query.clan_id, query.max_generations, doi_map=doi
        )
        if not tree:
            raise EntityNotFoundError("tree_empty")

        return {
            "tree": tree,
            "total_persons": _count_nodes(tree),
            "total_generations": _max_depth(tree) + 1,
        }

    async def get_ancestors(self, query: GetAncestors) -> list[dict[str, Any]]:
        """Return the ancestor chain, with đời computed from the graph (thủy tổ = đời
        1) — the same graph-computed contract enforced on every other tree endpoint,
        rather than the raw hand-entered ``clan_memberships.generation``."""
        if not await self._repo.person_in_clan(query.person_id, query.clan_id):
            raise EntityNotFoundError("person_not_found")

        doi = await self._repo.get_generation_map(query.clan_id)
        rows = await self._repo.get_ancestors(query.person_id, query.clan_id)

        stamped: list[dict[str, Any]] = []
        for row in rows:
            entry = doi.get(uuid.UUID(row["id"]))
            stamped.append({**row, "generation": entry.generation if entry else None})
        return stamped

    async def get_focus_view(self, query: GetFocusView) -> dict[str, Any]:
        """Assemble the focus view: breadcrumb ancestors + focus + descendant window,
        with đời computed from the graph (thủy tổ = đời 1).

        ``get_ancestors_flat`` is per-lineage-edge, not deduplicated: under pedigree
        collapse (an ancestor reachable via two different parents of the focus person)
        the same person can appear more than once, at one or more depths. The
        breadcrumb dedupes by person id, keeping the shallowest (minimum-depth)
        occurrence — rows arrive depth ASC, so the first-seen id is that occurrence."""
        if not await self._repo.person_in_clan(query.person_id, query.clan_id):
            raise EntityNotFoundError("person_not_found")

        chain = await self._repo.get_ancestors_flat(
            query.person_id, query.clan_id, query.ancestor_depth
        )
        founder_id = await self._repo.find_clan_founder(query.clan_id)
        founder_str = str(founder_id) if founder_id is not None else None

        doi = await self._repo.get_generation_map(query.clan_id)
        focus_entry = doi.get(query.person_id)
        generation_of_focus = focus_entry.generation if focus_entry else None

        seen: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for row in chain:
            if row["depth"] < 1 or row["id"] in seen:
                continue
            seen.add(row["id"])
            deduped.append(row)

        ancestors: list[dict[str, Any]] = []
        for row in sorted(deduped, key=lambda r: -r["depth"]):
            entry = doi.get(uuid.UUID(row["id"]))
            ancestors.append(
                {
                    "id": row["id"],
                    "full_name": row["full_name"],
                    "gender": row["gender"],
                    "birth_date": row["birth_date"],
                    "death_date": row["death_date"],
                    "avatar_url": row["avatar_url"],
                    "generation": entry.generation if entry else None,
                    "is_founder": row["id"] == founder_str,
                }
            )

        focus_subtree = await self._repo.build_focus_view(
            query.person_id, query.clan_id, query.descendant_depth, doi
        )
        if not focus_subtree:
            # Soft-delete TOCTOU: the membership gate above passed, but the focus person
            # (or the whole subtree) vanished by the time build_focus_view ran, so it
            # returned {}. Surface this as a normal 404 instead of a 500 in
            # FocusView.model_validate. A focus person WITH no descendants still yields a
            # populated lone-node dict (truthy), so this only catches the empty case.
            raise EntityNotFoundError("person_not_found")

        return {
            "focus_person_id": str(query.person_id),
            "generation_of_focus": generation_of_focus,
            "ancestors": ancestors,
            "focus_subtree": focus_subtree,
        }

    async def find_path(self, query: FindPath) -> dict[str, Any]:
        """Find the relationship path between two persons."""
        if query.from_id == query.to_id:
            raise BusinessRuleViolation("same_person_path")

        for pid in [query.from_id, query.to_id]:
            if not await self._repo.person_in_clan(pid, query.clan_id):
                raise EntityNotFoundError("person_not_found")

        path = await self._repo.find_path(query.from_id, query.to_id, query.clan_id)
        if not path:
            return {"path": [], "description": None, "found": False}

        description = describe_relationship(path)

        # birth_date/precision are carried only for the descriptor's age logic — strip
        # them so the /path response shape is unchanged (they were never exposed).
        for step in path:
            step.pop("birth_date", None)
            step.pop("birth_date_precision", None)

        return {"path": path, "description": description, "found": True}


def _count_nodes(tree: dict[str, Any]) -> int:
    count = 1
    for child in tree.get("children", []):
        count += _count_nodes(child)
    return count


def _max_depth(tree: dict[str, Any]) -> int:
    children = tree.get("children", [])
    if not children:
        return 0
    return 1 + max(_max_depth(c) for c in children)
