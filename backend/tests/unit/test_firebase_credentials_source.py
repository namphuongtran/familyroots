"""`init_firebase` builds the Firebase app from `FIREBASE_CREDENTIALS_JSON`, else the path.

ADR-065: a Vercel Function has no file mount, so the service account has to be able to
arrive inline. These tests read the outcome: the ``firebase_admin`` app that pushes would
be sent through, and the service account it was built from. No network is touched,
because building a credential from a service account only parses the private key, and a
throwaway RSA key generated here is a real one.

The inline value is a secret. The last tests plant a recognisable marker in a value that
cannot become credentials, and require that the marker appears in no log record.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path

import firebase_admin
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.services import notification

pytestmark = pytest.mark.unit

_INLINE_EMAIL = "inline@familyroots-test.iam.gserviceaccount.com"
_FILE_EMAIL = "file@familyroots-test.iam.gserviceaccount.com"
_MARKER = "SECRET-MARKER-7f3a9c"


@pytest.fixture(scope="module")
def private_key_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


def _service_account(private_key_pem: str, email: str) -> dict[str, str]:
    return {
        "type": "service_account",
        "project_id": "familyroots-test",
        "private_key_id": "test-key-id",
        "private_key": private_key_pem,
        "client_email": email,
        "client_id": "0",
        "token_uri": "https://oauth2.googleapis.com/token",
    }


@pytest.fixture(autouse=True)
def no_firebase_app(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Start with no app, and delete whatever the test built, so tests stay independent."""
    monkeypatch.setattr(notification, "_firebase_app", None)
    yield
    built = notification._firebase_app
    if built is not None:
        firebase_admin.delete_app(built)


def _configure(monkeypatch: pytest.MonkeyPatch, *, inline: str, path: str) -> None:
    # By dotted path, so the patch lands on the settings object the module actually reads.
    monkeypatch.setattr("app.services.notification.settings.FIREBASE_CREDENTIALS_JSON", inline)
    monkeypatch.setattr("app.services.notification.settings.FIREBASE_CREDENTIALS_PATH", path)


def _built_email() -> str | None:
    built = notification._firebase_app
    if built is None:
        return None
    email = built.credential.service_account_email
    assert isinstance(email, str)
    return email


def test_the_inline_json_builds_the_app(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, private_key_pem: str
) -> None:
    inline = json.dumps(_service_account(private_key_pem, _INLINE_EMAIL))
    _configure(monkeypatch, inline=inline, path=str(tmp_path / "absent.json"))

    notification.init_firebase()

    assert _built_email() == _INLINE_EMAIL
    assert notification._firebase_app is not None
    assert notification._firebase_app.project_id == "familyroots-test"


def test_the_inline_json_wins_over_a_valid_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, private_key_pem: str
) -> None:
    key_file = tmp_path / "firebase-credentials.json"
    key_file.write_text(json.dumps(_service_account(private_key_pem, _FILE_EMAIL)))
    inline = json.dumps(_service_account(private_key_pem, _INLINE_EMAIL))
    _configure(monkeypatch, inline=inline, path=str(key_file))

    notification.init_firebase()

    assert _built_email() == _INLINE_EMAIL


def test_without_inline_json_the_file_is_used(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, private_key_pem: str
) -> None:
    key_file = tmp_path / "firebase-credentials.json"
    key_file.write_text(json.dumps(_service_account(private_key_pem, _FILE_EMAIL)))
    _configure(monkeypatch, inline="", path=str(key_file))

    notification.init_firebase()

    assert _built_email() == _FILE_EMAIL


def test_with_neither_pushes_are_disabled_and_boot_continues(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _configure(monkeypatch, inline="", path=str(tmp_path / "absent.json"))
    with caplog.at_level(logging.WARNING, logger="app.services.notification"):
        notification.init_firebase()
    assert notification._firebase_app is None
    assert any("Firebase init skipped" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize(
    "inline",
    [
        f'{{"type": "service_account", "private_key": "{_MARKER}"',  # truncated JSON
        json.dumps(f"/run/secrets/{_MARKER}"),  # a JSON string: Certificate reads it as a path
        json.dumps([_MARKER]),  # a JSON array: Certificate echoes it in its ValueError
        json.dumps({"type": "service_account", "private_key": _MARKER}),  # not a usable key
    ],
    ids=["malformed", "a-string", "an-array", "an-object-without-a-usable-key"],
)
def test_an_unusable_inline_value_disables_pushes_without_logging_it(
    inline: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _configure(monkeypatch, inline=inline, path=str(tmp_path / "absent.json"))
    with caplog.at_level(logging.DEBUG):
        notification.init_firebase()

    assert notification._firebase_app is None
    assert any("Firebase init skipped" in r.getMessage() for r in caplog.records)
    leaked = [r.getMessage() for r in caplog.records if _MARKER in r.getMessage()]
    assert leaked == [], leaked
