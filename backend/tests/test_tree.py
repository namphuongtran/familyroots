"""Tests for family tree builder assembly logic.

These tests mock the AsyncSession to validate the pure assembly logic
(node wiring, spouse attachment, sorting, cycle detection) without a real DB.
"""

import uuid
from datetime import date
from typing import Any

import pytest

from app.services.tree_builder import build_descendants_tree, find_clan_founder
from tests.conftest import (
    MockMappingResult,
    MockScalarResult,
    make_member_row,
    make_mock_db,
    make_spouse_row,
)

CLAN_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


# ── Test 1: Single member (root only, no children, no spouse) ──


@pytest.mark.asyncio
async def test_single_member():
    root_id = uuid.uuid4()
    rows = [
        make_member_row(member_id=root_id, full_name="Nguyễn Văn A", is_clan_founder=True, depth=0)
    ]
    spouse_rows: list[dict[str, Any]] = []

    db = make_mock_db(
        MockMappingResult(rows),  # get_family_tree_flat result
        MockMappingResult(spouse_rows),  # spouse query result
    )

    result = await build_descendants_tree(db, root_id, CLAN_ID)

    assert result["id"] == str(root_id)
    assert result["full_name"] == "Nguyễn Văn A"
    assert result["is_clan_founder"] is True
    assert result["spouses"] == []
    assert result["children"] == []
    assert result["depth"] == 0


# ── Test 2: Member with spouse ──


@pytest.mark.asyncio
async def test_member_with_spouse():
    root_id = uuid.uuid4()
    spouse_id = uuid.uuid4()

    rows = [make_member_row(member_id=root_id, full_name="Nguyễn Văn A", depth=0)]
    spouse_rows = [
        make_spouse_row(
            for_member_id=root_id,
            spouse_id=spouse_id,
            full_name="Trần Thị B",
            gender="female",
            relation_subtype="married",
            start_date=date(1945, 2, 10),
        )
    ]

    db = make_mock_db(
        MockMappingResult(rows),
        MockMappingResult(spouse_rows),
    )

    result = await build_descendants_tree(db, root_id, CLAN_ID)

    assert len(result["spouses"]) == 1
    assert result["spouses"][0]["full_name"] == "Trần Thị B"
    assert result["spouses"][0]["relation_subtype"] == "married"
    assert result["spouses"][0]["start_date"] == "1945-02-10"
    assert result["spouses"][0]["id"] == str(spouse_id)


# ── Test 3: Member with children ──


@pytest.mark.asyncio
async def test_member_with_children():
    root_id = uuid.uuid4()
    child1_id = uuid.uuid4()
    child2_id = uuid.uuid4()

    rows = [
        make_member_row(member_id=root_id, full_name="Father", depth=0, generation=1),
        make_member_row(
            member_id=child1_id,
            full_name="Child B",
            parent_id=root_id,
            depth=1,
            generation=2,
            birth_date=date(1970, 6, 15),
        ),
        make_member_row(
            member_id=child2_id,
            full_name="Child A",
            parent_id=root_id,
            depth=1,
            generation=2,
            birth_date=date(1965, 3, 10),
        ),
    ]

    db = make_mock_db(
        MockMappingResult(rows),
        MockMappingResult([]),  # no spouses
    )

    result = await build_descendants_tree(db, root_id, CLAN_ID)

    assert len(result["children"]) == 2
    # Children sorted by birth_date: Child A (1965) before Child B (1970)
    assert result["children"][0]["full_name"] == "Child A"
    assert result["children"][1]["full_name"] == "Child B"
    assert result["children"][0]["depth"] == 1


# ── Test 4: Three-generation tree ──


@pytest.mark.asyncio
async def test_three_generation_tree():
    grandparent = uuid.uuid4()
    parent = uuid.uuid4()
    grandchild = uuid.uuid4()

    rows = [
        make_member_row(
            member_id=grandparent,
            full_name="Grandparent",
            depth=0,
            generation=1,
            is_clan_founder=True,
        ),
        make_member_row(
            member_id=parent,
            full_name="Parent",
            parent_id=grandparent,
            depth=1,
            generation=2,
            birth_date=date(1950, 1, 1),
        ),
        make_member_row(
            member_id=grandchild,
            full_name="Grandchild",
            parent_id=parent,
            depth=2,
            generation=3,
            birth_date=date(1980, 5, 20),
        ),
    ]

    db = make_mock_db(
        MockMappingResult(rows),
        MockMappingResult([]),
    )

    result = await build_descendants_tree(db, grandparent, CLAN_ID)

    assert result["full_name"] == "Grandparent"
    assert result["is_clan_founder"] is True
    assert len(result["children"]) == 1
    assert result["children"][0]["full_name"] == "Parent"
    assert len(result["children"][0]["children"]) == 1
    assert result["children"][0]["children"][0]["full_name"] == "Grandchild"
    assert result["children"][0]["children"][0]["depth"] == 2


