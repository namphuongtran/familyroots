"""Pure GEDCOM 5.5.1 serializer — the interop view of a clan's archive.

No I/O, no FastAPI/SQLAlchemy imports: this module only shapes plain dicts
(the same port row dicts consumed by `app.services.clan_export`) into a
GEDCOM 5.5.1 text document. Unlike the JSON archive, which is lossless and
keeps soft-deleted rows (flagged), GEDCOM is the interop view: soft-deleted
persons/marriages/parent_child edges are dropped entirely so downstream
genealogy software never has to reason about `is_deleted`.

NOTE (import-linter): kept out of `app.application.export.handlers` for the
same reason as `app.services.clan_export` — see that module's docstring.
The composition root (`app.infrastructure.dependencies`) injects
`build_gedcom` into `ExportQueryHandler` as a plain callable.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date
from typing import Any

_MAX_LINE_LEN = 240  # binding constraint: fold well under the 255-char hard limit

_MONTHS = {
    1: "JAN",
    2: "FEB",
    3: "MAR",
    4: "APR",
    5: "MAY",
    6: "JUN",
    7: "JUL",
    8: "AUG",
    9: "SEP",
    10: "OCT",
    11: "NOV",
    12: "DEC",
}


def build_gedcom(
    clan: dict[str, Any],
    persons: list[dict[str, Any]],
    marriages: list[dict[str, Any]],
    parent_child: list[dict[str, Any]],
    branches: list[dict[str, Any]],
    generation_map: dict[uuid.UUID, int],
) -> str:
    """Render the clan archive as a GEDCOM 5.5.1 document (pure — no I/O).

    ``persons``/``marriages``/``parent_child`` are the same
    ``ExportQueryPort`` row dicts consumed by ``build_clan_export`` — soft-
    deleted rows (``is_deleted``) are filtered out here rather than kept.
    ``persons`` rows carry the joined membership field ``branch_id``, used
    to resolve the Vietnamese "chi" (branch) note. xref numbering
    (``@In@``/``@Fn@``) is assigned deterministically (sorted by uuid /
    marriage uuid / synthesized couple key) so repeated exports of the same
    data are byte-identical.
    """
    live_persons = [p for p in persons if not p.get("is_deleted")]
    sorted_persons = sorted(live_persons, key=lambda p: str(p["id"]))
    persons_by_id = {p["id"]: p for p in sorted_persons}
    indi_xref = {p["id"]: f"@I{i + 1}@" for i, p in enumerate(sorted_persons)}
    branch_name_by_id = {b["id"]: b.get("name") for b in branches}

    live_marriages = [
        m
        for m in marriages
        if not m.get("is_deleted")
        and m["person1_id"] in persons_by_id
        and m["person2_id"] in persons_by_id
    ]
    live_edges = [
        e
        for e in parent_child
        if not e.get("is_deleted")
        and e["parent_id"] in persons_by_id
        and e["child_id"] in persons_by_id
    ]

    families, family_by_pair = _build_marriage_families(live_marriages, persons_by_id)
    child_famc = _link_children(live_edges, persons_by_id, families, family_by_pair)
    spouse_fams = _spouse_families(families)
    _assign_family_xrefs(families)  # sorts `families` in place, then stamps `_xref`

    lines: list[str] = list(_HEADER_LINES)
    for person in sorted_persons:
        lines.extend(
            _indi_lines(
                person,
                indi_xref[person["id"]],
                generation_map,
                branch_name_by_id,
                child_famc.get(person["id"], []),
                spouse_fams.get(person["id"], []),
            )
        )
    for fam in families:
        lines.extend(_fam_lines(fam, indi_xref))
    lines.append("0 TRLR")
    return "\n".join(lines)


_HEADER_LINES = (
    "0 HEAD",
    "1 SOUR FamilyRoots",
    "1 GEDC",
    "2 VERS 5.5.1",
    "2 FORM LINEAGE-LINKED",
    "1 CHAR UTF-8",
)


def _build_marriage_families(
    live_marriages: list[dict[str, Any]],
    persons_by_id: dict[Any, dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[frozenset[Any], dict[str, Any]]]:
    """One FAM per non-deleted marriage, HUSB/WIFE assigned by gender."""
    families: list[dict[str, Any]] = []
    family_by_pair: dict[frozenset[Any], dict[str, Any]] = {}
    for marriage in live_marriages:
        p1, p2 = marriage["person1_id"], marriage["person2_id"]
        husb, wife = _husb_wife(
            p1, persons_by_id[p1].get("gender"), p2, persons_by_id[p2].get("gender")
        )
        fam = {
            "husb": husb,
            "wife": wife,
            "marriage": marriage,
            "children": [],
            "_sort_key": (0, str(marriage["id"])),
        }
        families.append(fam)
        family_by_pair[frozenset({p1, p2})] = fam
    return families, family_by_pair


def _husb_wife(p1: Any, gender1: str | None, p2: Any, gender2: str | None) -> tuple[Any, Any]:
    """HUSB/WIFE by gender; fallback: person1 -> HUSB."""
    if gender1 == "female" and gender2 == "male":
        return p2, p1
    return p1, p2


def _link_children(
    live_edges: list[dict[str, Any]],
    persons_by_id: dict[Any, dict[str, Any]],
    families: list[dict[str, Any]],
    family_by_pair: dict[frozenset[Any], dict[str, Any]],
) -> dict[Any, list[tuple[dict[str, Any], str | None]]]:
    """Group parent_child edges by child, matching (father, mother) pairs
    against existing marriage FAMs and creating single-parent FAMs (or
    synthetic couple FAMs, for an unmarried pair) for the rest. A given
    single parent's children all share the same single-parent FAM."""
    child_groups: dict[Any, list[tuple[Any, str]]] = defaultdict(list)
    for edge in live_edges:
        child_groups[edge["child_id"]].append(
            (edge["parent_id"], edge.get("relationship_type", "biological"))
        )

    child_famc: dict[Any, list[tuple[dict[str, Any], str | None]]] = defaultdict(list)

    for child_id in sorted(child_groups, key=str):
        unique_parents: dict[Any, str] = {}
        for parent_id, rel in child_groups[child_id]:
            unique_parents.setdefault(parent_id, rel)
        parent_items = sorted(unique_parents.items(), key=lambda kv: str(kv[0]))

        while len(parent_items) >= 2:
            (p_a, rel_a), (p_b, rel_b) = parent_items[0], parent_items[1]
            parent_items = parent_items[2:]
            pair_key = frozenset({p_a, p_b})
            fam = family_by_pair.get(pair_key)
            if fam is None:
                husb, wife = _husb_wife(
                    p_a,
                    persons_by_id[p_a].get("gender"),
                    p_b,
                    persons_by_id[p_b].get("gender"),
                )
                fam = {
                    "husb": husb,
                    "wife": wife,
                    "marriage": None,
                    "children": [],
                    "_sort_key": (1, str(husb), str(wife)),
                }
                families.append(fam)
                family_by_pair[pair_key] = fam
            pedi = rel_a if rel_a != "biological" else (rel_b if rel_b != "biological" else None)
            fam["children"].append(child_id)
            child_famc[child_id].append((fam, pedi))

        for parent_id, rel in parent_items:  # 0 or 1 leftover parent
            single_key = frozenset({parent_id})
            fam = family_by_pair.get(single_key)
            if fam is None:
                gender = persons_by_id[parent_id].get("gender")
                is_husb = gender != "female"
                fam = {
                    "husb": parent_id if is_husb else None,
                    "wife": parent_id if not is_husb else None,
                    "marriage": None,
                    "children": [],
                    "_sort_key": (2, str(parent_id)),
                }
                families.append(fam)
                family_by_pair[single_key] = fam
            pedi = rel if rel != "biological" else None
            fam["children"].append(child_id)
            child_famc[child_id].append((fam, pedi))

    return child_famc


