"""M7 — the document upload route must cap how much it reads into memory.

Before the fix the route did ``await file.read()`` (whole spooled body copied into one
`bytes`), so a huge upload copied the entire file into RAM before the size check. The
route now reads at most ``MAX_FILE_SIZE_BYTES + 1``. These tests drive the actual route
function (with a fake handler that records what it received), so a revert to an
unbounded ``read()`` fails them. A small cap is monkeypatched in so the test is cheap.
"""

import io
import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import UploadFile

import app.api.v1.documents as documents_route
from app.core.permissions import ClanRole

pytestmark = [pytest.mark.unit]


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
    monkeypatch.setattr(documents_route, "MAX_FILE_SIZE_BYTES", 10)
    handler = _RecordingHandler()

    await _call_route(handler, b"x" * 50)  # far over the (patched) 10-byte limit

    # The route read only MAX+1 = 11 bytes, NOT the full 50 — this is the memory bound.
    # A revert to `await file.read()` would make this 50 and fail the assertion.
    assert handler.received_len == 11


@pytest.mark.asyncio
async def test_route_reads_normal_file_in_full(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(documents_route, "MAX_FILE_SIZE_BYTES", 10)
    handler = _RecordingHandler()

    await _call_route(handler, b"xyz")  # within the limit

    assert handler.received_len == 3
