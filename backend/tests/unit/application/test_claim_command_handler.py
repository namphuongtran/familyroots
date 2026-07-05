"""Unit tests for ClaimCommandHandler approve/reject (no real DB)."""

import uuid
from datetime import UTC, datetime

import pytest

from app.application.person.claim_handlers import ClaimCommandHandler
from app.core.exceptions import ForbiddenError


class _Person:
    def __init__(self, clan_id):
        self.created_by_clan_id = clan_id


class _Claim:
    def __init__(self, person):
        self.id = uuid.uuid4()
        self.user_id = uuid.uuid4()
        self.person_id = uuid.uuid4()
        self.status = "PENDING"
        self.reviewed_by = None
        self.reviewer_note = None
        self.reviewed_at = None
        self.created_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)
        self.person = person


class _UserProfile:
    def __init__(self):
        self.person_id = None


class _FakeRepo:
    """Implements only the methods approve_claim/reject_claim call."""

    def __init__(self, claim, clan_id, *, caller_role="admin"):
        self._claim = claim
        self._clan_id = clan_id
        self._caller_role = caller_role
        self.added_audits = []
        self.added_roles = []

    async def get_claim(self, claim_id, load_person=False):
        return self._claim

    async def get_role(self, user_id, clan_id):
        return self._caller_role  # caller's role in the person's origin clan

    async def get_user_profile(self, user_id):
        return _UserProfile()

    async def lock_person(self, person_id):
        return None

    async def is_person_linked(self, person_id):
        return False

    async def auto_reject_other_pending_claims(self, **kwargs):
        return None

    def add_role(self, **kwargs):
        self.added_roles.append(kwargs)

    def add_audit(self, **kwargs):
        self.added_audits.append(kwargs)


class _FakeUow:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1


@pytest.mark.asyncio
async def test_approve_claim_uses_uow_and_writes_audit():
    clan_id = uuid.uuid4()
    claim = _Claim(_Person(clan_id))
    repo = _FakeRepo(claim, clan_id)
    uow = _FakeUow()
    handler = ClaimCommandHandler(repo, uow)  # type: ignore[arg-type]

    result = await handler.approve_claim(
        claim_id=claim.id, admin_id=uuid.uuid4(), reviewer_note="ok"
    )

    assert claim.status == "APPROVED"
    assert claim.reviewed_at is not None  # copied from the entity transition
    assert uow.commits == 1
    assert len(repo.added_audits) == 1
    assert result.status == "APPROVED"


@pytest.mark.asyncio
async def test_reject_claim_uses_uow_and_writes_audit():
    clan_id = uuid.uuid4()
    claim = _Claim(_Person(clan_id))
    repo = _FakeRepo(claim, clan_id)
    uow = _FakeUow()
    handler = ClaimCommandHandler(repo, uow)  # type: ignore[arg-type]

    result = await handler.reject_claim(
        claim_id=claim.id, admin_id=uuid.uuid4(), reviewer_note="no"
    )

    assert claim.status == "REJECTED"
    assert claim.reviewed_at is not None  # copied from the entity transition
    assert uow.commits == 1
    assert len(repo.added_audits) == 1
    assert result.status == "REJECTED"


# ── M14: claim review is authorized by the person's ORIGIN clan (provenance) ──
# These pin the deliberate authorization contract so it can't silently regress or be
# accidentally switched to a membership-based model.


@pytest.mark.parametrize("caller_role", ["viewer", "editor", None])
@pytest.mark.parametrize("action", ["approve_claim", "reject_claim"])
@pytest.mark.asyncio
async def test_review_rejects_non_admin_of_origin_clan(action, caller_role):
    """Only an ADMIN of the person's origin clan may review; anyone else is forbidden."""
    clan_id = uuid.uuid4()
    claim = _Claim(_Person(clan_id))
    repo = _FakeRepo(claim, clan_id, caller_role=caller_role)
    handler = ClaimCommandHandler(repo, _FakeUow())  # type: ignore[arg-type]

    with pytest.raises(ForbiddenError, match="only_clan_admin_can_review_claims"):
        await getattr(handler, action)(claim_id=claim.id, admin_id=uuid.uuid4(), reviewer_note="x")
    assert claim.status == "PENDING"  # unchanged — the review never happened


@pytest.mark.parametrize("action", ["approve_claim", "reject_claim"])
@pytest.mark.asyncio
async def test_review_rejects_orphaned_person(action):
    """A person whose origin clan was cleared (created_by_clan_id is None) has no
    controlling clan, so its claims cannot be reviewed by anyone."""
    claim = _Claim(_Person(None))
    repo = _FakeRepo(claim, None, caller_role="admin")
    handler = ClaimCommandHandler(repo, _FakeUow())  # type: ignore[arg-type]

    with pytest.raises(ForbiddenError, match="person_has_no_controlling_clan"):
        await getattr(handler, action)(claim_id=claim.id, admin_id=uuid.uuid4(), reviewer_note="x")
    assert claim.status == "PENDING"
