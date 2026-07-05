"""Kinship term generator — describes the relationship between two members.

Given a path from person A to person B (from ``find_relationship_path``), generate a
localized Vietnamese kinship term. Vietnamese kinship is specific: the right word
depends on **gender**, **paternal-vs-maternal side**, and **relative age**. This
resolver uses:

- each path node's ``gender`` (already carried by the path), and
- ``birth_date`` (threaded through the path) for the older/younger distinctions
  (bác vs chú; anh/chị vs em).

Paternal-vs-maternal side is derived from the *intermediate* node's gender (through
the father → paternal/nội; through the mother → maternal/ngoại). When the data needed
for a specific term is missing (unknown gender, unknown side, or missing birth dates)
it falls back to the age/gender-agnostic generic term via ``KINSHIP_MAP`` — the label
is always safe, never wrong.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from app.services.translator import t

# Age/gender-agnostic fallback per edge sequence — used when a specific term can't be
# resolved (missing gender/side/birth_date) and for relations not yet specialized.
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

_MALE = "male"
_FEMALE = "female"


def _gender(node: dict[str, Any]) -> str:
    return node.get("gender") or "unknown"


def _is_older(a: dict[str, Any], b: dict[str, Any]) -> bool | None:
    """Is ``a`` older than ``b`` (earlier birth_date)? None if either date is unknown."""
    da, db = a.get("birth_date"), b.get("birth_date")
    if not isinstance(da, date) or not isinstance(db, date):
        return None
    return da < db


def _specific_key(edges: tuple[str, ...], path: list[dict[str, Any]]) -> str | None:
    """Resolve a gender/side/age-specific kinship key, or None to use the generic term.

    Returning None (rather than a wrong guess) is deliberate — the caller falls back to
    the age/gender-agnostic term whenever the distinguishing data is absent.
    """
    source, target = path[0], path[-1]
    tg = _gender(target)

    if edges == ("parent",):
        return {_MALE: "kinship.father", _FEMALE: "kinship.mother"}.get(tg)

    if edges == ("child",):
        return {_MALE: "kinship.son", _FEMALE: "kinship.daughter"}.get(tg)

    if edges == ("spouse",):
        return {_MALE: "kinship.husband", _FEMALE: "kinship.wife"}.get(tg)

    if edges == ("parent", "child"):  # sibling — older/younger vs me
        older = _is_older(target, source)
        if older is None:
            return None
        if older:
            return {_MALE: "kinship.older_brother", _FEMALE: "kinship.older_sister"}.get(tg)
        return {_MALE: "kinship.younger_brother", _FEMALE: "kinship.younger_sister"}.get(tg)

    if edges == ("child", "child"):  # grandchild
        return {_MALE: "kinship.grandson", _FEMALE: "kinship.granddaughter"}.get(tg)

    if edges == ("parent", "parent"):  # grandparent — side from the linking parent
        side = _gender(path[1])
        if side == _MALE:  # through father → paternal (nội)
            return {
                _MALE: "kinship.paternal_grandfather",
                _FEMALE: "kinship.paternal_grandmother",
            }.get(tg)
        if side == _FEMALE:  # through mother → maternal (ngoại)
            return {
                _MALE: "kinship.maternal_grandfather",
                _FEMALE: "kinship.maternal_grandmother",
            }.get(tg)
        return None

    if edges == ("parent", "parent", "child"):  # uncle/aunt — side from my linking parent
        my_parent = path[1]
        side = _gender(my_parent)
        if side == _MALE:  # father's sibling (paternal) — bác/chú/cô use age vs father
            older = _is_older(target, my_parent)
            if older is None:
                return None
            if tg == _MALE:
                return "kinship.paternal_uncle_older" if older else "kinship.paternal_uncle_younger"
            if tg == _FEMALE:
                return "kinship.paternal_aunt_older" if older else "kinship.paternal_aunt_younger"
            return None
        if side == _FEMALE:  # mother's sibling (maternal) — cậu/dì, age-agnostic
            return {_MALE: "kinship.maternal_uncle", _FEMALE: "kinship.maternal_aunt"}.get(tg)
        return None

    return None


def describe_relationship(
    path: list[dict[str, Any]],
    from_gender: str = "unknown",
    to_gender: str = "unknown",
    locale: str = "vi",
) -> str:
    """Return a localized relationship description from a path of steps.

    ``path`` is a list of dicts with at least ``edge_type``; steps also carry
    ``gender`` and ``birth_date`` used to pick the specific Vietnamese term. The
    ``from_gender``/``to_gender``/``locale`` parameters are retained for backward
    compatibility but the description is derived from the path itself.
    """
    if not path or len(path) < 2:
        return t("kinship.same_person")

    edges = tuple(step["edge_type"] for step in path[1:] if step.get("edge_type"))

    key = _specific_key(edges, path) or KINSHIP_MAP.get(edges)
    if key:
        return t(key)

    degree = len(path) - 1
    return t("kinship.distant_relative", degree=degree)
