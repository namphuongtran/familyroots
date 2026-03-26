import uuid

import pytest

from app.domain.person.claim_entity import IdentityClaim


def test_claim_approve_success():
    claim = IdentityClaim(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        person_id=uuid.uuid4(),
        status="PENDING",
        requester_note="I am this person",
    )
    admin_id = uuid.uuid4()
    claim.approve(admin_id=admin_id, reviewer_note="Verified.")

    assert claim.status == "APPROVED"
    assert claim.reviewed_by == admin_id
    assert claim.reviewer_note == "Verified."


def test_claim_approve_invalid_state():
    claim = IdentityClaim(
        id=uuid.uuid4(), user_id=uuid.uuid4(), person_id=uuid.uuid4(), status="REJECTED"
    )
    admin_id = uuid.uuid4()
    with pytest.raises(ValueError, match="Only PENDING claims can be approved"):
        claim.approve(admin_id=admin_id, reviewer_note="Oops")


def test_claim_reject_success():
    claim = IdentityClaim(
        id=uuid.uuid4(), user_id=uuid.uuid4(), person_id=uuid.uuid4(), status="PENDING"
    )
    admin_id = uuid.uuid4()
    claim.reject(admin_id=admin_id, reviewer_note="Not matching records.")

    assert claim.status == "REJECTED"
    assert claim.reviewed_by == admin_id
    assert claim.reviewer_note == "Not matching records."


def test_claim_reject_invalid_state():
    claim = IdentityClaim(
        id=uuid.uuid4(), user_id=uuid.uuid4(), person_id=uuid.uuid4(), status="CANCELLED"
    )
    with pytest.raises(ValueError, match="Only PENDING claims can be rejected"):
        claim.reject(admin_id=uuid.uuid4(), reviewer_note="...")


def test_claim_cancel_success():
    user_id = uuid.uuid4()
    claim = IdentityClaim(
        id=uuid.uuid4(), user_id=user_id, person_id=uuid.uuid4(), status="PENDING"
    )
    claim.cancel(user_id=user_id)
    assert claim.status == "CANCELLED"


def test_claim_cancel_wrong_user():
    user_id = uuid.uuid4()
    wrong_user_id = uuid.uuid4()
    claim = IdentityClaim(
        id=uuid.uuid4(), user_id=user_id, person_id=uuid.uuid4(), status="PENDING"
    )
    with pytest.raises(ValueError, match="Only the requester can cancel their claim"):
        claim.cancel(user_id=wrong_user_id)


def test_claim_cancel_invalid_state():
    user_id = uuid.uuid4()
    claim = IdentityClaim(
        id=uuid.uuid4(), user_id=user_id, person_id=uuid.uuid4(), status="APPROVED"
    )
    with pytest.raises(ValueError, match="Only PENDING claims can be cancelled"):
        claim.cancel(user_id=user_id)
