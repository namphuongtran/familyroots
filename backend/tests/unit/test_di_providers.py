"""Smoke tests for the FastAPI DI providers in app.infrastructure.dependencies.

Regression for a NameError shipped on main: several handler providers referenced
their handler class (e.g. AuthCommandHandler / MeQueryHandler) but imported it only
under ``if TYPE_CHECKING`` — so those endpoints 500'd at runtime. These db-only
providers build their handler without touching the DB at construction time, so
calling them with a mock session must return a handler and never raise NameError.
"""

from unittest.mock import MagicMock

import pytest

from app.infrastructure import dependencies as deps

# Providers that depend only on a DB session (no Supabase / storage clients at
# construction), so they are safe to invoke with a mock in a pure unit test.
DB_ONLY_QUERY_PROVIDERS = [
    "get_me_query_handler",
    "get_auth_query_handler",
    "get_fcm_token_handler",
    "get_person_query_handler",
    "get_tree_query_handler",
    "get_clan_query_handler",
    "get_branch_query_handler",
    "get_event_query_handler",
    "get_marriage_query_handler",
    "get_parent_child_query_handler",
    "get_platform_admin_query_handler",
]


@pytest.mark.parametrize("provider_name", DB_ONLY_QUERY_PROVIDERS)
def test_di_provider_resolves_without_nameerror(provider_name: str) -> None:
    provider = getattr(deps, provider_name)
    handler = provider(db=MagicMock())
    assert handler is not None
