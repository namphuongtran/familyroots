"""Contact PII (phone/email) is redacted on read unless the viewer is admin or self.

The rule is docs/decisions/049-contact-pii-is-the-whole-field-visibility-rule.md. Its § 1
fixes the set at exactly ``phone`` and ``email``; its § 2 gives an ``editor`` or ``viewer``
the contact details of "their own linked person only", and an ``admin`` those of every
person in the clan.

Genealogy content stays visible to every clan member; only phone/email are gated.
redact_pii mutates the PersonResponse list in place before it is serialized to the wire.

**This file proves the function, not the wiring.** Every case below calls ``redact_pii``
itself and none issues an HTTP request. ADR-049 § "Measurement 5" deleted a route's
redaction call and watched the whole suite stay at ``1351 passed``. The four routes that
redact are proved by request and response body in
``tests/integration/test_person_pii_over_http.py``.
"""

import uuid
from datetime import UTC, datetime

import pytest

from app.application.person.handlers import PersonQueryHandler
from app.schemas.person import PersonResponse

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


class _FakeRepo:
    """Only get_linked_person_id is exercised by redact_pii."""

    def __init__(self, linked_person_id: uuid.UUID | None) -> None:
        self._linked = linked_person_id

    async def get_linked_person_id(self, user_id: uuid.UUID) -> uuid.UUID | None:
        return self._linked


def _person(person_id: uuid.UUID) -> PersonResponse:
    return PersonResponse(
        id=person_id,
        full_name="Nguyễn Văn A",
        gender="male",
        nationality="VN",
        birth_date_approx=False,
        death_date_approx=False,
        is_deleted=False,
        created_by=uuid.uuid4(),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        phone="0900000000",
        email="a@example.com",
    )


def _handler(linked: uuid.UUID | None) -> PersonQueryHandler:
    return PersonQueryHandler(_FakeRepo(linked))  # type: ignore[arg-type]


async def test_admin_sees_contact_pii() -> None:
    p = _person(uuid.uuid4())
    await _handler(None).redact_pii([p], viewer_role="admin", viewer_user_id=uuid.uuid4())
    assert p.phone == "0900000000" and p.email == "a@example.com"


async def test_viewer_sees_own_linked_person_pii() -> None:
    pid = uuid.uuid4()
    p = _person(pid)
    # viewer is linked to this exact person → self → not redacted
    await _handler(pid).redact_pii([p], viewer_role="viewer", viewer_user_id=uuid.uuid4())
    assert p.phone == "0900000000" and p.email == "a@example.com"


async def test_viewer_cannot_see_others_pii() -> None:
    p = _person(uuid.uuid4())
    # viewer linked to a DIFFERENT person → phone/email nulled
    await _handler(uuid.uuid4()).redact_pii([p], viewer_role="viewer", viewer_user_id=uuid.uuid4())
    assert p.phone is None and p.email is None
    assert p.full_name == "Nguyễn Văn A"  # genealogy content untouched


async def test_viewer_without_linked_person_sees_no_pii() -> None:
    p = _person(uuid.uuid4())
    await _handler(None).redact_pii([p], viewer_role="viewer", viewer_user_id=uuid.uuid4())
    assert p.phone is None and p.email is None


async def test_editor_is_gated_like_viewer() -> None:
    """Only admin (and self) bypass; an editor viewing someone else is redacted."""
    p = _person(uuid.uuid4())
    await _handler(uuid.uuid4()).redact_pii([p], viewer_role="editor", viewer_user_id=uuid.uuid4())
    assert p.phone is None and p.email is None
