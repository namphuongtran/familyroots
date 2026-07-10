"""_classify_storage maps SDK/transport failures to the storage taxonomy.

Mirrors tests/unit/infrastructure/test_identity_error_classification.py: a
missing object → 404 type, anything infrastructural → 503 type, an unexpected
error → returned unchanged so it stays a loud 500.
"""

from unittest.mock import MagicMock

import pytest
from storage3.exceptions import StorageApiError

from app.domain.document.repository import StorageNotFoundError, StorageUnavailableError
from app.infrastructure.storage.supabase_adapter import _classify_storage


@pytest.mark.parametrize(
    "exc, expected_type",
    [
        (StorageApiError("Object not found", "not_found", 404), StorageNotFoundError),
        (StorageApiError("boom", "internal_error", 500), StorageUnavailableError),
        (StorageApiError("bad key", "invalid_api_key", 401), StorageUnavailableError),
        (ConnectionError("dns failure"), StorageUnavailableError),
        (TimeoutError("timed out"), StorageUnavailableError),
    ],
)
def test_classify_maps_to_storage_error(exc: Exception, expected_type: type) -> None:
    assert isinstance(_classify_storage(exc), expected_type)


def test_classify_reraises_unexpected_4xx_unchanged() -> None:
    # A duplicate/400 is a genuine bug on our uuid+upsert=false paths — keep it loud.
    dup = StorageApiError("Duplicate", "duplicate", 409)
    assert _classify_storage(dup) is dup


@pytest.mark.asyncio
async def test_get_presigned_url_raises_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.infrastructure.storage import supabase_adapter as mod

    bucket = MagicMock()
    bucket.create_signed_url.side_effect = StorageApiError("Object not found", "not_found", 404)
    client = MagicMock()
    client.storage.from_.return_value = bucket
    monkeypatch.setattr(mod, "get_service_client", lambda: client)

    with pytest.raises(StorageNotFoundError):
        await mod.SupabaseStorageAdapter().get_presigned_url("clans/x/documents/y.jpg")


@pytest.mark.asyncio
async def test_upload_raises_unavailable_on_5xx(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.infrastructure.storage import supabase_adapter as mod

    bucket = MagicMock()
    bucket.upload.side_effect = StorageApiError("boom", "internal_error", 500)
    client = MagicMock()
    client.storage.from_.return_value = bucket
    monkeypatch.setattr(mod, "get_service_client", lambda: client)

    with pytest.raises(StorageUnavailableError):
        await mod.SupabaseStorageAdapter().upload("p", b"data", "image/jpeg")


@pytest.mark.asyncio
async def test_delete_swallows_error_and_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    # delete() runs post-commit as best-effort compensation, so it must never
    # raise — any SDK/transport failure must be swallowed and reported as False.
    from app.infrastructure.storage import supabase_adapter as mod

    bucket = MagicMock()
    bucket.remove.side_effect = StorageApiError("boom", "internal_error", 500)
    client = MagicMock()
    client.storage.from_.return_value = bucket
    monkeypatch.setattr(mod, "get_service_client", lambda: client)

    result = await mod.SupabaseStorageAdapter().delete("clans/x/documents/y.jpg")

    assert result is False
