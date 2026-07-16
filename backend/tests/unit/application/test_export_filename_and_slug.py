"""Clan slug hygiene: strict at the door, sanitized at the export header.

The slug lands in a Content-Disposition response header
(`attachment; filename="{slug}-gia-pha-....json"`). Headers are latin-1: a
Vietnamese-diacritic slug raised UnicodeEncodeError → 500 on export, and a
double quote broke the quoted filename. Two layers:

1. Input validation — new slugs must match ^[a-z0-9]+(-[a-z0-9]+)*$.
2. Export sanitization — slugs created before the validation existed still
   export safely (diacritics transliterated, junk stripped, never empty).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.application.export.handlers import filename_slug
from app.schemas.auth import AuthenticatedOnboardingRequest, RegisterRequest

# ── export filename sanitization ─────────────────────────────────────────────


def test_vietnamese_diacritics_transliterated() -> None:
    assert filename_slug("dòng-họ-đinh") == "dong-ho-dinh"


def test_result_is_always_header_safe() -> None:
    for raw in ['a"b', "họ “Nguyễn”", "x\r\ny", "  ", "日本語"]:
        out = filename_slug(raw)
        out.encode("latin-1")  # must never raise
        assert '"' not in out and "\r" not in out and "\n" not in out
        assert out  # never empty — header must stay well-formed


def test_hostile_input_falls_back_to_clan() -> None:
    assert filename_slug("日本語") == "clan"
    assert filename_slug("") == "clan"


def test_clean_slug_passes_through() -> None:
    assert filename_slug("nguyen-van") == "nguyen-van"


# ── input validation on clan creation ────────────────────────────────────────

_REGISTER_BASE = {
    "email": "a@example.com",
    "password": "longenough",
    "full_name": "Nguyễn Văn A",
    "clan_action": "create",
    "clan_name": "Dòng họ Nguyễn",
}


@pytest.mark.parametrize("bad", ["Dòng Họ", "UPPER", "a b", 'x"y', "-lead", "trail-", "a--b", ""])
def test_register_rejects_invalid_slug(bad: str) -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(**_REGISTER_BASE, clan_slug=bad)


@pytest.mark.parametrize("good", ["nguyen", "dong-ho-nguyen", "clan2", "a-1-b"])
def test_register_accepts_valid_slug(good: str) -> None:
    assert RegisterRequest(**_REGISTER_BASE, clan_slug=good).clan_slug == good


def test_onboard_rejects_invalid_slug() -> None:
    with pytest.raises(ValidationError):
        AuthenticatedOnboardingRequest(
            clan_action="create", clan_name="Dòng họ", clan_slug="dòng-họ"
        )
