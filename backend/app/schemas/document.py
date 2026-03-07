"""Pydantic v2 schemas for Document requests and responses."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
    "application/pdf",
    "audio/mpeg",
    "audio/wav",
    "video/mp4",
    "video/quicktime",
}

MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB


class DocumentUploadMeta(BaseModel):
    """Metadata fields sent alongside the file upload (form fields)."""

    member_id: uuid.UUID | None = None
    title: str = Field(..., min_length=1, max_length=255)
    document_type: str = Field(..., pattern="^(photo|id_document|certificate|audio|video|other)$")
    description: str | None = None
    taken_date: date | None = None
    taken_place: str | None = Field(None, max_length=255)


class DocumentResponse(BaseModel):
    id: uuid.UUID
    clan_id: uuid.UUID
    member_id: uuid.UUID | None = None
    title: str
    document_type: str
    description: str | None = None
    storage_path: str
    presigned_url: str | None = None
    presigned_url_expires_at: datetime | None = None
    file_size_bytes: int | None = None
    mime_type: str | None = None
    original_filename: str | None = None
    taken_date: date | None = None
    taken_place: str | None = None
    is_avatar: bool = False
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentSummary(BaseModel):
    id: uuid.UUID
    title: str
    document_type: str
    mime_type: str | None = None
    file_size_bytes: int | None = None
    is_avatar: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}
