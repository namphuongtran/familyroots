"""Smoke test for every FastAPI DI provider in app.infrastructure.dependencies.

Regression guard for the class of bug that shipped on main: a provider that
referenced its handler class without importing it (it was under ``TYPE_CHECKING``)
raised ``NameError`` only at request time — invisible to mypy and to handler unit
tests. dependencies.py now imports everything at module level and each provider
only wires collaborators, so:

- importing the module catches any missing/typo'd import (ImportError), and
- invoking every provider with a mock session catches any wiring/construction bug.

The provider list is discovered dynamically, so new providers are covered
automatically. Providers construct repos/query-ports/handlers (and the Supabase
adapters, which create their SDK client lazily inside methods) without any DB or
network I/O at construction, so a MagicMock session is sufficient.
"""

import inspect
from unittest.mock import MagicMock

import pytest

from app.infrastructure import dependencies as deps

PROVIDERS = sorted(
    name
    for name in dir(deps)
    if name.startswith("get_") and callable(getattr(deps, name))
)


def test_providers_are_discovered() -> None:
    # Guard against the discovery silently finding nothing (which would make the
    # parametrized test vacuously pass).
    assert len(PROVIDERS) >= 20, PROVIDERS


@pytest.mark.parametrize("provider_name", PROVIDERS)
def test_di_provider_wires_without_error(provider_name: str) -> None:
    provider = getattr(deps, provider_name)
    params = inspect.signature(provider).parameters
    kwargs = {"db": MagicMock()} if "db" in params else {}
    assert provider(**kwargs) is not None
