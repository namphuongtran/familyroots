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
@pytest.mark.parametrize("signed_url", [None, ""])
async def test_get_presigned_url_rejects_empty_signed_url(
    monkeypatch: pytest.MonkeyPatch, signed_url: str | None
) -> None:
    """A 200 with no URL must 503, not hand ``None`` back as if it were a URL.

    storage3 2.31 types ``signedURL`` as ``str | None``; before that the adapter
    returned whatever was in the key unchecked.
    """
    from app.infrastructure.storage import supabase_adapter as mod

    bucket = MagicMock()
    bucket.create_signed_url.return_value = {"signedURL": signed_url}
    client = MagicMock()
    client.storage.from_.return_value = bucket
    monkeypatch.setattr(mod, "get_service_client", lambda: client)

    with pytest.raises(StorageUnavailableError):
        await mod.SupabaseStorageAdapter().get_presigned_url("clans/x/documents/y.jpg")


@pytest.mark.asyncio
async def test_get_presigned_url_returns_url_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.infrastructure.storage import supabase_adapter as mod

    bucket = MagicMock()
    bucket.create_signed_url.return_value = {"signedURL": "https://cdn.example/signed"}
    client = MagicMock()
    client.storage.from_.return_value = bucket
    monkeypatch.setattr(mod, "get_service_client", lambda: client)

    url = await mod.SupabaseStorageAdapter().get_presigned_url("clans/x/documents/y.jpg")
    assert url == "https://cdn.example/signed"


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
async def test_delete_raises_unavailable_on_5xx(monkeypatch: pytest.MonkeyPatch) -> None:
    # delete()'s contract (task 3 review FIX 2): True on success OR confirmed
    # not-found; anything else (transport/provider failure, here a 5xx) must
    # raise the classified StorageError rather than being swallowed — a
    # caller (notably the retention purge job) must be able to tell "gone"
    # apart from "we don't know".
    from app.infrastructure.storage import supabase_adapter as mod

    bucket = MagicMock()
    bucket.remove.side_effect = StorageApiError("boom", "internal_error", 500)
    client = MagicMock()
    client.storage.from_.return_value = bucket
    monkeypatch.setattr(mod, "get_service_client", lambda: client)

    with pytest.raises(StorageUnavailableError):
        await mod.SupabaseStorageAdapter().delete("clans/x/documents/y.jpg")


@pytest.mark.asyncio
async def test_delete_returns_true_on_confirmed_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    # A 404/not_found response is not a failure — the object is confirmed
    # already absent, which is the same success outcome as actually deleting it.
    from app.infrastructure.storage import supabase_adapter as mod

    bucket = MagicMock()
    bucket.remove.side_effect = StorageApiError("Object not found", "not_found", 404)
    client = MagicMock()
    client.storage.from_.return_value = bucket
    monkeypatch.setattr(mod, "get_service_client", lambda: client)

    result = await mod.SupabaseStorageAdapter().delete("clans/x/documents/y.jpg")

    assert result is True


@pytest.mark.asyncio
async def test_delete_returns_true_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.infrastructure.storage import supabase_adapter as mod

    bucket = MagicMock()
    bucket.remove.return_value = [{"name": "y.jpg"}]
    client = MagicMock()
    client.storage.from_.return_value = bucket
    monkeypatch.setattr(mod, "get_service_client", lambda: client)

    result = await mod.SupabaseStorageAdapter().delete("clans/x/documents/y.jpg")

    assert result is True
