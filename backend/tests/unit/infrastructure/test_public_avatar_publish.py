"""SupabaseStorageAdapter.publish_public — the ADR-036 write path into the public bucket.

Covers what must never happen even once, because the URL it returns is stored
permanently in ``persons.avatar_url``:

* an unconfigured / missing / private bucket must raise a *mapped* error, never
  return a URL that will not resolve;
* the returned URL must be permanent — no query string, so it can never be a
  presigned URL (``Person.set_avatar_url`` rejects those, so a regression here
  would surface as a 422 rather than a rotting column, but this pins it at the
  source);
* the destination path must be preserved verbatim, since it carries the clan
  prefix that keeps one clan's avatars out of another clan's namespace.

The Supabase SDK is faked — no network, no real bucket.
"""

from __future__ import annotations

from typing import Any

import pytest
from storage3.exceptions import StorageApiError

from app.core.config import settings
from app.domain.document.repository import (
    StorageBucketNotConfiguredError,
    StorageNotFoundError,
    StorageUnavailableError,
)
from app.infrastructure.storage import supabase_adapter as adapter_module
from app.infrastructure.storage.supabase_adapter import SupabaseStorageAdapter

pytestmark = pytest.mark.asyncio

_SOURCE = "clans/11111111-1111-1111-1111-111111111111/documents/abc.jpg"
_DEST = "clans/11111111-1111-1111-1111-111111111111/avatars/22222222-2222-2222-2222-222222222222"


class _FakeBucketInfo:
    def __init__(self, public: bool) -> None:
        self.public = public


class _FakeBucketApi:
    def __init__(self, parent: _FakeStorage, name: str) -> None:
        self._parent = parent
        self._name = name

    def download(self, path: str) -> bytes:
        if self._parent.download_error is not None:
            raise self._parent.download_error
        self._parent.downloaded.append((self._name, path))
        return b"\x89PNG\r\n\x1a\n"

    def upload(self, *, path: str, file: bytes, file_options: dict[str, str]) -> None:
        if self._parent.upload_error is not None:
            raise self._parent.upload_error
        self._parent.uploaded.append((self._name, path, file_options))


class _FakeStorage:
    def __init__(
        self,
        *,
        bucket_info: _FakeBucketInfo | None = None,
        get_bucket_error: Exception | None = None,
        download_error: Exception | None = None,
        upload_error: Exception | None = None,
    ) -> None:
        self._bucket_info = bucket_info or _FakeBucketInfo(public=True)
        self.get_bucket_error = get_bucket_error
        self.download_error = download_error
        self.upload_error = upload_error
        self.downloaded: list[tuple[str, str]] = []
        self.uploaded: list[tuple[str, str, dict[str, str]]] = []

    def get_bucket(self, name: str) -> _FakeBucketInfo:
        if self.get_bucket_error is not None:
            raise self.get_bucket_error
        return self._bucket_info

    def from_(self, name: str) -> _FakeBucketApi:
        return _FakeBucketApi(self, name)


class _FakeClient:
    def __init__(self, storage: _FakeStorage) -> None:
        self.storage = storage


def _api_error(message: str, status: str = "400") -> StorageApiError:
    return StorageApiError(message=message, code="error", status=status)


@pytest.fixture()
def configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_AVATAR_BUCKET", "family-roots-avatars")
    monkeypatch.setattr(settings, "SUPABASE_STORAGE_BUCKET", "family-roots-files")
    monkeypatch.setattr(settings, "AVATAR_CACHE_CONTROL_SECONDS", 300)


def _install(monkeypatch: pytest.MonkeyPatch, storage: _FakeStorage) -> None:
    monkeypatch.setattr(
        adapter_module, "get_service_client", lambda: _FakeClient(storage), raising=True
    )


async def _publish(**kwargs: Any) -> str:
    return await SupabaseStorageAdapter().publish_public(
        source_path=_SOURCE, destination_path=_DEST, content_type="image/jpeg", **kwargs
    )


async def test_publishes_and_returns_a_permanent_public_url(
    configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = _FakeStorage()
    _install(monkeypatch, storage)

    url = await _publish()

    assert url == f"https://proj.supabase.co/storage/v1/object/public/family-roots-avatars/{_DEST}"
    # Permanent means: no signature, no expiry, therefore no query string at all.
    assert "?" not in url and "#" not in url
    assert "token=" not in url
    assert storage.downloaded == [("family-roots-files", _SOURCE)]
    bucket, path, options = storage.uploaded[0]
    assert (bucket, path) == ("family-roots-avatars", _DEST)  # clan prefix preserved verbatim
    assert options["upsert"] == "true"  # stable per-person path: replace, don't collide
    assert options["cache-control"] == "max-age=300"
    assert options["content-type"] == "image/jpeg"


async def test_missing_bucket_raises_the_mapped_config_error(
    configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The bucket must be created by hand in Supabase. Until it is, the write path
    fails loudly with its own 503 code — not a 404, not a 500, and above all not a
    success that stores an unresolvable URL."""
    storage = _FakeStorage(get_bucket_error=_api_error("Bucket not found", status="404"))
    _install(monkeypatch, storage)

    with pytest.raises(StorageBucketNotConfiguredError):
        await _publish()
    assert storage.uploaded == []  # nothing was published


async def test_private_bucket_is_refused(configured: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """A bucket that exists but is not public-read would accept the upload happily
    and yield a URL that 400s for every anonymous reader — refuse before copying."""
    storage = _FakeStorage(bucket_info=_FakeBucketInfo(public=False))
    _install(monkeypatch, storage)

    with pytest.raises(StorageBucketNotConfiguredError):
        await _publish()
    assert storage.uploaded == []


async def test_empty_bucket_setting_raises_before_touching_the_network(
    configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "SUPABASE_AVATAR_BUCKET", "   ")
    storage = _FakeStorage()
    _install(monkeypatch, storage)

    with pytest.raises(StorageBucketNotConfiguredError):
        await _publish()
    assert storage.downloaded == [] and storage.uploaded == []


async def test_missing_supabase_url_raises_rather_than_building_a_relative_url(
    configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "SUPABASE_URL", "")
    storage = _FakeStorage()
    _install(monkeypatch, storage)

    with pytest.raises(StorageBucketNotConfiguredError):
        await _publish()


async def test_missing_source_object_is_a_404_not_a_bucket_problem(
    configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = _FakeStorage(download_error=_api_error("Object not found", status="404"))
    _install(monkeypatch, storage)

    with pytest.raises(StorageNotFoundError):
        await _publish()


async def test_provider_outage_on_upload_is_503_unavailable(
    configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = _FakeStorage(upload_error=_api_error("upstream boom", status="500"))
    _install(monkeypatch, storage)

    with pytest.raises(StorageUnavailableError):
        await _publish()
