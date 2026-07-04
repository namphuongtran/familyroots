"""Unit tests for ClaimCommandHandler approve/reject (no real DB)."""

import uuid
from datetime import UTC, datetime

import pytest

from app.application.person.claim_handlers import ClaimCommandHandler


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

    def __init__(self, claim, clan_id):
        self._claim = claim
        self._clan_id = clan_id
        self.added_audits = []
        self.added_roles = []

    async def get_claim(self, claim_id, load_person=False):
        return self._claim

    async def get_role(self, user_id, clan_id):
        return "admin"  # caller is admin of the person's clan

    async def get_user_profile(self, user_id):
        return _UserProfile()

    async def lock_person(self, person_id):
        return None

    async def is_person_linked(self, person_id):
        return False

    async def auto_reject_other_pending_claims(self, **kwargs):
        return None

    def add_role(self, role):
        self.added_roles.append(role)

    def add_audit(self, audit):
        self.added_audits.append(audit)


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
    assert uow.commits == 1
    assert len(repo.added_audits) == 1
    assert result.status == "REJECTED"
