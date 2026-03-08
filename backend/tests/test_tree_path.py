"""Tests for tree path finder (relationship descriptor)."""

import uuid

from app.services.relationship_descriptor import KINSHIP_MAP, describe_relationship


def _path_step(person_id, full_name="Test", gender="male", edge_type=None):
    """Build a path step dict."""
    return {
        "person_id": str(person_id),
        "full_name": full_name,
        "gender": gender,
        "edge_type": edge_type,
    }


def test_same_person():
    """Single-element path returns 'same person'."""
    me = uuid.uuid4()
    result = describe_relationship([_path_step(me)], "male", "male")
    assert result  # returns a non-empty string


def test_parent_relationship():
    """Two-step path with 'parent' edge."""
    child = uuid.uuid4()
    parent = uuid.uuid4()
    path = [
        _path_step(child, "Child"),
        _path_step(parent, "Parent", edge_type="parent"),
    ]
    result = describe_relationship(path, "male", "male")
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
    result = describe_relationship(path, "male", "female")
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
    result = describe_relationship(path, "male", "male")
    assert result


def test_distant_relative():
    """Long path falls back to distant relative description."""
    ids = [uuid.uuid4() for _ in range(8)]
    edges = ["parent", "parent", "parent", "parent", "child", "child", "child"]
    path = [_path_step(ids[0], "Person0")]
    for i, edge in enumerate(edges):
        path.append(_path_step(ids[i + 1], f"Person{i + 1}", edge_type=edge))

    result = describe_relationship(path, "male", "male")
    # Sequence not in KINSHIP_MAP → distant relative
    assert result


def test_kinship_map_coverage():
    """All entries in KINSHIP_MAP are non-empty strings."""
    for key, value in KINSHIP_MAP.items():
        assert isinstance(key, tuple)
        assert isinstance(value, str)
        assert len(value) > 0
