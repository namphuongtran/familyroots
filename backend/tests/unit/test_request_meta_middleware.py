"""_validated_ip: malformed IPs are NULLed *and* logged (never silent) —
the ordinary no-IP path stays quiet."""

import logging
from collections.abc import Iterator

import pytest

from app.middleware.request_meta_middleware import _validated_ip

_LOGGER_NAME = "app.middleware.request_meta_middleware"


@pytest.fixture(autouse=True)
def _ensure_logger_enabled() -> Iterator[None]:
    """Guard against cross-test pollution: ``migrations/env.py`` calls
    ``logging.config.fileConfig`` (default ``disable_existing_loggers=True``)
    when integration tests run migrations earlier in the same pytest session,
    which permanently flips ``.disabled`` on any module logger already created
    — including this one — for the rest of the process. Unrelated to the
    behavior under test, so pin it enabled here."""
    target = logging.getLogger(_LOGGER_NAME)
    original = target.disabled
    target.disabled = False
    try:
        yield
    finally:
        target.disabled = original


def test_unparseable_ip_is_nulled_and_warns(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        result = _validated_ip("not-an-ip")

    assert result is None
    assert len(caplog.records) == 1
    message = caplog.records[0].getMessage()
    assert "not-an-ip" in message
    assert "discarding unparseable client IP" in message


def test_valid_ip_passes_through_without_warning(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        result = _validated_ip("127.0.0.1")

    assert result == "127.0.0.1"
    assert caplog.records == []


def test_none_ip_passes_through_without_warning(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        result = _validated_ip(None)

    assert result is None
    assert caplog.records == []