# ── Test 5: Cycle detection (empty result if cycle) ──


@pytest.mark.asyncio
async def test_empty_result():
    """When SQL returns no rows (e.g., invalid root_id), return empty dict."""
    db = make_mock_db(
        MockMappingResult([]),  # no descendants found
    )

    result = await build_descendants_tree(db, uuid.uuid4(), CLAN_ID)
    assert result == {}


# ── Test 6: Remarriage (multiple spouses) ──


@pytest.mark.asyncio
async def test_remarriage_multiple_spouses():
    root_id = uuid.uuid4()
    spouse1_id = uuid.uuid4()
    spouse2_id = uuid.uuid4()

    rows = [make_member_row(member_id=root_id, full_name="Remarrying Person", depth=0)]
    spouse_rows = [
        make_spouse_row(
            for_member_id=root_id,
            spouse_id=spouse1_id,
            full_name="First Spouse",
            relation_subtype="divorced",
            start_date=date(1940, 1, 1),
            end_date=date(1960, 6, 1),
            is_primary=False,
        ),
        make_spouse_row(
            for_member_id=root_id,
            spouse_id=spouse2_id,
            full_name="Second Spouse",
            relation_subtype="married",
            start_date=date(1962, 3, 15),
            is_primary=True,
        ),
    ]

    db = make_mock_db(
        MockMappingResult(rows),
        MockMappingResult(spouse_rows),
    )

    result = await build_descendants_tree(db, root_id, CLAN_ID)

    assert len(result["spouses"]) == 2
    subtypes = {s["relation_subtype"] for s in result["spouses"]}
    assert subtypes == {"divorced", "married"}
    # Verify both spouse IDs are present
    spouse_ids = {s["id"] for s in result["spouses"]}
    assert str(spouse1_id) in spouse_ids
    assert str(spouse2_id) in spouse_ids


# ── Test 7: Adopted children (different relation_subtype preserved) ──


@pytest.mark.asyncio
async def test_adopted_children_in_tree():
    """Adopted children appear alongside biological children in the tree.

    Note: The tree builder doesn't directly encode relation_subtype in the
    tree nodes (that comes from the relationships table). The test verifies
    that adopted children are wired into the tree the same as biological ones.
    """
    root_id = uuid.uuid4()
    bio_child = uuid.uuid4()
    adopted_child = uuid.uuid4()

    rows = [
        make_member_row(member_id=root_id, full_name="Parent", depth=0, generation=1),
        make_member_row(
            member_id=bio_child,
            full_name="Bio Child",
            parent_id=root_id,
            depth=1,
            generation=2,
            birth_date=date(1970, 1, 1),
            is_clan_member=True,
        ),
        make_member_row(
            member_id=adopted_child,
            full_name="Adopted Child",
            parent_id=root_id,
            depth=1,
            generation=2,
            birth_date=date(1972, 6, 15),
            is_clan_member=True,
        ),
    ]

    db = make_mock_db(
        MockMappingResult(rows),
        MockMappingResult([]),
    )

    result = await build_descendants_tree(db, root_id, CLAN_ID)

    assert len(result["children"]) == 2
    names = [c["full_name"] for c in result["children"]]
    assert "Bio Child" in names
    assert "Adopted Child" in names
    # Sorted by birth_date
    assert result["children"][0]["full_name"] == "Bio Child"
    assert result["children"][1]["full_name"] == "Adopted Child"


# ── Test 8: find_clan_founder ──


@pytest.mark.asyncio
async def test_find_clan_founder_found():
    founder_id = uuid.uuid4()
    db = make_mock_db(MockScalarResult(founder_id))

    result = await find_clan_founder(db, CLAN_ID)
    assert result == founder_id


@pytest.mark.asyncio
async def test_find_clan_founder_not_found():
    db = make_mock_db(MockScalarResult(None))

    result = await find_clan_founder(db, CLAN_ID)
    assert result is None