def _spouse_families(families: list[dict[str, Any]]) -> dict[Any, list[dict[str, Any]]]:
    spouse_fams: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for fam in families:
        if fam.get("husb") is not None:
            spouse_fams[fam["husb"]].append(fam)
        if fam.get("wife") is not None:
            spouse_fams[fam["wife"]].append(fam)
    return spouse_fams


def _assign_family_xrefs(families: list[dict[str, Any]]) -> None:
    """Sort `families` in place by its deterministic `_sort_key`, then stamp
    `@Fn@` xrefs in that order — marriage-backed FAMs (keyed by marriage
    uuid) sort before synthetic couple/single-parent FAMs."""
    families.sort(key=lambda f: f["_sort_key"])
    for i, fam in enumerate(families):
        fam["_xref"] = f"@F{i + 1}@"


def _indi_lines(
    person: dict[str, Any],
    xref: str,
    generation_map: dict[Any, int],
    branch_name_by_id: dict[Any, str | None],
    famc_links: list[tuple[dict[str, Any], str | None]],
    fams_links: list[dict[str, Any]],
) -> list[str]:
    lines = [f"0 {xref} INDI"]
    lines.extend(_fold(1, "NAME", person["full_name"]))
    lines.append(f"1 SEX {_sex(person.get('gender'))}")

    if person.get("birth_date") is not None:
        lines.append("1 BIRT")
        date_str = _format_date(person["birth_date"], person.get("birth_date_precision"))
        if date_str:
            lines.extend(_fold(2, "DATE", date_str))

    if person.get("death_date") is not None:
        lines.append("1 DEAT")
        date_str = _format_date(person["death_date"], person.get("death_date_precision"))
        if date_str:
            lines.extend(_fold(2, "DATE", date_str))

    meta_pairs: list[tuple[str, str]] = []
    if person.get("birth_name"):
        meta_pairs.append(("ten_huy", person["birth_name"]))
    if person.get("posthumous_name"):
        meta_pairs.append(("ten_thuy", person["posthumous_name"]))
    generation = generation_map.get(person["id"])
    if generation is not None:
        meta_pairs.append(("doi", str(generation)))
    branch_name = branch_name_by_id.get(person.get("branch_id"))
    if branch_name:
        meta_pairs.append(("chi", branch_name))
    if person.get("lunar_birth_date"):
        meta_pairs.append(("lunar_birth", person["lunar_birth_date"]))
    if meta_pairs:
        note = "FamilyRoots: " + "; ".join(f"{k}={v}" for k, v in meta_pairs)
        lines.extend(_fold(1, "NOTE", note))

    if person.get("biography"):
        lines.extend(_fold(1, "NOTE", person["biography"]))

    for fam, pedi in sorted(famc_links, key=lambda item: item[0]["_xref"]):
        lines.append(f"1 FAMC {fam['_xref']}")
        if pedi:
            lines.append(f"2 PEDI {pedi}")

    for fam in sorted(fams_links, key=lambda f: f["_xref"]):
        lines.append(f"1 FAMS {fam['_xref']}")

    return lines


