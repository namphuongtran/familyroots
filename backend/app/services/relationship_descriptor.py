"""Kinship term generator — describes the relationship between two members.

Given a path from person A to person B (from ``find_relationship_path``),
generates a human-readable localized description using edge-sequence
pattern matching and the ``t()`` i18n function.
"""

from typing import Any

from app.services.translator import t

# Keys: tuple of edge directions from the source's perspective.
# Values: i18n key for the kinship term.
KINSHIP_MAP: dict[tuple[str, ...], str] = {
    ("child",): "kinship.child",
    ("parent",): "kinship.parent",
    ("spouse",): "kinship.spouse",
    ("parent", "child"): "kinship.sibling",
    ("parent", "spouse"): "kinship.parent_in_law",
    ("spouse", "child"): "kinship.stepchild",
    ("child", "child"): "kinship.grandchild",
    ("parent", "parent"): "kinship.grandparent",
    ("parent", "parent", "child"): "kinship.uncle_aunt",
    ("parent", "parent", "child", "child"): "kinship.cousin",
    ("child", "spouse"): "kinship.child_in_law",
    ("spouse", "parent"): "kinship.parent_in_law",
    ("parent", "parent", "parent"): "kinship.great_grandparent",
    ("child", "child", "child"): "kinship.great_grandchild",
}


def describe_relationship(
    path: list[dict[str, Any]],
    from_gender: str = "unknown",
    to_gender: str = "unknown",
    locale: str = "vi",
) -> str:
    """Return a localized relationship description from a path of steps.

    ``path`` is a list of dicts with at least ``edge_type`` (str).
    The first element is the source person (no edge), so edges start
    at index 1.
    """
    if not path or len(path) < 2:
        return t("kinship.same_person")

    edge_sequence = tuple(step["edge_type"] for step in path[1:] if step.get("edge_type"))
    kinship_key = KINSHIP_MAP.get(edge_sequence)

    if kinship_key:
        return t(kinship_key)

    degree = len(path) - 1
    return t("kinship.distant_relative", degree=degree)
