"""M6 RED tests: GEDCOM parent-family grouping must respect relationship_type.

The pure serializer's `_link_children` sorts a child's parents by UUID string
order and pairs them TWO-AT-A-TIME, ignoring `relationship_type` / gender /
marriage. So a child with a biological mother + biological father + adoptive
father can be emitted with a FAM pairing e.g. (biological_father,
adoptive_father) as HUSB/WIFE — a couple that never existed.

These tests assert the DESIRED post-fix behavior: parents are grouped by
relationship_type; two same-type parents form ONE couple FAM (using a real
marriage FAM when they are married), a lone same-type parent forms a
single-parent FAM, and two parents of DIFFERENT types are NEVER paired. A
child gets one `1 FAMC` per family unit (birth family = no PEDI; adoptive
family = `2 PEDI adopted`).

Fixtures/parse helpers mirror `tests/unit/test_gedcom_export.py` exactly.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.services.gedcom_export import build_gedcom

pytestmark = pytest.mark.unit


# --- fixtures (same dict shapes as tests/unit/test_gedcom_export.py) --------


def _clan() -> dict[str, Any]:
    return {"id": uuid.uuid4(), "name": "Họ Nguyễn", "slug": "ho-nguyen"}


def _person(person_id: uuid.UUID | None = None, **overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": person_id or uuid.uuid4(),
        "full_name": "Nguyễn Văn A",
        "gender": "unknown",
        "birth_date": None,
        "birth_date_precision": "unknown",
        "death_date": None,
        "death_date_precision": "unknown",
        "birth_name": None,
        "posthumous_name": None,
        "lunar_birth_date": None,
        "biography": None,
        "is_deleted": False,
        "branch_id": None,
    }
    row.update(overrides)
    return row


def _marriage(person1_id: uuid.UUID, person2_id: uuid.UUID, **overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": uuid.uuid4(),
        "person1_id": person1_id,
        "person2_id": person2_id,
        "status": "married",
        "spouse_order": None,
        "is_deleted": False,
    }
    row.update(overrides)
    return row


def _edge(parent_id: uuid.UUID, child_id: uuid.UUID, **overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": uuid.uuid4(),
        "parent_id": parent_id,
        "child_id": child_id,
        "relationship_type": "biological",
        "is_deleted": False,
    }
    row.update(overrides)
    return row


# --- GEDCOM parse helpers ---------------------------------------------------


def _records(gedcom: str) -> list[list[str]]:
    """Split a GEDCOM document into its `0 @xref@ TAG` records (each a list of lines)."""
    records: list[list[str]] = []
    current: list[str] = []
    for line in gedcom.split("\n"):
        if line.startswith("0 "):
            if current:
                records.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        records.append(current)
    return records


def _indi_xrefs(gedcom: str) -> dict[str, str]:
    """Map `full_name` -> its `@In@` xref."""
    xrefs: dict[str, str] = {}
    for rec in _records(gedcom):
        if rec[0].endswith(" INDI"):
            xref = rec[0].split()[1]
            name_line = next(line for line in rec if line.startswith("1 NAME "))
            xrefs[name_line[len("1 NAME ") :]] = xref
    return xrefs


def _indi_record(gedcom: str, xref: str) -> list[str]:
    for rec in _records(gedcom):
        if rec[0] == f"0 {xref} INDI":
            return rec
    raise KeyError(xref)


def _famc_links(indi_rec: list[str]) -> list[tuple[str, str | None]]:
    """Return (fam_xref, pedi_or_None) for each `1 FAMC` in an INDI record."""
    links: list[tuple[str, str | None]] = []
    for i, line in enumerate(indi_rec):
        if line.startswith("1 FAMC "):
            fam_xref = line.split()[2]
            pedi: str | None = None
            if i + 1 < len(indi_rec) and indi_rec[i + 1].startswith("2 PEDI "):
                pedi = indi_rec[i + 1][len("2 PEDI ") :]
            links.append((fam_xref, pedi))
    return links


def _fam_map(gedcom: str) -> dict[str, dict[str, Any]]:
    """Map FAM xref -> {husb, wife, chil(set)} from the emitted document."""
    fams: dict[str, dict[str, Any]] = {}
    for rec in _records(gedcom):
        if not rec[0].endswith(" FAM"):
            continue
        xref = rec[0].split()[1]
        husb: str | None = None
        wife: str | None = None
        chil: set[str] = set()
        for line in rec:
            if line.startswith("1 HUSB "):
                husb = line.split()[2]
            elif line.startswith("1 WIFE "):
                wife = line.split()[2]
            elif line.startswith("1 CHIL "):
                chil.add(line.split()[2])
        fams[xref] = {"husb": husb, "wife": wife, "chil": chil}
    return fams


def _spouse_pair(fam: dict[str, Any]) -> frozenset[str | None]:
    return frozenset({fam["husb"], fam["wife"]})


# --- Test 1: the RED — no invented cross-type couple ------------------------
#
# HOW THE RED IS FORCED: `_link_children` sorts a child's parents by UUID
# string order, then pairs them two-at-a-time. With three parents whose sorted
# order INTERLEAVES types, the first two (a biological parent + the adoptive
# father) become a synthetic couple FAM. We pick explicit constant UUIDs:
#
#   bio_father       = ...0001   -> sorts 1st
#   adoptive_father  = ...0002   -> sorts 2nd  (between the two biological ids)
#   bio_mother       = ...0003   -> sorts 3rd
#
# So today's sorted order is [bio_father, adoptive_father, bio_mother]; the code
# pairs (bio_father, adoptive_father) as ONE couple FAM (with PEDI adopted from
# the adoptive edge) and leaves bio_mother as a single-parent FAM — a couple
# that never existed. This test asserts the DESIRED structure (bio couple +
# adoptive single-parent), so it FAILS today.

_ID_BIO_FATHER = uuid.UUID("00000000-0000-0000-0000-000000000001")
_ID_ADOPT_FATHER = uuid.UUID("00000000-0000-0000-0000-000000000002")
_ID_BIO_MOTHER = uuid.UUID("00000000-0000-0000-0000-000000000003")
_ID_CHILD = uuid.UUID("00000000-0000-0000-0000-000000000004")


def test_no_invented_cross_type_couple() -> None:
    mother = _person(_ID_BIO_MOTHER, full_name="Bio Mother", gender="female")
    father = _person(_ID_BIO_FATHER, full_name="Bio Father", gender="male")
    adoptive = _person(_ID_ADOPT_FATHER, full_name="Adoptive Father", gender="male")
    child = _person(_ID_CHILD, full_name="Child")
    edges = [
        _edge(mother["id"], child["id"], relationship_type="biological"),
        _edge(father["id"], child["id"], relationship_type="biological"),
        _edge(adoptive["id"], child["id"], relationship_type="adopted"),
    ]
    gedcom = build_gedcom(_clan(), [mother, father, adoptive, child], [], edges, [], {})

    xr = _indi_xrefs(gedcom)
    m, f, a, c = (
        xr["Bio Mother"],
        xr["Bio Father"],
        xr["Adoptive Father"],
        xr["Child"],
    )
    fams = _fam_map(gedcom)

    # (a) exactly ONE FAM has BOTH biological parents as HUSB/WIFE, with C a child.
    bio_couples = [x for x, fm in fams.items() if _spouse_pair(fm) == frozenset({m, f})]
    assert len(bio_couples) == 1, f"expected one biological-couple FAM, got {fams}"
    assert c in fams[bio_couples[0]]["chil"]

    # (b) NO FAM pairs a biological parent together with the adoptive father.
    for x, fm in fams.items():
        pair = _spouse_pair(fm)
        assert not (a in pair and (m in pair or f in pair)), (
            f"invented cross-type couple in {x}: {fm}"
        )

    # (c) the adoptive father is in a single-parent FAM; C's FAMC to it is PEDI adopted.
    adopt_fams = [x for x, fm in fams.items() if _spouse_pair(fm) == frozenset({a, None})]
    assert len(adopt_fams) == 1, f"expected one single-parent adoptive FAM, got {fams}"
    assert c in fams[adopt_fams[0]]["chil"]
    links = _famc_links(_indi_record(gedcom, c))
    adopt_link = [(fam, pedi) for fam, pedi in links if fam == adopt_fams[0]]
    assert adopt_link and adopt_link[0][1] == "adopted", f"FAMC links: {links}"

    # (d) C has exactly TWO `1 FAMC` lines (bio couple + adoptive single-parent).
    assert len(links) == 2, f"expected 2 FAMC links, got {links}"


# --- Test 2: unmarried biological couple grouped (regression pin) -----------


def test_unmarried_bio_couple_grouped() -> None:
    father = _person(full_name="Cha", gender="male")
    mother = _person(full_name="Mẹ", gender="female")
    child = _person(full_name="Con")
    edges = [
        _edge(father["id"], child["id"], relationship_type="biological"),
        _edge(mother["id"], child["id"], relationship_type="biological"),
    ]
    gedcom = build_gedcom(_clan(), [father, mother, child], [], edges, [], {})

    xr = _indi_xrefs(gedcom)
    fams = _fam_map(gedcom)

    couples = [x for x, fm in fams.items() if _spouse_pair(fm) == frozenset({xr["Cha"], xr["Mẹ"]})]
    assert len(couples) == 1, f"expected one couple FAM, got {fams}"
    fam = fams[couples[0]]
    assert fam["husb"] == xr["Cha"]  # male -> HUSB
    assert fam["wife"] == xr["Mẹ"]  # female -> WIFE
    assert xr["Con"] in fam["chil"]

    links = _famc_links(_indi_record(gedcom, xr["Con"]))
    assert len(links) == 1
    assert links[0] == (couples[0], None)  # biological -> no PEDI


# --- Test 3: married biological couple uses the marriage FAM ----------------


def test_married_bio_couple_uses_marriage_fam() -> None:
    father = _person(full_name="Cha", gender="male")
    mother = _person(full_name="Mẹ", gender="female")
    child = _person(full_name="Con")
    marriage = _marriage(father["id"], mother["id"])
    edges = [
        _edge(father["id"], child["id"], relationship_type="biological"),
        _edge(mother["id"], child["id"], relationship_type="biological"),
    ]
    gedcom = build_gedcom(_clan(), [father, mother, child], [marriage], edges, [], {})

    xr = _indi_xrefs(gedcom)
    fams = _fam_map(gedcom)

    # Exactly one FAM contains both parents as spouses; the child attaches there.
    couples = [x for x, fm in fams.items() if _spouse_pair(fm) == frozenset({xr["Cha"], xr["Mẹ"]})]
    assert len(couples) == 1, f"expected a single marriage FAM, no synthetic dup, got {fams}"
    assert xr["Con"] in fams[couples[0]]["chil"]

    links = _famc_links(_indi_record(gedcom, xr["Con"]))
    assert links == [(couples[0], None)]


# --- Test 4: adoptive couple -> one FAM, PEDI adopted -----------------------


def test_adoptive_couple_one_fam() -> None:
    father = _person(full_name="Cha Nuôi", gender="male")
    mother = _person(full_name="Mẹ Nuôi", gender="female")
    child = _person(full_name="Con Nuôi")
    edges = [
        _edge(father["id"], child["id"], relationship_type="adopted"),
        _edge(mother["id"], child["id"], relationship_type="adopted"),
    ]
    gedcom = build_gedcom(_clan(), [father, mother, child], [], edges, [], {})

    xr = _indi_xrefs(gedcom)
    fams = _fam_map(gedcom)

    couples = [
        x
        for x, fm in fams.items()
        if _spouse_pair(fm) == frozenset({xr["Cha Nuôi"], xr["Mẹ Nuôi"]})
    ]
    assert len(couples) == 1, f"expected one adoptive-couple FAM, got {fams}"
    assert xr["Con Nuôi"] in fams[couples[0]]["chil"]

    links = _famc_links(_indi_record(gedcom, xr["Con Nuôi"]))
    assert len(links) == 1
    assert links[0] == (couples[0], "adopted")


# --- Test 5: single adoptive parent alongside a biological couple -----------
#
# Same interleaving trick as Test 1: pick UUIDs so the biological father and the
# adoptive mother sort adjacent, which today pairs them as a synthetic couple.

_ID5_BIO_FATHER = uuid.UUID("00000000-0000-0000-0000-000000000011")
_ID5_ADOPT_MOTHER = uuid.UUID("00000000-0000-0000-0000-000000000012")
_ID5_BIO_MOTHER = uuid.UUID("00000000-0000-0000-0000-000000000013")
_ID5_CHILD = uuid.UUID("00000000-0000-0000-0000-000000000014")


def test_single_adoptive_alongside_bio_couple() -> None:
    father = _person(_ID5_BIO_FATHER, full_name="Bio Father", gender="male")
    adopt_mother = _person(_ID5_ADOPT_MOTHER, full_name="Adoptive Mother", gender="female")
    mother = _person(_ID5_BIO_MOTHER, full_name="Bio Mother", gender="female")
    child = _person(_ID5_CHILD, full_name="Child")
    edges = [
        _edge(father["id"], child["id"], relationship_type="biological"),
        _edge(mother["id"], child["id"], relationship_type="biological"),
        _edge(adopt_mother["id"], child["id"], relationship_type="adopted"),
    ]
    gedcom = build_gedcom(_clan(), [father, adopt_mother, mother, child], [], edges, [], {})

    xr = _indi_xrefs(gedcom)
    m, f, am, c = (
        xr["Bio Mother"],
        xr["Bio Father"],
        xr["Adoptive Mother"],
        xr["Child"],
    )
    fams = _fam_map(gedcom)

    # No cross-type couple: the adoptive mother is never paired with a bio parent.
    for x, fm in fams.items():
        pair = _spouse_pair(fm)
        assert not (am in pair and (m in pair or f in pair)), (
            f"invented cross-type couple in {x}: {fm}"
        )

    # Biological couple FAM with the child.
    bio_couples = [x for x, fm in fams.items() if _spouse_pair(fm) == frozenset({m, f})]
    assert len(bio_couples) == 1, f"expected one biological-couple FAM, got {fams}"
    assert c in fams[bio_couples[0]]["chil"]

    # Adoptive single-parent FAM with the child.
    adopt_fams = [x for x, fm in fams.items() if _spouse_pair(fm) == frozenset({am, None})]
    assert len(adopt_fams) == 1, f"expected one single-parent adoptive FAM, got {fams}"
    assert c in fams[adopt_fams[0]]["chil"]

    # Exactly two FAMC: bio couple (no PEDI) + adoptive single-parent (PEDI adopted).
    links = dict(_famc_links(_indi_record(gedcom, c)))
    assert len(links) == 2, f"expected 2 FAMC links, got {links}"
    assert links[bio_couples[0]] is None
    assert links[adopt_fams[0]] == "adopted"


# --- Test 6: deterministic regardless of edge input order -------------------


def test_deterministic_regardless_of_edge_order() -> None:
    father = _person(full_name="Cha", gender="male")
    mother = _person(full_name="Mẹ", gender="female")
    adoptive = _person(full_name="Cha Nuôi", gender="male")
    child = _person(full_name="Con")
    persons = [father, mother, adoptive, child]

    edges_a = [
        _edge(father["id"], child["id"], relationship_type="biological"),
        _edge(mother["id"], child["id"], relationship_type="biological"),
        _edge(adoptive["id"], child["id"], relationship_type="adopted"),
    ]
    edges_b = [
        _edge(adoptive["id"], child["id"], relationship_type="adopted"),
        _edge(mother["id"], child["id"], relationship_type="biological"),
        _edge(father["id"], child["id"], relationship_type="biological"),
    ]

    clan = _clan()
    gedcom_1 = build_gedcom(clan, persons, [], edges_a, [], {})
    gedcom_2 = build_gedcom(clan, persons, [], edges_b, [], {})
    assert gedcom_1 == gedcom_2, "GEDCOM output must be byte-identical regardless of edge order"


def test_step_parent_emits_note_not_invalid_pedi() -> None:
    """`2 PEDI step` is invalid GEDCOM 5.5.1 ({adopted, birth, foster, sealing}). A step
    relationship must emit a NOTE under FAMC instead; adopted/foster stay valid PEDI."""
    child = _person(full_name="Con")
    step = _person(full_name="Cha Ghẻ")
    adoptive = _person(full_name="Cha Nuôi")
    foster = _person(full_name="Cha Đỡ Đầu")
    edges = [
        _edge(step["id"], child["id"], relationship_type="step"),
        _edge(adoptive["id"], child["id"], relationship_type="adopted"),
        _edge(foster["id"], child["id"], relationship_type="foster"),
    ]
    gedcom = build_gedcom(_clan(), [child, step, adoptive, foster], [], edges, [], {})

    # No invalid PEDI value anywhere.
    assert "2 PEDI step" not in gedcom
    # Valid PEDI values are still emitted for adopted/foster.
    assert "2 PEDI adopted" in gedcom
    assert "2 PEDI foster" in gedcom

    # The child's FAMC pedi values are only the valid ones (step → None, i.e. a NOTE).
    child_rec = _indi_record(gedcom, _indi_xrefs(gedcom)["Con"])
    pedis = {pedi for _, pedi in _famc_links(child_rec) if pedi is not None}
    assert pedis == {"adopted", "foster"}
    # The step relationship is documented via a NOTE (a valid GEDCOM structure).
    assert any(line.startswith("2 NOTE") and "step" in line for line in child_rec), child_rec
