"""Translation service — load JSON translation files and resolve localized strings."""

import json
from pathlib import Path

from app.core.locale import current_locale

_translations: dict[str, dict[str, str]] = {}


def load_translations() -> None:
    """Load all translation JSON files from the i18n directory."""
    i18n_dir = Path(__file__).parent.parent / "i18n"
    for f in i18n_dir.glob("*.json"):
        lang = f.stem
        _translations[lang] = json.loads(f.read_text(encoding="utf-8"))


def t(key: str, *, locale: str | None = None, **kwargs: object) -> str:
    """Translate a key. Uses ``locale`` when given, else the current request locale.

    Falls back to Vietnamese (vi) if the key is missing in the chosen locale, and
    returns the raw key if missing everywhere. The explicit ``locale`` override exists
    for contexts with no request contextvar (e.g. the notification job sending in each
    recipient's ``user_profiles.language``).

    Usage::

        t("error.member_not_found")                        # request locale
        t("notification.body", locale="en", name="An")      # explicit locale
    """
    loc = locale or current_locale.get()
    text = _translations.get(loc, {}).get(key) or _translations.get("vi", {}).get(key, key)
    return text.format(**kwargs) if kwargs else text
