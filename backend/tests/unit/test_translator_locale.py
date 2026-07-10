"""t() honors an explicit locale override, and still falls back to the contextvar.

NOTE: The Task-1 brief's example asserts `notification.birthday.title`, which is
added in Task 2. To keep this task's commit green and self-contained, this test
asserts the same three behaviors (explicit override wins, contextvar fallback,
unknown-locale fallback to vi) against `kinship.child` — a key already present
in all four locale files (vi/en/zh/fr) — reading expected values from the
loaded translation table instead of hardcoding translated strings.
"""

from app.core.locale import current_locale
from app.services.translator import _translations, load_translations, t

_KEY = "kinship.child"  # exists in all locales; swap only if grep shows it doesn't


def test_explicit_locale_overrides_contextvar() -> None:
    load_translations()
    token = current_locale.set("vi")
    try:
        # Explicit en wins over the vi contextvar.
        assert t(_KEY, locale="en") == _translations["en"][_KEY]
        # Omitting locale still uses the contextvar (vi).
        assert t(_KEY) == _translations["vi"][_KEY]
    finally:
        current_locale.reset(token)


def test_unknown_locale_falls_back_to_vi() -> None:
    load_translations()
    # 'zz' has no file → fall back to vi text, not the raw key.
    assert t(_KEY, locale="zz") == _translations["vi"][_KEY]
