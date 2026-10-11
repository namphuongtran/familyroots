"""SupabaseStorageAdapter.get_presigned_urls signs many paths in bounded calls (#271).

The faked SDK client answers the way local storage-api v1.77.5 answered on
2026-10-11. ``create_signed_urls`` is one ``POST object/sign/{bucket}`` for the
whole list. Storage refuses a list of more than 1000 paths, and an empty list,
with a 400. It reports a missing object per item, inside a 200:
``{"error": "Either the object does not exist or you do not have access to it",
"path": ..., "signedURL": None}``. The single-path sign answers the same object
with a 404 ``not_found``, which the adapter raises as ``StorageNotFoundError``.
Both look up the object only, never the bucket (storage-api's ``signObjectUrl`` and
``signObjectUrls``, read in the v1.77.5 container on 2026-10-11).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from storage3.exceptions import StorageApiError

from app.domain.document.repository import StorageNotFoundError, StorageUnavailableError

pytestmark = pytest.mark.asyncio

_MISSING = "Either the object does not exist or you do not have access to it"
_STORAGE_LIMIT = 1000


class FakeFilesApi:
    """``client.storage.from_(bucket)``, signing the way Storage does."""

    def __init__(self, missing: frozenset[str] = frozenset()) -> None:
        self.missing = missing
        self.missing_error = _MISSING
        self.batch_calls: list[list[str]] = []
        self.single_calls: list[str] = []

    def create_signed_urls(self, paths: list[str], expires_in: int) -> list[dict[str, Any]]:
        self.batch_calls.append(list(paths))
        if not paths:
            raise StorageApiError("body/paths must NOT have fewer than 1 items", "Error", "400")
        if len(paths) > _STORAGE_LIMIT:
            raise StorageApiError("body/paths must NOT have more than 1000 items", "Error", "400")
        items: list[dict[str, Any]] = []
        for path in paths:
            if path in self.missing:
                items.append({"error": self.missing_error, "path": path, "signedURL": None})
            else:
                url = f"https://storage.example/sign/{path}?ttl={expires_in}"
                items.append({"error": None, "path": path, "signedURL": url})
        return items

    def create_signed_url(self, path: str, expires_in: int) -> dict[str, Any]:
        self.single_calls.append(path)
        raise AssertionError("the batch presign must not sign one path at a time")


def _install(monkeypatch: pytest.MonkeyPatch, files_api: Any) -> None:
    from app.infrastructure.storage import supabase_adapter as mod

    client = MagicMock()
    client.storage.from_.return_value = files_api
    monkeypatch.setattr(mod, "get_service_client", lambda: client)


async def _sign(paths: list[str], expires_in: int = 3600) -> dict[str, str]:
    from app.infrastructure.storage.supabase_adapter import SupabaseStorageAdapter

    return await SupabaseStorageAdapter().get_presigned_urls(paths, expires_in)


async def test_2500_paths_are_signed_in_three_calls_each_url_its_own_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    files_api = FakeFilesApi()
    _install(monkeypatch, files_api)
    paths = [f"clans/c/documents/{i}.png" for i in range(2500)]

    urls = await _sign(paths, 600)

    assert [len(call) for call in files_api.batch_calls] == [1000, 1000, 500]
    assert files_api.single_calls == []
    assert urls == {p: f"https://storage.example/sign/{p}?ttl=600" for p in paths}


async def test_no_paths_makes_no_call(monkeypatch: pytest.MonkeyPatch) -> None:
    files_api = FakeFilesApi()
    _install(monkeypatch, files_api)

    assert await _sign([]) == {}
    assert files_api.batch_calls == []


@pytest.mark.parametrize("error", [_MISSING, "worded some other way"])
async def test_an_item_storage_could_not_sign_is_not_found(
    monkeypatch: pytest.MonkeyPatch, error: str
) -> None:
    """The single sign answers a missing object with a 404 type, so the batch must
    too. Storage sets an item's error only when its object lookup found no row, so
    the adapter does not depend on the error's wording."""
    files_api = FakeFilesApi(missing=frozenset({"b.png"}))
    files_api.missing_error = error
    _install(monkeypatch, files_api)

    with pytest.raises(StorageNotFoundError):
        await _sign(["a.png", "b.png", "c.png"])


@pytest.mark.parametrize(
    "items",
    [
        pytest.param([{"error": None, "path": "a.png", "signedURL": None}], id="null-url"),
        pytest.param([{"error": None, "path": "a.png", "signedURL": ""}], id="empty-url"),
        pytest.param([], id="path-absent"),
        pytest.param(
            [{"error": None, "path": "other.png", "signedURL": "https://x/other"}],
            id="another-path",
        ),
    ],
)
async def test_a_path_storage_returns_no_url_for_is_unavailable(
    monkeypatch: pytest.MonkeyPatch, items: list[dict[str, Any]]
) -> None:
    """As the single-path sign: a 200 that hands back no URL for a path is a
    provider fault (503), never a ``None`` passed on as a URL."""
    files_api = MagicMock()
    files_api.create_signed_urls.return_value = items
    _install(monkeypatch, files_api)

    with pytest.raises(StorageUnavailableError):
        await _sign(["a.png"])


@pytest.mark.parametrize(
    "exc",
    [
        pytest.param(StorageApiError("boom", "internal_error", "500"), id="provider-5xx"),
        pytest.param(ConnectionError("dns failure"), id="transport"),
        pytest.param(StorageApiError("Bucket not found", "error", "400"), id="bucket-not-found"),
        pytest.param(StorageApiError("Object not found", "not_found", "404"), id="object-404"),
        pytest.param(StorageApiError("Duplicate", "duplicate", "409"), id="unexpected-4xx"),
    ],
)
async def test_a_failed_call_raises_what_the_single_sign_raises(
    monkeypatch: pytest.MonkeyPatch, exc: Exception
) -> None:
    """The same SDK failure, through both signs: the batch must raise the same type."""
    from app.infrastructure.storage.supabase_adapter import SupabaseStorageAdapter

    files_api = MagicMock()
    files_api.create_signed_url.side_effect = exc
    files_api.create_signed_urls.side_effect = exc
    _install(monkeypatch, files_api)

    with pytest.raises(Exception) as single:
        await SupabaseStorageAdapter().get_presigned_url("a.png")
    with pytest.raises(Exception) as batch:
        await _sign(["a.png"])
    assert type(batch.value) is type(single.value)
