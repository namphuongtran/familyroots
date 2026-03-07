"""Tests for relationship validation rules."""

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import ConflictError, ValidationError
from app.services.relationship_validator import RelationshipValidator


@pytest.fixture
def validator():
    return RelationshipValidator()


@pytest.fixture
def clan_id():
    return uuid.uuid4()


def _make_member(mid=None, birth_date=None):
    """Create a mock Member object."""
    m = MagicMock()
    m.id = mid or uuid.uuid4()
    m.birth_date = birth_date
    return m


@pytest.mark.asyncio
async def test_self_loop_prevented_by_schema():
    """Self-referential relationships are caught by the Pydantic schema validator."""
    from app.schemas.relationship import RelationshipCreateRequest

    member_id = uuid.uuid4()
    with pytest.raises(ValueError, match="must be different"):
        RelationshipCreateRequest(
            member_id=member_id,
            related_id=member_id,
            relation_type="parent",
            relation_subtype="biological",
        )


@pytest.mark.asyncio
async def test_too_many_bio_parents(validator, clan_id):
    """Cannot add a 3rd biological parent."""
    parent = _make_member(birth_date=date(1970, 1, 1))
    child = _make_member(birth_date=date(2000, 1, 1))

    db = AsyncMock()
    db.get = AsyncMock(side_effect=[parent, child])

    # _count_bio_parents returns 2
    count_result = MagicMock()
    count_result.first.return_value = (2,)

    db.execute = AsyncMock(return_value=count_result)

    with pytest.raises(ConflictError, match="too_many_biological_parents"):
        await validator.validate_parent_child(parent.id, child.id, "biological", db, clan_id)


@pytest.mark.asyncio
async def test_parent_too_young(validator, clan_id):
    """Parent must be at least 12 years older than child."""
    parent = _make_member(birth_date=date(2000, 1, 1))
    child = _make_member(birth_date=date(2005, 1, 1))

    db = AsyncMock()
    db.get = AsyncMock(side_effect=[parent, child])

    # _count_bio_parents returns 0
    count_result = MagicMock()
    count_result.first.return_value = (0,)
    db.execute = AsyncMock(return_value=count_result)

    with pytest.raises(ValidationError, match="parent_too_young"):
        await validator.validate_parent_child(parent.id, child.id, "biological", db, clan_id)


@pytest.mark.asyncio
async def test_cycle_detection(validator, clan_id):
    """Creating a parent-child where child is ancestor of parent raises error."""
    parent = _make_member(birth_date=date(1950, 1, 1))
    child = _make_member(birth_date=date(1980, 1, 1))

    db = AsyncMock()
    db.get = AsyncMock(side_effect=[parent, child])

    # _count_bio_parents returns 0
    count_result = MagicMock()
    count_result.first.return_value = (0,)

    # get_ancestors_flat returns child.id as an ancestor of parent
    ancestors_result = MagicMock()
    ancestors_result.__iter__ = MagicMock(return_value=iter([(child.id,)]))

    call_count = 0

    async def mock_execute(query, params=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return count_result
        return ancestors_result

    db.execute = AsyncMock(side_effect=mock_execute)

    with pytest.raises(ValidationError, match="creates_cycle"):
        await validator.validate_parent_child(parent.id, child.id, "biological", db, clan_id)


@pytest.mark.asyncio
async def test_duplicate_active_spouse(validator, clan_id):
    """Cannot marry someone who already has an active marriage."""
    member_id = uuid.uuid4()
    spouse_id = uuid.uuid4()

    db = AsyncMock()

    # First execute returns existing active marriage
    existing_result = MagicMock()
    existing_result.first.return_value = (1,)
    db.execute = AsyncMock(return_value=existing_result)

    with pytest.raises(ConflictError, match="already_married"):
        await validator.validate_spouse(member_id, spouse_id, None, db, clan_id)
