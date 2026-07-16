"""The person repository must expose no unscoped-by-clan entity lookup.

App-layer clan filtering is the ONLY enforced isolation layer (RLS is an inert
pilot), so an unscoped `get_by_id(person_id)` returning any clan's person is a
latent IDOR footgun: it had zero callers, but one future handler reaching for
the shortest-named method would silently bypass isolation. Every lookup must
go through get_in_clan(person_id, clan_id).
"""

from app.domain.person.repository import PersonRepository
from app.infrastructure.persistence.person_repository import SqlAlchemyPersonRepository


def test_concrete_repository_has_no_unscoped_get_by_id() -> None:
    assert not hasattr(SqlAlchemyPersonRepository, "get_by_id")


def test_repository_port_has_no_unscoped_get_by_id() -> None:
    assert not hasattr(PersonRepository, "get_by_id")
