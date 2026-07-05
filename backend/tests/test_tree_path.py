"""Tests for tree path finder (relationship descriptor)."""

import uuid
from datetime import date

import pytest

from app.services.relationship_descriptor import (
    KINSHIP_MAP,
    SPECIFIC_KINSHIP_KEYS,
    _specific_key,
    describe_relationship,
)


def _path_step(
    person_id,
    full_name="Test",
    gender="male",
    edge_type=None,
    birth_date=None,
    birth_date_approx=False,
):
    """Build a path step dict."""
    return {
        "person_id": str(person_id),
        "full_name": full_name,
        "gender": gender,
        "edge_type": edge_type,
        "birth_date": birth_date,
        "birth_date_approx": birth_date_approx,
    }


def test_same_person():
    """Single-element path returns 'same person'."""
    me = uuid.uuid4()
    result = describe_relationship([_path_step(me)])
    assert result  # returns a non-empty string


def test_parent_relationship():
    """Two-step path with 'parent' edge."""
    child = uuid.uuid4()
    parent = uuid.uuid4()
    path = [
        _path_step(child, "Child"),
        _path_step(parent, "Parent", edge_type="parent"),
    ]
    result = describe_relationship(path)
    # Should return the i18n value for kinship.parent
    assert result


def test_sibling_relationship():
    """Parent → child path describes sibling."""
    me = uuid.uuid4()
    shared_parent = uuid.uuid4()
    sibling = uuid.uuid4()
    path = [
        _path_step(me, "Me"),
        _path_step(shared_parent, "Parent", edge_type="parent"),
        _path_step(sibling, "Sibling", edge_type="child"),
    ]
    result = describe_relationship(path)
    assert result


def test_grandparent_relationship():
    """parent → parent path describes grandparent."""
    me = uuid.uuid4()
    parent = uuid.uuid4()
    grandparent = uuid.uuid4()
    path = [
        _path_step(me, "Me"),
        _path_step(parent, "Parent", edge_type="parent"),
        _path_step(grandparent, "Grandparent", edge_type="parent"),
    ]
    result = describe_relationship(path)
    assert result


def test_distant_relative():
    """Long path falls back to distant relative description."""
    ids = [uuid.uuid4() for _ in range(8)]
    edges = ["parent", "parent", "parent", "parent", "child", "child", "child"]
    path = [_path_step(ids[0], "Person0")]
    for i, edge in enumerate(edges):
        path.append(_path_step(ids[i + 1], f"Person{i + 1}", edge_type=edge))

    result = describe_relationship(path)
    # Sequence not in KINSHIP_MAP → distant relative
    assert result


def test_kinship_map_coverage():
    """All entries in KINSHIP_MAP are non-empty strings."""
    for key, value in KINSHIP_MAP.items():
        assert isinstance(key, tuple)
        assert isinstance(value, str)
        assert len(value) > 0


# ── M6: gender + paternal/maternal side + relative age resolution ──────────────
# _specific_key is the deterministic core (returns the i18n key, no locale coupling).


def _n(gender="unknown", birth_date=None, birth_date_approx=False):
    return _path_step(
        uuid.uuid4(), gender=gender, birth_date=birth_date, birth_date_approx=birth_date_approx
    )


@pytest.mark.parametrize(
    ("gender", "expected"),
    [("male", "kinship.father"), ("female", "kinship.mother"), ("unknown", None)],
)
def test_parent_gendered(gender, expected):
    assert _specific_key(("parent",), [_n(), _n(gender)]) == expected


@pytest.mark.parametrize(
    ("gender", "expected"),
    [("male", "kinship.son"), ("female", "kinship.daughter")],
)
def test_child_gendered(gender, expected):
    assert _specific_key(("child",), [_n(), _n(gender)]) == expected


def test_spouse_gendered():
    assert _specific_key(("spouse",), [_n(), _n("male")]) == "kinship.husband"
    assert _specific_key(("spouse",), [_n(), _n("female")]) == "kinship.wife"


def test_sibling_uses_age_and_gender():
    me = _n("male", date(1990, 1, 1))
    older_bro = _n("male", date(1985, 1, 1))
    older_sis = _n("female", date(1985, 1, 1))
    younger_sis = _n("female", date(1995, 1, 1))
    mid = _n("male")  # shared parent (side irrelevant for siblings)
    assert _specific_key(("parent", "child"), [me, mid, older_bro]) == "kinship.older_brother"
    assert _specific_key(("parent", "child"), [me, mid, older_sis]) == "kinship.older_sister"
    assert _specific_key(("parent", "child"), [me, mid, younger_sis]) == "kinship.younger_sister"


