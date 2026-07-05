"""Tree query handlers.

Orchestrate tree repository and relationship descriptor service.
"""

from __future__ import annotations

from typing import Any

from app.application.tree.queries import FindPath, GetAncestors, GetFullTree, GetSubtree
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

        tree = await self._repo.build_descendants_tree(
            root_id, query.clan_id, query.max_generations
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

        tree = await self._repo.build_descendants_tree(
            query.person_id, query.clan_id, query.max_generations
        )
        if not tree:
            raise EntityNotFoundError("tree_empty")

        return {
            "tree": tree,
            "total_persons": _count_nodes(tree),
            "total_generations": _max_depth(tree) + 1,
        }

    async def get_ancestors(self, query: GetAncestors) -> list[dict[str, Any]]:
        """Return the ancestor chain."""
        if not await self._repo.person_in_clan(query.person_id, query.clan_id):
            raise EntityNotFoundError("person_not_found")
        return await self._repo.get_ancestors(query.person_id, query.clan_id)

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

        # birth_date/_approx are carried only for the descriptor's age logic — strip
        # them so the /path response shape is unchanged (they were never exposed).
        for step in path:
            step.pop("birth_date", None)
            step.pop("birth_date_approx", None)

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