def _fam_lines(fam: dict[str, Any], indi_xref: dict[Any, str]) -> list[str]:
    lines = [f"0 {fam['_xref']} FAM"]
    if fam.get("husb") is not None:
        lines.append(f"1 HUSB {indi_xref[fam['husb']]}")
    if fam.get("wife") is not None:
        lines.append(f"1 WIFE {indi_xref[fam['wife']]}")

    marriage = fam.get("marriage")
    if marriage is not None:
        if marriage.get("status") == "divorced":
            lines.append("1 DIV")
        if marriage.get("spouse_order") is not None:
            note = f"spouse_order={marriage['spouse_order']}; status={marriage.get('status')}"
            lines.extend(_fold(1, "NOTE", note))

    for child_id in sorted(fam["children"], key=str):
        lines.append(f"1 CHIL {indi_xref[child_id]}")

    return lines


def _sex(gender: str | None) -> str:
    if gender == "male":
        return "M"
    if gender == "female":
        return "F"
    return "U"


def _format_date(value: date | None, precision: str | None) -> str | None:
    if value is None or precision in (None, "unknown"):
        return None
    if precision == "exact":
        return f"{value.day} {_MONTHS[value.month]} {value.year}"
    if precision == "month":
        return f"{_MONTHS[value.month]} {value.year}"
    if precision == "year":
        return str(value.year)
    if precision == "circa":
        return f"ABT {value.year}"
    return None


def _fold(level: int, tag: str, value: str) -> list[str]:
    """Emit a `LEVEL TAG value` line, folding with CONC continuations when
    the line would exceed `_MAX_LINE_LEN` chars (binding constraint: fold at
    240, comfortably under the 255-char GEDCOM line limit)."""
    prefix = f"{level} {tag} "
    if len(prefix) + len(value) <= _MAX_LINE_LEN:
        return [prefix + value]

    first_len = _MAX_LINE_LEN - len(prefix)
    lines = [prefix + value[:first_len]]
    remaining = value[first_len:]
    conc_prefix = f"{level + 1} CONC "
    chunk_len = _MAX_LINE_LEN - len(conc_prefix)
    while remaining:
        lines.append(conc_prefix + remaining[:chunk_len])
        remaining = remaining[chunk_len:]
    return lines
