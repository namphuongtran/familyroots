"""Unit tests for the pure GEDCOM 5.5.1 serializer (no I/O, no database).

Hand-built row dicts mirroring the shapes `ExportQueryPort` produces — see
`app.services.clan_export`'s sibling test file for the same convention.
"""

from __future__ import annotations

import re
import uuid
from datetime import date
from typing import Any

import pytest

from app.services.gedcom_export import build_gedcom

pytestmark = pytest.mark.unit


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


def _indi_blocks(gedcom: str) -> dict[str, str]:
    """Map `full_name` -> the joined text of that person's INDI record."""
    blocks: dict[str, str] = {}
    for rec in _records(gedcom):
        if rec[0].endswith(" INDI"):
            name_line = next(line for line in rec if line.startswith("1 NAME "))
            blocks[name_line[len("1 NAME ") :]] = "\n".join(rec)
    return blocks


def _indi_xrefs(gedcom: str) -> dict[str, str]:
    """Map `full_name` -> its `@In@` xref."""
    xrefs: dict[str, str] = {}
    for rec in _records(gedcom):
        if rec[0].endswith(" INDI"):
            xref = rec[0].split()[1]
            name_line = next(line for line in rec if line.startswith("1 NAME "))
            xrefs[name_line[len("1 NAME ") :]] = xref
    return xrefs


def _fam_records(gedcom: str) -> list[list[str]]:
    return [rec for rec in _records(gedcom) if rec[0].endswith(" FAM")]


def test_header_and_trailer_structure() -> None:
    gedcom = build_gedcom(_clan(), [], [], [], [], {})
    lines = gedcom.split("\n")
    assert lines[0] == "0 HEAD"
    assert "1 GEDC" in lines
    assert "2 VERS 5.5.1" in lines
    assert "1 CHAR UTF-8" in lines
    assert "1 SOUR FamilyRoots" in lines
    assert lines[-1] == "0 TRLR"


def test_indi_one_per_live_person_name_and_soft_deleted_excluded() -> None:
    alive = _person(full_name="Cụ Thủy Tổ")
    dead = _person(full_name="Người Đã Xóa", is_deleted=True)
    gedcom = build_gedcom(_clan(), [alive, dead], [], [], [], {})
    assert gedcom.count(" INDI") == 1
    assert "1 NAME Cụ Thủy Tổ" in gedcom
    assert "Người Đã Xóa" not in gedcom


def test_sex_mapping_from_gender() -> None:
    persons = [
        _person(gender="male"),
        _person(gender="female"),
        _person(gender="unknown"),
        _person(gender="something-else"),
    ]
    gedcom = build_gedcom(_clan(), persons, [], [], [], {})
    sex_lines = [line for line in gedcom.split("\n") if line.startswith("1 SEX")]
    assert sex_lines.count("1 SEX M") == 1
    assert sex_lines.count("1 SEX F") == 1
    assert sex_lines.count("1 SEX U") == 2  # unknown + unrecognized both fall back to U


def test_birth_date_precision_mapping() -> None:
    persons = [
        _person(full_name="Exact", birth_date=date(1975, 3, 10), birth_date_precision="exact"),
        _person(full_name="Year", birth_date=date(1975, 3, 10), birth_date_precision="year"),
        _person(full_name="Month", birth_date=date(1975, 3, 10), birth_date_precision="month"),
        _person(full_name="Circa", birth_date=date(1975, 3, 10), birth_date_precision="circa"),
        _person(full_name="Unknown", birth_date=date(1975, 3, 10), birth_date_precision="unknown"),
    ]
    gedcom = build_gedcom(_clan(), persons, [], [], [], {})
    blocks = _indi_blocks(gedcom)
    assert "2 DATE 10 MAR 1975" in blocks["Exact"]
    assert "2 DATE 1975" in blocks["Year"]
    assert "2 DATE MAR 1975" in blocks["Month"]
    assert "2 DATE ABT 1975" in blocks["Circa"]
    assert "1 BIRT" in blocks["Unknown"]
    assert "DATE" not in blocks["Unknown"]


def test_vietnamese_note_mapping() -> None:
    branch_id = uuid.uuid4()
    person_id = uuid.uuid4()
    person = _person(
        person_id=person_id,
        full_name="Cụ Tổ",
        birth_name="Nguyễn Văn Húy",
        posthumous_name="Nguyễn Văn Thụy",
        lunar_birth_date="15/08 Canh Thân",
        branch_id=branch_id,
    )
    branches = [{"id": branch_id, "name": "Chi Hai"}]
    gedcom = build_gedcom(_clan(), [person], [], [], branches, {person_id: 3})
    blocks = _indi_blocks(gedcom)
    assert (
        "1 NOTE FamilyRoots: ten_huy=Nguyễn Văn Húy; ten_thuy=Nguyễn Văn Thụy; "
        "doi=3; chi=Chi Hai; lunar_birth=15/08 Canh Thân"
    ) in blocks["Cụ Tổ"]


