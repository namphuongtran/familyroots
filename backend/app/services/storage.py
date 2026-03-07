"""Supabase Storage upload/delete service."""

import logging

from supabase import Client, create_client

from app.core.config import settings

logger = logging.getLogger(__name__)


def get_storage_client() -> Client:
    """Return a Supabase client using the service role key (bypasses RLS)."""
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


async def upload_file(path: str, content: bytes, content_type: str) -> str:
    """Upload a file to Supabase Storage. Returns the storage path."""
    client = get_storage_client()
    client.storage.from_(settings.SUPABASE_STORAGE_BUCKET).upload(
        path=path,
        file=content,
        file_options={"content-type": content_type, "upsert": "false"},
    )
    return path


async def delete_file(storage_path: str) -> bool:
    """Delete a file from Supabase Storage. Returns True on success."""
    try:
        client = get_storage_client()
        client.storage.from_(settings.SUPABASE_STORAGE_BUCKET).remove([storage_path])
        return True
    except Exception as e:
        logger.error("Storage delete failed: %s (path=%s)", e, storage_path)
        return False


async def get_presigned_url(storage_path: str, expires_in: int = 3600) -> str:
    """Generate a time-limited presigned URL. Never expose raw storage paths."""
    client = get_storage_client()
    result = client.storage.from_(settings.SUPABASE_STORAGE_BUCKET).create_signed_url(
        storage_path, expires_in
    )
    return result["signedURL"]
