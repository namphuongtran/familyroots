"""M7 — the document upload route must cap how much it reads into memory.

Before the fix the route did ``await file.read()`` (whole spooled body copied into one
`bytes`), so a huge upload copied the entire file into RAM before the size check. The
route now reads at most ``settings.max_upload_bytes + 1``. These tests drive the actual
route function (with a fake handler that records what it received), so a revert to an
unbounded ``read()`` fails them. A small limit is monkeypatched in so the test is cheap.
"""

import io
import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import UploadFile

import app.api.v1.documents as documents_route
from app.core.config import settings
from app.core.permissions import ClanRole

pytestmark = [pytest.mark.unit]

_MB = 1024 * 1024


class _RecordingHandler:
    """Captures the byte length the route actually read and passed on."""

    def __init__(self) -> None:
        self.received_len: int | None = None

    async def upload(self, *, file_content: bytes, **_: Any) -> SimpleNamespace:
        self.received_len = len(file_content)
        return SimpleNamespace(model_dump=lambda: {})


async def _call_route(handler: _RecordingHandler, body: bytes) -> None:
    upload = UploadFile(io.BytesIO(body), filename="f.jpg")
    await documents_route.upload_document(
        file=upload,
        title="t",
        document_type="photo",
        person_id=None,
        description=None,
        taken_date=None,
        taken_place=None,
        current_user={"sub": str(uuid.uuid4())},
        clan_id=uuid.uuid4(),
        cmd_handler=handler,  # type: ignore[arg-type]
        role=ClanRole.EDITOR,  # the route now records the caller's resolved role in the audit actor
    )


@pytest.mark.asyncio
async def test_route_caps_read_for_oversized_body(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_MB", 1)  # 1 MB cap
    handler = _RecordingHandler()

    await _call_route(handler, b"x" * (2 * _MB))  # far over the 1 MB limit

    # The route read only max_upload_bytes + 1, NOT the full 2 MB — the memory bound.
    # A revert to `await file.read()` would make this 2 MB and fail the assertion.
    assert handler.received_len == _MB + 1


@pytest.mark.asyncio
async def test_route_reads_normal_file_in_full(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_MB", 1)
    handler = _RecordingHandler()

    await _call_route(handler, b"xyz")  # within the limit

    assert handler.received_len == 3
