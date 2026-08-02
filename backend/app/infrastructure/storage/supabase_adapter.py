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
from collections.abc import Mapping
from urllib.parse import quote

from storage3.exceptions import StorageApiError

from app.core.config import settings
from app.domain.document.repository import (
    DEFAULT_PRESIGN_TTL,
    StorageBucketNotConfiguredError,
    StorageError,
    StorageNotFoundError,
    StorageUnavailableError,
)
from app.infrastructure.supabase_client import get_service_client

logger = logging.getLogger(__name__)


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
    gap. The public avatars bucket has to be created by hand (ADR-036), so this is
    the misconfiguration we most expect to hit and it gets its own code.
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
    """Concrete storage adapter backed by Supabase Storage."""

    async def upload(self, path: str, content: bytes, content_type: str | None) -> str:
        client = get_service_client()
        try:
            await asyncio.to_thread(
                client.storage.from_(settings.SUPABASE_STORAGE_BUCKET).upload,
                path=path,
                file=content,
                file_options={
                    "content-type": content_type or "application/octet-stream",
                    "upsert": "false",
                },
            )
        except Exception as e:
            raise _classify_storage(e) from e
        return path

    async def delete(self, storage_path: str) -> bool:
        # Contract (StoragePort.delete): True on success OR confirmed
        # not-found; raise the classified StorageError for anything else. The
        # retention purge job (app.services.document_purge) claims a document's
        # row before calling this and only commits the claim once this
        # returns — so "not found" and "we don't know" must never be conflated
        # (the latter has to raise, or a row could be purged while its blob
        # deletion is genuinely unconfirmed).
        client = get_service_client()
        try:
            await asyncio.to_thread(
                client.storage.from_(settings.SUPABASE_STORAGE_BUCKET).remove, [storage_path]
            )
        except Exception as e:
            classified = _classify_storage(e)
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
            raise _classify_storage(e) from e
        signed_url = result["signedURL"]
        if not signed_url:
            # storage3 2.31 types signedURL as str | None. A success response with
            # no URL is a provider fault, not a code bug — same class as a 5xx, so
            # it 503s instead of handing None to the caller as if it were a URL.
            raise StorageUnavailableError(f"storage returned no signed URL for {storage_path!r}")
        return signed_url

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
            raise _classify_storage(e) from e

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
