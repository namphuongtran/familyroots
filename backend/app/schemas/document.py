"""Pydantic v2 schemas for Document requests and responses."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


class SignUploadRequest(BaseModel):
    """``POST /documents/uploads``: what the client says it is about to upload.

    These are declarations, checked before any byte is sent. The confirm call checks
    what Storage actually received (ADR-068).
    """

    filename: str = Field(..., min_length=1, max_length=255)
    content_type: str = Field(..., min_length=1, max_length=100)
    size_bytes: int = Field(..., ge=0)


class SignedUploadResponse(BaseModel):
    """Where to send the bytes. ``storage_path`` goes back in the confirm call."""

    storage_path: str
    upload_url: str
    token: str
    expires_at: datetime


class DocumentCreateRequest(BaseModel):
    """``POST /documents``: confirm a staged upload as a document of this clan."""

    storage_path: str = Field(..., min_length=1, max_length=500)
    title: str = Field(..., min_length=1, max_length=255)
    document_type: str = Field(..., pattern="^(photo|id_document|certificate|audio|video|other)$")
    original_filename: str | None = Field(None, max_length=255)
    person_id: uuid.UUID | None = None
    description: str | None = None
    taken_date: date | None = None
    taken_place: str | None = Field(None, max_length=255)


class DocumentResponse(BaseModel):
    id: uuid.UUID
    clan_id: uuid.UUID
    person_id: uuid.UUID | None = None
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
