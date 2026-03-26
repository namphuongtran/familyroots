"""Supabase implementation of the StoragePort protocol.

Keeps the application/domain layers free of Supabase SDK imports.
"""

from __future__ import annotations

import logging

from app.core.config import settings
from app.infrastructure.supabase_client import get_service_client

logger = logging.getLogger(__name__)


class SupabaseStorageAdapter:
    """Concrete storage adapter backed by Supabase Storage."""

    async def upload(self, path: str, content: bytes, content_type: str | None) -> str:
        client = get_service_client()
        client.storage.from_(settings.SUPABASE_STORAGE_BUCKET).upload(
            path=path,
            file=content,
            file_options={
                "content-type": content_type or "application/octet-stream",
                "upsert": "false",
            },
        )
        return path

    async def delete(self, storage_path: str) -> bool:
        try:
            client = get_service_client()
            client.storage.from_(settings.SUPABASE_STORAGE_BUCKET).remove([storage_path])
            return True
        except Exception as e:
            logger.error("Storage delete failed: %s (path=%s)", e, storage_path)
            return False

    async def get_presigned_url(self, storage_path: str, expires_in: int = 3600) -> str:
        client = get_service_client()
        result = client.storage.from_(settings.SUPABASE_STORAGE_BUCKET).create_signed_url(
            storage_path, expires_in
        )
        return result["signedURL"]