def test_fam_marriage_husb_wife_divorce_and_spouse_order_note() -> None:
    husband = _person(full_name="Chồng", gender="male")
    wife = _person(full_name="Vợ", gender="female")
    ex_wife = _person(full_name="Vợ Cũ", gender="female")
    m_married = _marriage(husband["id"], wife["id"], spouse_order=2)
    m_divorced = _marriage(husband["id"], ex_wife["id"], status="divorced")
    gedcom = build_gedcom(_clan(), [husband, wife, ex_wife], [m_married, m_divorced], [], [], {})
    xrefs = _indi_xrefs(gedcom)
    fams = _fam_records(gedcom)

    married_fam = next(
        rec for rec in fams if f"1 HUSB {xrefs['Chồng']}" in rec and f"1 WIFE {xrefs['Vợ']}" in rec
    )
    assert "1 NOTE spouse_order=2; status=married" in married_fam

    divorced_fam = next(rec for rec in fams if f"1 WIFE {xrefs['Vợ Cũ']}" in rec)
    assert "1 DIV" in divorced_fam
    assert f"1 HUSB {xrefs['Chồng']}" in divorced_fam


def test_child_linking_married_parents_and_single_parent_adopted() -> None:
    father = _person(full_name="Cha", gender="male")
    mother = _person(full_name="Mẹ", gender="female")
    bio_child = _person(full_name="Con Ruột")
    adopted_child = _person(full_name="Con Nuôi")
    marriage = _marriage(father["id"], mother["id"])
    edges = [
        _edge(father["id"], bio_child["id"], relationship_type="biological"),
        _edge(mother["id"], bio_child["id"], relationship_type="biological"),
        _edge(father["id"], adopted_child["id"], relationship_type="adopted"),
    ]
    gedcom = build_gedcom(
        _clan(), [father, mother, bio_child, adopted_child], [marriage], edges, [], {}
    )
    xrefs = _indi_xrefs(gedcom)
    records = _records(gedcom)
    fams = _fam_records(gedcom)

    married_fam = next(
        rec for rec in fams if f"1 HUSB {xrefs['Cha']}" in rec and f"1 WIFE {xrefs['Mẹ']}" in rec
    )
    married_fam_xref = married_fam[0].split()[1]
    assert f"1 CHIL {xrefs['Con Ruột']}" in married_fam
    assert f"1 CHIL {xrefs['Con Nuôi']}" not in married_fam

    bio_child_rec = next(rec for rec in records if rec[0] == f"0 {xrefs['Con Ruột']} INDI")
    assert f"1 FAMC {married_fam_xref}" in bio_child_rec
    assert not any(line.startswith("2 PEDI") for line in bio_child_rec)

    adopted_child_rec = next(rec for rec in records if rec[0] == f"0 {xrefs['Con Nuôi']} INDI")
    adopted_fam = next(rec for rec in fams if f"1 CHIL {xrefs['Con Nuôi']}" in rec)
    adopted_fam_xref = adopted_fam[0].split()[1]
    assert adopted_fam_xref != married_fam_xref  # own single-parent FAM
    assert f"1 HUSB {xrefs['Cha']}" in adopted_fam
    assert not any(line.startswith("1 WIFE") for line in adopted_fam)
    assert f"1 FAMC {adopted_fam_xref}" in adopted_child_rec
    assert "2 PEDI adopted" in adopted_child_rec


def test_xref_integrity_deterministic_numbering_and_conc_folding() -> None:
    father = _person(full_name="Cha", gender="male")
    mother = _person(full_name="Mẹ", gender="female")
    child = _person(full_name="Con", biography="A" * 500)
    marriage = _marriage(father["id"], mother["id"])
    edges = [
        _edge(father["id"], child["id"]),
        _edge(mother["id"], child["id"]),
    ]
    gedcom_1 = build_gedcom(_clan(), [father, mother, child], [marriage], edges, [], {})
    gedcom_2 = build_gedcom(_clan(), [father, mother, child], [marriage], edges, [], {})
    assert gedcom_1 == gedcom_2  # deterministic across runs

    lines = gedcom_1.split("\n")
    defined_indi = {line.split()[1] for line in lines if line.startswith("0 @I")}
    defined_fam = {line.split()[1] for line in lines if line.startswith("0 @F")}
    referenced_indi = set(re.findall(r"@I\d+@", gedcom_1))
    referenced_fam = set(re.findall(r"@F\d+@", gedcom_1))
    assert referenced_indi <= defined_indi
    assert referenced_fam <= defined_fam

    sorted_ids = sorted([father["id"], mother["id"], child["id"]], key=str)
    name_by_id = {father["id"]: "Cha", mother["id"]: "Mẹ", child["id"]: "Con"}
    xrefs = _indi_xrefs(gedcom_1)
    assert xrefs[name_by_id[sorted_ids[0]]] == "@I1@"

    assert all(len(line) <= 240 for line in lines)
    assert any(line.startswith("2 CONC ") for line in lines)
