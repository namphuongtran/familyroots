"""The integration harness' throwaway database name is configurable.

`migrated_db_url` drops its database with `WITH (FORCE)`, which terminates every
other backend connected to it. Two suites sharing one name therefore wipe each
other's schema mid-run. These tests pin the two properties that make parallel
runs safe: the default is unchanged (so existing invocations behave identically)
and the override is honoured.
"""

import pytest

from tests.integration.conftest import (
    DEFAULT_TEST_DB_NAME,
    TEST_DB_NAME_ENV,
    resolve_test_db_name,
)

pytestmark = pytest.mark.unit


def test_default_is_unchanged_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every invocation that sets nothing must target the historical name."""
    monkeypatch.delenv(TEST_DB_NAME_ENV, raising=False)
    assert resolve_test_db_name() == "family_roots_schema_test"
    assert DEFAULT_TEST_DB_NAME == "family_roots_schema_test"


def test_environment_override_is_honoured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(TEST_DB_NAME_ENV, "family_roots_schema_test_agent_b")
    assert resolve_test_db_name() == "family_roots_schema_test_agent_b"


@pytest.mark.parametrize(
    "value",
    [
        "",  # empty: would produce DROP DATABASE ""
        "9lives",  # leading digit is not a valid unquoted identifier
        "has-a-dash",
        "has a space",
        'quote"injection',
        '"; DROP DATABASE postgres; --',
        "a" * 64,  # NAMEDATALEN-1 is 63; Postgres would silently truncate
    ],
)
def test_unusable_names_are_rejected(value: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """The name is interpolated into DROP/CREATE DATABASE, which takes no bind
    parameter. A literal constant was safe by construction; an env var is not,
    and an over-long name would be truncated into a collision with the very run
    the override exists to keep apart."""
    monkeypatch.setenv(TEST_DB_NAME_ENV, value)
    with pytest.raises(ValueError, match=TEST_DB_NAME_ENV):
        resolve_test_db_name()


def test_63_characters_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    """The boundary itself is legal — the guard must not be off by one."""
    monkeypatch.setenv(TEST_DB_NAME_ENV, "a" * 63)
    assert resolve_test_db_name() == "a" * 63
