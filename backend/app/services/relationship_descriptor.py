"""Kinship term generator — describes the relationship between two members.

Given a path from person A to person B (from ``find_relationship_path``), generate a
localized Vietnamese kinship term. Vietnamese kinship is specific: the right word
depends on **gender**, **paternal-vs-maternal side**, and **relative age**. This
resolver uses:

- each path node's ``gender`` (already carried by the path),
- the *intermediate* node's gender for side (through father → paternal/nội, through
  mother → maternal/ngoại), via ``_side``, and
- ``birth_date`` for the older/younger distinctions (bác vs chú; anh/chị vs em), via
  ``_age_rank``.

Correctness principle — "never wrong, only less specific": whenever the distinguishing
data is missing OR unreliable, the resolver returns ``None`` and the caller falls back
to the age/gender-agnostic generic term (``KINSHIP_MAP``). In particular an APPROXIMATE
birth date, a missing date, or two EQUAL dates never produce a hard older/younger claim.

Known limitation: the path is a single shortest path, so half-siblings and full siblings
are both ``("parent","child")`` and share the base term (anh/chị/em) — the
cùng-cha-khác-mẹ qualifier is out of scope.
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
    # my parent's spouse who is NOT my parent = a STEP-parent (a bio parent is reached
    # via the direct ("parent",) edge, so a shortest ("parent","spouse") path is a
    # step-parent, not a parent-in-law — that is ("spouse","parent")).
    ("parent", "spouse"): "kinship.step_parent",
    ("spouse", "child"): "kinship.stepchild",
    ("child", "child"): "kinship.grandchild",
    ("parent", "parent"): "kinship.grandparent",
    ("parent", "parent", "child"): "kinship.uncle_aunt",
    ("parent", "parent", "child", "child"): "kinship.cousin",
    ("child", "spouse"): "kinship.child_in_law",
    ("spouse", "parent"): "kinship.parent_in_law",
    ("parent", "parent", "parent"): "kinship.great_grandparent",
    ("child", "child", "child"): "kinship.great_grandchild",
    ("parent", "parent", "child", "spouse"): "kinship.uncle_aunt_in_law",
}

# Every specific key the resolver can emit — single source of truth shared with the
# i18n-coverage test so a new term can't drift out of sync with the locale files.
SPECIFIC_KINSHIP_KEYS: frozenset[str] = frozenset(
    {
        "kinship.father",
        "kinship.mother",
        "kinship.husband",
        "kinship.wife",
        "kinship.son",
        "kinship.daughter",
        "kinship.older_brother",
        "kinship.older_sister",
        "kinship.younger_brother",
        "kinship.younger_sister",
        "kinship.paternal_grandfather",
        "kinship.paternal_grandmother",
        "kinship.maternal_grandfather",
        "kinship.maternal_grandmother",
        "kinship.grandson",
        "kinship.granddaughter",
        "kinship.paternal_uncle_older",
        "kinship.paternal_uncle_younger",
        "kinship.paternal_aunt_older",
        "kinship.paternal_aunt_younger",
        "kinship.maternal_uncle",
        "kinship.maternal_aunt",
        # phase 2
        "kinship.cousin_older_brother",
        "kinship.cousin_older_sister",
        "kinship.cousin_younger",
        "kinship.paternal_great_grandfather",
        "kinship.paternal_great_grandmother",
        "kinship.maternal_great_grandfather",
        "kinship.maternal_great_grandmother",
        "kinship.aunt_in_law_paternal_older",
        "kinship.aunt_in_law_paternal_younger",
        "kinship.aunt_in_law_maternal",
        "kinship.uncle_in_law",
        # phase 3
        "kinship.daughter_in_law",
        "kinship.son_in_law",
        "kinship.father_in_law_husband",
        "kinship.mother_in_law_husband",
        "kinship.father_in_law_wife",
        "kinship.mother_in_law_wife",
        "kinship.step_father",
        "kinship.step_mother",
    }
)

_MALE = "male"
_FEMALE = "female"


def _gender(node: dict[str, Any]) -> str:
    return node.get("gender") or "unknown"


def _side(linking_parent: dict[str, Any]) -> str | None:
    """Paternal (through father) / maternal (through mother) / None if unknown."""
    g = _gender(linking_parent)
    if g == _MALE:
        return "paternal"
    if g == _FEMALE:
        return "maternal"
    return None


def _age_rank(a: dict[str, Any], b: dict[str, Any]) -> str | None:
    """``"older"``/``"younger"`` of ``a`` relative to ``b``, or ``None`` when it cannot
    be asserted safely.

    Returns None if either birth_date is missing, either date is APPROXIMATE (an
    estimate must not become a hard Bác/Chú or Anh/Em claim), or the dates are EQUAL
    (twins / unknown-but-equal → do not guess).
    """
    da, db = a.get("birth_date"), b.get("birth_date")
    if not isinstance(da, date) or not isinstance(db, date):
        return None
    if a.get("birth_date_approx") or b.get("birth_date_approx"):
        return None
    if da == db:
        return None
    return "older" if da < db else "younger"


def _specific_key(edges: tuple[str, ...], path: list[dict[str, Any]]) -> str | None:
    """Resolve a gender/side/age-specific kinship key, or None to use the generic term.

    Returning None (rather than a wrong guess) is deliberate — the caller falls back to
    the age/gender-agnostic term whenever the distinguishing data is absent or unreliable.
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
        rank = _age_rank(target, source)
        if rank == "older":
            return {_MALE: "kinship.older_brother", _FEMALE: "kinship.older_sister"}.get(tg)
        if rank == "younger":
            return {_MALE: "kinship.younger_brother", _FEMALE: "kinship.younger_sister"}.get(tg)
        return None

    if edges == ("child", "child"):  # grandchild
        return {_MALE: "kinship.grandson", _FEMALE: "kinship.granddaughter"}.get(tg)

    if edges == ("parent", "parent"):  # grandparent — side from the linking parent
        side = _side(path[1])
        if side == "paternal":
            return {
                _MALE: "kinship.paternal_grandfather",
                _FEMALE: "kinship.paternal_grandmother",
            }.get(tg)
        if side == "maternal":
            return {
                _MALE: "kinship.maternal_grandfather",
                _FEMALE: "kinship.maternal_grandmother",
            }.get(tg)
        return None

    if edges == ("parent", "parent", "child"):  # uncle/aunt — side from my linking parent
        my_parent = path[1]
        side = _side(my_parent)
        if side == "paternal":  # father's sibling — bác/chú/cô use age vs father
            rank = _age_rank(target, my_parent)
            if rank is None:
                return None
            older = rank == "older"
            if tg == _MALE:
                return "kinship.paternal_uncle_older" if older else "kinship.paternal_uncle_younger"
            if tg == _FEMALE:
                return "kinship.paternal_aunt_older" if older else "kinship.paternal_aunt_younger"
            return None
        if side == "maternal":  # mother's sibling — cậu/dì, age-agnostic
            return {_MALE: "kinship.maternal_uncle", _FEMALE: "kinship.maternal_aunt"}.get(tg)
        return None

    if edges == ("parent", "parent", "child", "child"):  # cousin — anh/chị/em họ, age vs me
        rank = _age_rank(target, source)
        if rank == "older":
            return {
                _MALE: "kinship.cousin_older_brother",
                _FEMALE: "kinship.cousin_older_sister",
            }.get(tg)
        if rank == "younger":
            return "kinship.cousin_younger"  # em họ — gender-neutral in common usage
        return None

    if edges == ("parent", "parent", "parent"):  # great-grandparent — cụ, side + gender
        side = _side(path[1])
        if side == "paternal":
            return {
                _MALE: "kinship.paternal_great_grandfather",
                _FEMALE: "kinship.paternal_great_grandmother",
            }.get(tg)
        if side == "maternal":
            return {
                _MALE: "kinship.maternal_great_grandfather",
                _FEMALE: "kinship.maternal_great_grandmother",
            }.get(tg)
        return None

    if edges == ("parent", "parent", "child", "spouse"):  # spouse of a parent's sibling
        my_parent = path[1]
        the_sibling = path[3]  # my parent's blood sibling; target (path[4]) is their spouse
        side = _side(my_parent)
        sg = _gender(the_sibling)
        # The in-law terms are gendered by role: a male sibling's spouse is his WIFE
        # (thím/bác gái/mợ), a female sibling's spouse is her HUSBAND (dượng). If the
        # recorded spouse gender contradicts that (a same-sex spouse), don't emit a
        # wrong gendered term — fall back to the generic (never wrong, only less specific).
        if sg == _MALE and tg != _FEMALE:
            return None
        if sg == _FEMALE and tg != _MALE:
            return None
        if side == "paternal":
            if sg == _MALE:  # father's brother's wife — thím (chú's) / bác gái (bác's), by age
                rank = _age_rank(the_sibling, my_parent)
                if rank is None:
                    return None
                return (
                    "kinship.aunt_in_law_paternal_older"
                    if rank == "older"
                    else "kinship.aunt_in_law_paternal_younger"
                )
            if sg == _FEMALE:  # father's sister's husband — dượng
                return "kinship.uncle_in_law"
            return None
        if side == "maternal":
            if sg == _MALE:  # mother's brother's wife — mợ
                return "kinship.aunt_in_law_maternal"
            if sg == _FEMALE:  # mother's sister's husband — dượng
                return "kinship.uncle_in_law"
            return None
        return None

    if edges == ("parent", "spouse"):  # my parent's spouse (not my parent) — step-parent
        return {_MALE: "kinship.step_father", _FEMALE: "kinship.step_mother"}.get(tg)

    if edges == ("child", "spouse"):  # my child's spouse — con dâu / con rể
        my_child = path[1]
        cg = _gender(my_child)
        # con dâu = son's WIFE, con rể = daughter's HUSBAND. A same-sex in-law child
        # (son's husband / daughter's wife) matches neither → generic.
        if cg == _MALE and tg == _FEMALE:
            return "kinship.daughter_in_law"
        if cg == _FEMALE and tg == _MALE:
            return "kinship.son_in_law"
        return None

    if edges == ("spouse", "parent"):  # my spouse's parent — bố/mẹ chồng | bố/mẹ vợ
        my_spouse = path[1]
        ss = _gender(my_spouse)  # side is my spouse's gender: husband → chồng, wife → vợ
        if ss == _MALE:  # husband's parent
            return {
                _MALE: "kinship.father_in_law_husband",
                _FEMALE: "kinship.mother_in_law_husband",
            }.get(tg)
        if ss == _FEMALE:  # wife's parent
            return {
                _MALE: "kinship.father_in_law_wife",
                _FEMALE: "kinship.mother_in_law_wife",
            }.get(tg)
        return None

    return None


def describe_relationship(path: list[dict[str, Any]]) -> str:
    """Return a localized relationship description from a path of steps.

    ``path`` is a list of dicts with ``edge_type`` (steps 1..N) and ``gender`` /
    ``birth_date`` / ``birth_date_approx`` used to pick the specific Vietnamese term.
    The localized string uses the request locale via ``t()``.
    """
    if not path or len(path) < 2:
        return t("kinship.same_person")

    edges = tuple(step["edge_type"] for step in path[1:] if step.get("edge_type"))

    key = _specific_key(edges, path) or KINSHIP_MAP.get(edges)
    if key:
        return t(key)

    degree = len(path) - 1
    return t("kinship.distant_relative", degree=degree)
