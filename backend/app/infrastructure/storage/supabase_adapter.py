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

from storage3.exceptions import StorageApiError

from app.core.config import settings
from app.domain.document.repository import (
    DEFAULT_PRESIGN_TTL,
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
