"""M7 — the document upload must not read an unbounded body into memory.

Before the fix the route did ``await file.read()`` (entire body into RAM) and only
checked the size afterwards, so a multi-GB upload could exhaust memory. The route now
reads at most ``MAX_FILE_SIZE_BYTES + 1``; anything over the limit is still rejected by
the domain's file_too_large validation.
"""

import io
import uuid

import pytest
from starlette.datastructures import UploadFile

from app.domain.document.entity import MAX_FILE_SIZE_BYTES, Document
from app.domain.shared.exceptions import ValidationError
from app.domain.shared.value_objects import ActorInfo

pytestmark = [pytest.mark.unit]


@pytest.mark.asyncio
async def test_read_is_capped_and_oversized_is_rejected() -> None:
    # A body well over the limit.
    oversized = b"x" * (MAX_FILE_SIZE_BYTES + 4096)
    upload = UploadFile(filename="huge.jpg", file=io.BytesIO(oversized))

    # The route reads with this exact cap — memory is bounded to MAX+1, NOT the full
    # (potentially unbounded) upload size.
    content = await upload.read(MAX_FILE_SIZE_BYTES + 1)
    assert len(content) == MAX_FILE_SIZE_BYTES + 1
    assert len(content) < len(oversized)

    # The capped content still trips the domain size check → file_too_large.
    with pytest.raises(ValidationError, match="file_too_large"):
        Document.create(
            clan_id=uuid.uuid4(),
            actor=ActorInfo.from_jwt({"sub": str(uuid.uuid4())}, "editor"),
            title="t",
            document_type="photo",
            storage_path="clans/x/documents/y.jpg",
            mime_type="image/jpeg",
            file_size_bytes=len(content),
        )


@pytest.mark.asyncio
async def test_within_limit_upload_reads_fully() -> None:
    body = b"y" * 1024
    upload = UploadFile(filename="ok.jpg", file=io.BytesIO(body))
    content = await upload.read(MAX_FILE_SIZE_BYTES + 1)
    assert content == body  # a normal file is read in full and accepted downstream
