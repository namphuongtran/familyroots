"""Smoke tests for the FastAPI DI providers in app.infrastructure.dependencies.

Regression for a NameError shipped on main: the auth handler providers referenced
their handler class (AuthCommandHandler / AuthQueryHandler / FCMTokenHandler) but
only imported it under ``if TYPE_CHECKING`` — so every auth endpoint 500'd at
runtime. These providers build handlers without touching the DB at construction
time, so calling them with a mock session must not raise NameError.
"""

from unittest.mock import MagicMock

from app.application.auth.handlers import AuthQueryHandler, FCMTokenHandler
from app.infrastructure.dependencies import (
    get_auth_query_handler,
    get_fcm_token_handler,
)


def test_get_auth_query_handler_resolves() -> None:
    handler = get_auth_query_handler(db=MagicMock())
    assert isinstance(handler, AuthQueryHandler)


def test_get_fcm_token_handler_resolves() -> None:
    handler = get_fcm_token_handler(db=MagicMock())
    assert isinstance(handler, FCMTokenHandler)
