"""Translation service — load JSON translation files and resolve localized strings."""

import json
from pathlib import Path

from app.middleware.language_middleware import current_locale

_translations: dict[str, dict[str, str]] = {}


def load_translations() -> None:
    """Load all translation JSON files from the i18n directory."""
    i18n_dir = Path(__file__).parent.parent / "i18n"
    for f in i18n_dir.glob("*.json"):
        lang = f.stem
        _translations[lang] = json.loads(f.read_text(encoding="utf-8"))


def t(key: str, **kwargs: object) -> str:
    """Translate a key using the current request locale.

    Falls back to Vietnamese (vi) if the key is not found in the
    current locale, and returns the raw key if not found in any locale.

    Usage::

        from app.services.translator import t
        raise HTTPException(status_code=404, detail=t("error.member_not_found"))
        body = t("notification.death_anniversary", name="Nguyễn Văn A", days=3)
    """
    locale = current_locale.get()
    text = _translations.get(locale, {}).get(key) or _translations.get("vi", {}).get(key, key)
    return text.format(**kwargs) if kwargs else text
