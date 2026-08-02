"""ADR-036 — `persons.avatar_url` is server-managed and must stay permanent.

Two separate guarantees live here:

1. **Nobody but the server writes it.** It is out of `_UPDATABLE_FIELDS`, so
   `Person.update()` rejects it like any other non-updatable column, and
   `Person.create()` rejects it too (create does not go through that whitelist).
   Without this, a client could point a member's portrait at an arbitrary host.
2. **What the server writes is durable.** `set_avatar_url` accepts only an absolute
   http(s) URL with no query string and no fragment. Every presigned URL carries its
   signature and expiry in the query string, so that one rule structurally excludes
   the whole class — the column cannot come to hold a URL that silently stops
   resolving, which is the failure that made this decision necessary.
"""

import uuid

import pytest

from app.domain.person.entity import AVATAR_URL_MAX_LENGTH, Person
from app.domain.person.events import PersonUpdated
from app.domain.shared.exceptions import BusinessRuleViolation
from app.domain.shared.value_objects import ActorInfo

_PUBLIC = (
    "https://proj.supabase.co/storage/v1/object/public/family-roots-avatars/"
    "clans/11111111-1111-1111-1111-111111111111/avatars/22222222-2222-2222-2222-222222222222"
)


def _actor() -> ActorInfo:
    return ActorInfo.from_jwt({"sub": str(uuid.uuid4())}, "editor")


def _person() -> Person:
    p = Person.create(full_name="Nguyễn Văn A", actor=_actor(), clan_id=uuid.uuid4())
    p.collect_events()
    return p


class TestClientsCannotWriteAvatarUrl:
    def test_update_rejects_avatar_url(self) -> None:
        p = _person()
        with pytest.raises(BusinessRuleViolation, match="field_not_updatable"):
            p.update({"avatar_url": "https://evil.example/tracker.gif"}, _actor(), uuid.uuid4())
        assert p.avatar_url is None

    def test_create_rejects_avatar_url(self) -> None:
        with pytest.raises(BusinessRuleViolation, match="field_not_updatable"):
            Person.create(
                full_name="A",
                actor=_actor(),
                clan_id=uuid.uuid4(),
                avatar_url="https://evil.example/tracker.gif",
            )


class TestSetAvatarUrl:
    def test_stores_a_permanent_public_url_and_emits_person_updated(self) -> None:
        p = _person()
        actor, clan_id = _actor(), uuid.uuid4()

        p.set_avatar_url(_PUBLIC, actor, clan_id)

        assert p.avatar_url == _PUBLIC
        assert p.updated_by == actor.user_id
        (event,) = p.collect_events()
        assert isinstance(event, PersonUpdated)
        assert event.changes == {"avatar_url": _PUBLIC}
        assert event.old_values == {"avatar_url": None}

    def test_trims_surrounding_whitespace(self) -> None:
        p = _person()
        p.set_avatar_url(f"  {_PUBLIC}  ", _actor(), uuid.uuid4())
        assert p.avatar_url == _PUBLIC

    @pytest.mark.parametrize(
        "presigned",
        [
            # Supabase signed-object URL: token in the query string.
            "https://proj.supabase.co/storage/v1/object/sign/files/x.jpg?token=eyJhbGciOi",
            # S3-style presign.
            "https://s3.example.com/bucket/x.jpg?X-Amz-Expires=3600&X-Amz-Signature=deadbeef",
            # Even a bare empty query string is refused — no query means no expiry.
            "https://proj.supabase.co/storage/v1/object/public/avatars/x.jpg?",
            # Fragments are equally not part of a canonical stored object URL.
            "https://proj.supabase.co/storage/v1/object/public/avatars/x.jpg#frag",
        ],
    )
    def test_refuses_anything_carrying_a_query_string_or_fragment(self, presigned: str) -> None:
        p = _person()
        with pytest.raises(BusinessRuleViolation) as err:
            p.set_avatar_url(presigned, _actor(), uuid.uuid4())
        assert err.value.code == "person.avatar_url_not_permanent"
        assert p.avatar_url is None
        assert p.collect_events() == []

    @pytest.mark.parametrize(
        "bad",
        [
            "",
            "   ",
            "not-a-url",
            "/relative/path.jpg",
            "ftp://host/x.jpg",
            "javascript:alert(1)",
            "data:image/png;base64,AAAA",
        ],
    )
    def test_refuses_a_non_absolute_http_url(self, bad: str) -> None:
        p = _person()
        with pytest.raises(BusinessRuleViolation) as err:
            p.set_avatar_url(bad, _actor(), uuid.uuid4())
        assert err.value.code == "person.avatar_url_invalid"
        assert p.avatar_url is None

    def test_refuses_a_url_longer_than_the_column(self) -> None:
        """persons.avatar_url is varchar(500); reject in the domain rather than let
        the driver raise a truncation error mid-transaction."""
        p = _person()
        too_long = "https://proj.supabase.co/" + "a" * AVATAR_URL_MAX_LENGTH
        with pytest.raises(BusinessRuleViolation) as err:
            p.set_avatar_url(too_long, _actor(), uuid.uuid4())
        assert err.value.code == "person.avatar_url_invalid"
        assert p.avatar_url is None

    def test_accepts_a_url_exactly_at_the_limit(self) -> None:
        p = _person()
        prefix = "https://proj.supabase.co/"
        at_limit = prefix + "a" * (AVATAR_URL_MAX_LENGTH - len(prefix))
        p.set_avatar_url(at_limit, _actor(), uuid.uuid4())
        assert p.avatar_url == at_limit and len(at_limit) == AVATAR_URL_MAX_LENGTH
