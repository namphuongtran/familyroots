"""Every notified event type has a title+body in every locale (not a raw key)."""

import pytest

from app.services.translator import _translations, load_translations

_TYPES = ["death_anniversary", "birthday", "wedding_anniversary"]
_LOCALES = ["vi", "en", "zh", "fr"]


@pytest.mark.parametrize("etype", _TYPES)
@pytest.mark.parametrize("locale", _LOCALES)
def test_title_and_body_exist_in_every_locale(etype: str, locale: str) -> None:
    load_translations()
    table = _translations[locale]
    for suffix in ("title", "body"):
        key = f"notification.{etype}.{suffix}"
        assert table.get(key), f"{locale} missing {key}"


def test_flat_notification_keys_removed() -> None:
    load_translations()
    for etype in _TYPES:
        assert f"notification.{etype}" not in _translations["vi"]
