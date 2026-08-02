"""ADR-036 — the person write schemas reject a client-supplied `avatar_url`.

Rejected, not silently ignored: the pre-ADR-036 state of this field was exactly a
column clients wrote into and nothing maintained, and a silent drop would leave a
client believing it had set an avatar. A 422 naming `body.avatar_url` sends them to
`PATCH /documents/{id}/set-avatar` instead.

Second line of defence, pinned below: `exclude=True` keeps the field out of
`model_dump()`, so even if the validator were removed the value could not ride into
`CreatePerson`/`UpdatePerson` — the command DTOs have no such attribute at all.
"""

import dataclasses

import pytest
from pydantic import ValidationError

from app.application.person.commands import CreatePerson
from app.schemas.person import PersonCreateRequest, PersonUpdateRequest


class TestCreateRequest:
    def test_rejects_a_supplied_avatar_url(self) -> None:
        with pytest.raises(ValidationError) as err:
            PersonCreateRequest(full_name="A", avatar_url="https://evil.example/pixel.gif")
        assert [e["loc"] for e in err.value.errors()] == [("avatar_url",)]

    def test_rejects_an_explicit_null_too(self) -> None:
        """Clearing an avatar is not a person-write either — there is one writer."""
        with pytest.raises(ValidationError):
            PersonCreateRequest.model_validate({"full_name": "A", "avatar_url": None})

    def test_unset_avatar_url_is_fine_and_absent_from_the_dump(self) -> None:
        dumped = PersonCreateRequest(full_name="A").model_dump()
        assert "avatar_url" not in dumped
        # The route does CreatePerson(**dumped); the DTO has no avatar_url field, so a
        # regression that let the key through would fail loudly here, not silently.
        assert "avatar_url" not in {f.name for f in dataclasses.fields(CreatePerson)}


class TestUpdateRequest:
    def test_rejects_a_supplied_avatar_url(self) -> None:
        with pytest.raises(ValidationError) as err:
            PersonUpdateRequest(expected_version=1, avatar_url="https://evil.example/pixel.gif")
        assert [e["loc"] for e in err.value.errors()] == [("avatar_url",)]

    def test_other_fields_still_patch_normally(self) -> None:
        body = PersonUpdateRequest(expected_version=3, phone="0900000000")
        dumped = body.model_dump(exclude_unset=True)
        assert dumped == {"expected_version": 3, "phone": "0900000000"}
        assert "avatar_url" not in dumped
