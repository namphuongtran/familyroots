"""Supabase implementation of the StoragePort protocol.

Keeps the application/domain layers free of Supabase SDK imports. The blocking
storage3 SDK is synchronous, so every call is off-loaded with asyncio.to_thread
to avoid freezing the event loop; failures are classified into the domain
StorageError taxonomy (mirroring the identity provider).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any
from urllib.parse import quote

from storage3.exceptions import StorageApiError
from storage3.types import ListBucketFilesOptions

from app.core.config import settings
from app.domain.document.repository import (
    DEFAULT_PRESIGN_TTL,
    SignedUpload,
    StorageBucketNotConfiguredError,
    StorageError,
    StorageNotFoundError,
    StorageUnavailableError,
    StoredObject,
)
from app.domain.document.storage_paths import CLANS_ROOT, STAGING_FOLDER
from app.infrastructure.supabase_client import get_service_client

logger = logging.getLogger(__name__)

# Storage's list endpoint pages its results; 100 is its default page size.
_LIST_PAGE_SIZE = 100

# Storage's batch sign refuses more than 1000 paths in one request, and an empty
# list, each with a 400: "body/paths must NOT have more than 1000 items". It is
# storage-api's MAX_OBJECTS_PER_REQUEST; measured on local v1.77.5 on 2026-10-11.
_SIGN_BATCH_SIZE = 1000


def _parse_storage_timestamp(value: object) -> datetime | None:
    """Storage reports ``created_at`` as ISO 8601 with a ``Z`` suffix."""
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _classify_storage(exc: Exception) -> Exception:
    """Map a storage SDK/transport failure to a domain StorageError.

    Missing object → StorageNotFoundError (404); provider 5xx / rejected key /
    transport failure → StorageUnavailableError (503); a genuinely unexpected
    error is returned unchanged so ``raise _classify_storage(e)`` keeps it a
    loud 500 rather than silently downgrading a code bug."""
    if isinstance(exc, StorageError):
        return exc
    if isinstance(exc, StorageApiError):
        info: Mapping[str, object] = {}
        with contextlib.suppress(Exception):  # defensive: never let classification raise
            info = exc.to_dict()
        status = str(info.get("status") or "")
        code = str(info.get("code") or "").lower()
        msg = str(info.get("message") or exc).lower()
        if status == "404" or "not_found" in code or "not found" in msg:
            return StorageNotFoundError(str(exc))
        if (
            status.startswith("5")
            or "api key" in msg
            or "apikey" in code
            or "invalid_api_key" in code
            or "unauthorized" in code + msg
        ):
            return StorageUnavailableError(str(exc))
        return exc  # unexpected 4xx (e.g. duplicate) — stay loud (500)
    return StorageUnavailableError(str(exc))  # transport / non-HTTP failure


def _classify_bucket(exc: Exception, bucket: str) -> Exception:
    """Like ``_classify_storage``, but recognises a missing/inaccessible BUCKET first.

    Supabase reports a missing bucket as a 400/404 whose message is "Bucket not
    found" — which ``_classify_storage`` would read as a missing *object* and turn
    into a 404 ``storage_not_found``, blaming the caller for our own infrastructure
    gap. Every call on a bucket goes through here, the private
    ``SUPABASE_STORAGE_BUCKET`` as much as the public avatars one: neither is created
    by this code, and the hosted project had no buckets at all until 2026-10-04 (#177).
    For ``delete`` the distinction is not cosmetic — a missing object is success, a
    missing bucket confirms nothing about the blob.
    """
    if isinstance(exc, StorageApiError):
        info: Mapping[str, object] = {}
        with contextlib.suppress(Exception):  # defensive: never let classification raise
            info = exc.to_dict()
        msg = str(info.get("message") or exc).lower()
        code = str(info.get("code") or "").lower()
        if "bucket not found" in msg or "bucket_not_found" in code or "no such bucket" in msg:
            return StorageBucketNotConfiguredError(
                f"bucket {bucket!r} does not exist or is not reachable with this key"
            )
    return _classify_storage(exc)


def _public_object_url(bucket: str, path: str) -> str:
    """Build Supabase's permanent public-object URL.

    Constructed here rather than via ``get_public_url`` because storage3 appends a
    trailing ``?`` (an empty query string) to that helper's result in some versions,
    and ``Person.set_avatar_url`` rejects any URL with a query string — the guard that
    keeps presigned URLs out of the column would reject our own perfectly good URL.
    """
    return f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1/object/public/{bucket}/" + quote(
        path, safe="/"
    )


class SupabaseStorageAdapter:
    """Concrete storage adapter backed by Supabase Storage.

    Implements both ``StoragePort`` and ``StagedUploadStorage``. No method writes a
    document's bytes: the browser uploads them to a signed URL (ADR-068).
    """

    async def create_signed_upload(self, path: str) -> SignedUpload:
        # No upsert option: a signed path accepts one upload, and a second PUT to the
        # same path is refused by Storage (409 KeyAlreadyExists, measured 2026-10-11).
        client = get_service_client()
        try:
            result = await asyncio.to_thread(
                client.storage.from_(settings.SUPABASE_STORAGE_BUCKET).create_signed_upload_url,
                path,
            )
        except Exception as e:
            raise _classify_bucket(e, settings.SUPABASE_STORAGE_BUCKET) from e
        return SignedUpload(upload_url=result["signed_url"], token=result["token"])

    async def stat(self, path: str) -> StoredObject:
        client = get_service_client()
        try:
            info = await asyncio.to_thread(
                client.storage.from_(settings.SUPABASE_STORAGE_BUCKET).info, path
            )
        except Exception as e:
            raise _classify_bucket(e, settings.SUPABASE_STORAGE_BUCKET) from e
        size = info.get("size")
        if not isinstance(size, int):
            # A success response with no size is a provider fault, like a signed URL
            # with no URL in get_presigned_url below: 503, never a guessed size.
            raise StorageUnavailableError(f"storage returned no size for {path!r}")
        content_type = info.get("content_type")
        return StoredObject(
            size_bytes=size,
            content_type=content_type if isinstance(content_type, str) else None,
        )

    async def move(self, from_path: str, to_path: str) -> None:
        client = get_service_client()
        try:
            await asyncio.to_thread(
                client.storage.from_(settings.SUPABASE_STORAGE_BUCKET).move, from_path, to_path
            )
        except Exception as e:
            raise _classify_bucket(e, settings.SUPABASE_STORAGE_BUCKET) from e

    async def list_staged_uploads_older_than(self, cutoff: datetime) -> list[str]:
        """Every staged upload path created before ``cutoff``, across all clans.

        Used only by the retention purge job's sweep (ADR-068). It lists each clan
        folder's ``uploads/`` and nothing else, so it cannot return a confirmed
        document's path. Storage pages its listings, so both levels are paged.
        """
        bucket = settings.SUPABASE_STORAGE_BUCKET
        files_api = get_service_client().storage.from_(bucket)

        async def list_all(prefix: str) -> list[dict[str, Any]]:
            entries: list[dict[str, Any]] = []
            offset = 0
            while True:
                options: ListBucketFilesOptions = {
                    "limit": _LIST_PAGE_SIZE,
                    "offset": offset,
                    "sortBy": {"column": "name", "order": "asc"},
                }
                try:
                    page = await asyncio.to_thread(files_api.list, prefix, options)
                except Exception as e:
                    raise _classify_bucket(e, bucket) from e
                entries.extend(page)
                if len(page) < _LIST_PAGE_SIZE:
                    return entries
                offset += _LIST_PAGE_SIZE

        stale: list[str] = []
        for clan_folder in await list_all(CLANS_ROOT):
            if clan_folder.get("id") is not None:
                continue  # a file directly under clans/, not a clan folder
            staging = f"{CLANS_ROOT}/{clan_folder['name']}/{STAGING_FOLDER}"
            for entry in await list_all(staging):
                created_at = _parse_storage_timestamp(entry.get("created_at"))
                if entry.get("id") is None or created_at is None:
                    continue  # a sub-folder, or an entry Storage gave no time for
                if created_at < cutoff:
                    stale.append(f"{staging}/{entry['name']}")
        return stale

    async def delete(self, storage_path: str) -> bool:
        # Contract (StoragePort.delete): True on success OR confirmed
        # not-found; raise the classified StorageError for anything else. The
        # retention purge job (app.services.document_purge) claims a document's
        # row before calling this and only commits the claim once this
        # returns — so "not found" and "we don't know" must never be conflated
        # (the latter has to raise, or a row could be purged while its blob
        # deletion is genuinely unconfirmed). A missing BUCKET is "we don't
        # know": it raises StorageBucketNotConfiguredError, never returns True.
        client = get_service_client()
        try:
            await asyncio.to_thread(
                client.storage.from_(settings.SUPABASE_STORAGE_BUCKET).remove, [storage_path]
            )
        except Exception as e:
            classified = _classify_bucket(e, settings.SUPABASE_STORAGE_BUCKET)
            if isinstance(classified, StorageNotFoundError):
                return True
            raise classified from e
        return True

    async def get_presigned_url(
        self, storage_path: str, expires_in: int = DEFAULT_PRESIGN_TTL
    ) -> str:
        client = get_service_client()
        try:
            result = await asyncio.to_thread(
                client.storage.from_(settings.SUPABASE_STORAGE_BUCKET).create_signed_url,
                storage_path,
                expires_in,
            )
        except Exception as e:
            raise _classify_bucket(e, settings.SUPABASE_STORAGE_BUCKET) from e
        signed_url = result["signedURL"]
        if not signed_url:
            # storage3 2.31 types signedURL as str | None. A success response with
            # no URL is a provider fault, not a code bug — same class as a 5xx, so
            # it 503s instead of handing None to the caller as if it were a URL.
            raise StorageUnavailableError(f"storage returned no signed URL for {storage_path!r}")
        return signed_url

    async def get_presigned_urls(
        self, storage_paths: Sequence[str], expires_in: int = DEFAULT_PRESIGN_TTL
    ) -> dict[str, str]:
        paths = list(storage_paths)
        if not paths:
            return {}  # a clan with no documents never needed a Storage client
        bucket = settings.SUPABASE_STORAGE_BUCKET
        files_api = get_service_client().storage.from_(bucket)
        signed: dict[str, str] = {}
        for start in range(0, len(paths), _SIGN_BATCH_SIZE):
            chunk = paths[start : start + _SIGN_BATCH_SIZE]
            try:
                items = await asyncio.to_thread(files_api.create_signed_urls, chunk, expires_in)
            except Exception as e:
                raise _classify_bucket(e, bucket) from e
            for item in items:
                if item["error"]:
                    # Storage sets an item's error only when its object lookup found no
                    # row, the case the single sign answers with a 404 `not_found`
                    # (storage-api v1.77.5, `signObjectUrls`, read 2026-10-11).
                    raise StorageNotFoundError(f"{item['path']!r}: {item['error']}")
                if item["signedURL"]:
                    signed[item["path"]] = item["signedURL"]
        for path in paths:
            if path not in signed:
                # As in get_presigned_url: a success with no URL is a provider fault.
                raise StorageUnavailableError(f"storage returned no signed URL for {path!r}")
        return signed

    async def publish_public(
        self, *, source_path: str, destination_path: str, content_type: str | None
    ) -> str:
        """Copy a private object into the public avatars bucket; return its permanent URL.

        Download-then-upload rather than a server-side copy: storage3's ``copy`` is
        same-bucket in the versions we pin, and avatars are small. ``upsert`` is on so
        the per-person destination path is stable across avatar changes.

        The bucket is verified *before* the copy — existence AND ``public`` — because
        the whole point of this write path is that the URL we hand back must resolve
        for an anonymous reader. Uploading into a private bucket would "succeed" and
        leave a permanently broken avatar in the database.
        """
        bucket = settings.SUPABASE_AVATAR_BUCKET.strip()
        if not bucket:
            raise StorageBucketNotConfiguredError("SUPABASE_AVATAR_BUCKET is empty")
        if not settings.SUPABASE_URL.strip():
            raise StorageBucketNotConfiguredError(
                "SUPABASE_URL is empty — cannot build a public object URL"
            )

        client = get_service_client()
        try:
            info = await asyncio.to_thread(client.storage.get_bucket, bucket)
        except Exception as e:
            raise _classify_bucket(e, bucket) from e
        if not getattr(info, "public", False):
            raise StorageBucketNotConfiguredError(
                f"bucket {bucket!r} exists but is not public-read; "
                "an avatar published there would never resolve"
            )

        try:
            content = await asyncio.to_thread(
                client.storage.from_(settings.SUPABASE_STORAGE_BUCKET).download, source_path
            )
        except Exception as e:
            raise _classify_bucket(e, settings.SUPABASE_STORAGE_BUCKET) from e

        try:
            await asyncio.to_thread(
                client.storage.from_(bucket).upload,
                path=destination_path,
                file=content,
                file_options={
                    "content-type": content_type or "application/octet-stream",
                    "cache-control": f"max-age={settings.AVATAR_CACHE_CONTROL_SECONDS}",
                    "upsert": "true",
                },
            )
        except Exception as e:
            raise _classify_bucket(e, bucket) from e

        return _public_object_url(bucket, destination_path)
