"""Every error code raised in the app must have an i18n key (in the vi fallback).

The translator falls back to vi and then to the raw key, so a missing key means
the user sees a machine code instead of a message. This test enumerates the codes
passed to the error constructors and asserts each has an ``error.<code>`` entry in
vi.json, turning "forgot to add a translation" into a CI failure.
"""

import json
import pathlib
import re

_APP = pathlib.Path(__file__).resolve().parents[2] / "app"
_ERR_CTOR = re.compile(
    r"\b(?:NotFoundError|ForbiddenError|ConflictError|ValidationError|AuthenticationError|"
    r"EntityNotFoundError|BusinessRuleViolation)\(\s*\"([^\"]+)\""
)
_APPERR = re.compile(r"\bAppError\(\s*\d+\s*,\s*\"([^\"]+)\"")

# Generic codes emitted by the normalizing handlers / catch-alls, not raised directly.
_HANDLER_CODES = {
    "bad_request",
    "unauthorized",
    "forbidden",
    "not_found",
    "method_not_allowed",
    "conflict",
    "validation_error",
    "rate_limited",
    "http_error",
    "internal_error",
    "auth_provider_unavailable",
}


def _raised_codes() -> set[str]:
    codes: set[str] = set()
    for f in _APP.rglob("*.py"):
        text = f.read_text(encoding="utf-8")
        codes |= set(_ERR_CTOR.findall(text))
        codes |= set(_APPERR.findall(text))
    return codes


def test_every_error_code_has_a_vi_i18n_key() -> None:
    vi = json.loads((_APP / "i18n" / "vi.json").read_text(encoding="utf-8"))
    keys = {k[len("error.") :] for k in vi if k.startswith("error.")}
    expected = _raised_codes() | _HANDLER_CODES
    missing = sorted(expected - keys)
    assert not missing, f"Missing error.<code> i18n keys in vi.json: {missing}"


def test_all_locales_have_matching_error_keys() -> None:
    i18n = _APP / "i18n"
    per_locale = {
        p.stem: {k for k in json.loads(p.read_text(encoding="utf-8")) if k.startswith("error.")}
        for p in i18n.glob("*.json")
    }
    union = set().union(*per_locale.values())
    for locale, keys in per_locale.items():
        missing = sorted(union - keys)
        assert not missing, f"{locale}.json is missing error keys: {missing}"