def test_sibling_without_birthdate_falls_back():
    """Missing birth dates → no age term → None (caller uses generic 'Anh/Chị/Em')."""
    me = _n("male")  # no birth_date
    sib = _n("male")
    assert _specific_key(("parent", "child"), [me, _n("male"), sib]) is None


def test_sibling_approximate_date_falls_back():
    """An APPROXIMATE date must not become a hard Anh/Em claim → fall back to generic."""
    me = _n("male", date(1990, 1, 1))
    approx_sib = _n("male", date(1985, 1, 1), birth_date_approx=True)
    assert _specific_key(("parent", "child"), [me, _n("male"), approx_sib]) is None


def test_sibling_equal_dates_falls_back():
    """Equal dates (twins / unknown-but-equal) must not silently pick 'younger'."""
    me = _n("male", date(1990, 1, 1))
    twin = _n("male", date(1990, 1, 1))
    assert _specific_key(("parent", "child"), [me, _n("male"), twin]) is None


def test_grandparent_paternal_vs_maternal():
    # side comes from the linking parent (path[1])
    via_father = [_n("male"), _n("male"), _n("male")]  # → ông nội
    via_mother = [_n("male"), _n("female"), _n("female")]  # → bà ngoại
    assert _specific_key(("parent", "parent"), via_father) == "kinship.paternal_grandfather"
    assert _specific_key(("parent", "parent"), via_mother) == "kinship.maternal_grandmother"
    # unknown side → generic
    assert _specific_key(("parent", "parent"), [_n("male"), _n("unknown"), _n("male")]) is None


def test_uncle_aunt_paternal_uses_age():
    father = _n("male", date(1960, 1, 1))
    older_bro_of_father = _n("male", date(1955, 1, 1))  # Bác
    younger_bro_of_father = _n("male", date(1965, 1, 1))  # Chú
    younger_sis_of_father = _n("female", date(1966, 1, 1))  # Cô
    gp = _n("male")
    assert (
        _specific_key(("parent", "parent", "child"), [_n(), father, gp, older_bro_of_father])
        == "kinship.paternal_uncle_older"
    )
    assert (
        _specific_key(("parent", "parent", "child"), [_n(), father, gp, younger_bro_of_father])
        == "kinship.paternal_uncle_younger"
    )
    assert (
        _specific_key(("parent", "parent", "child"), [_n(), father, gp, younger_sis_of_father])
        == "kinship.paternal_aunt_younger"
    )


def test_uncle_aunt_maternal_is_age_agnostic():
    mother = _n("female")  # via mother → maternal side, no birth_date needed
    gp = _n("female")
    assert (
        _specific_key(("parent", "parent", "child"), [_n(), mother, gp, _n("male")])
        == "kinship.maternal_uncle"  # Cậu
    )
    assert (
        _specific_key(("parent", "parent", "child"), [_n(), mother, gp, _n("female")])
        == "kinship.maternal_aunt"  # Dì
    )


def test_paternal_uncle_without_birthdate_falls_back():
    father = _n("male")  # no birth_date → can't tell Bác vs Chú
    assert (
        _specific_key(("parent", "parent", "child"), [_n(), father, _n("male"), _n("male")]) is None
    )


def test_paternal_uncle_approximate_date_falls_back():
    """Approximate father/uncle dates → can't assert Bác vs Chú → generic."""
    father = _n("male", date(1960, 1, 1), birth_date_approx=True)
    uncle = _n("male", date(1955, 1, 1))
    assert _specific_key(("parent", "parent", "child"), [_n(), father, _n("male"), uncle]) is None


def test_all_resolver_keys_have_vietnamese_translations():
    """Every key _specific_key can emit must exist in vi.json (code↔i18n in sync).

    Derives the key set from SPECIFIC_KINSHIP_KEYS (the resolver's own source of truth)
    so a phase-2 key can't drift out of the locale files unnoticed."""
    from app.services.translator import _translations, load_translations

    load_translations()
    vi = _translations.get("vi", {})
    missing = {k for k in SPECIFIC_KINSHIP_KEYS if not vi.get(k)}
    assert not missing, f"missing vi kinship translations: {missing}"
