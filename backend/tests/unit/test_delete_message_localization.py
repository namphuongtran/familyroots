"""Delete/avatar response messages must be localized in every locale.

Six routes hardcoded English ("Marriage deleted", "Event deleted", …) while
persons used t("person.deleted") — whose key didn't even exist, so it emitted
the raw key. Accept-Language was honored on some deletes and ignored on
others. Every message key must exist in all four locale files (the translator
falls back vi → raw key, so a missing key ships the key string to clients).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_I18N_DIR = Path(__file__).resolve().parents[2] / "app" / "i18n"
_LOCALES = ["vi", "en", "zh", "fr"]
_REQUIRED_KEYS = [
    "person.deleted",
    "marriage.deleted",
    "parent_child.deleted",
    "event.deleted",
    "branch.deleted",
    "document.deleted",
    "document.avatar_set",
]


@pytest.mark.parametrize("locale", _LOCALES)
def test_all_delete_message_keys_exist(locale: str) -> None:
    catalog = json.loads((_I18N_DIR / f"{locale}.json").read_text(encoding="utf-8"))
    missing = [k for k in _REQUIRED_KEYS if not catalog.get(k)]
    assert not missing, f"{locale}.json missing translations: {missing}"
