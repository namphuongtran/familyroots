"""Track-B B2: document routes surface storage failures as clean 503/404 envelopes.

The storage classifier (_classify_storage) and the handler envelopes are unit-tested in
isolation, but nothing drove a REAL route and asserted the mapping end-to-end — so a
regression that unwraps a storage call site (letting a raw httpx/KeyError escape) would
silently become a 500 with nothing catching it. This drives GET /documents/{id} and
POST /documents through create_app() (which registers the storage handlers) with a
StoragePort-backed handler that raises, and asserts the 503 storage_unavailable /
404 storage_not_found envelopes — with no raw storage detail leaked.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi.testclient import TestClient

from app.core.permissions import ClanRole, RequireEditor, RequireViewer
from app.core.security import get_current_clan_id, get_current_user
from app.domain.document.repository import StorageNotFoundError, StorageUnavailableError
from app.infrastructure.dependencies import (
    get_document_command_handler,
    get_document_query_handler,
)
from app.main import create_app
from app.services.translator import load_translations


class _FailingCmdHandler:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def upload(self, **_: Any) -> Any:
        raise self._exc


class _FailingQueryHandler:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def get(self, **_: Any) -> Any:
        raise self._exc


def _client(*, cmd_exc: Exception | None = None, query_exc: Exception | None = None) -> TestClient:
    load_translations()
    app = create_app()
    # Bypass auth + RBAC (a DB lookup); the point under test is storage-error mapping.
    app.dependency_overrides[get_current_user] = lambda: {"sub": str(uuid.uuid4())}
    app.dependency_overrides[get_current_clan_id] = lambda: uuid.uuid4()
    app.dependency_overrides[RequireViewer.dependency] = lambda: ClanRole.VIEWER
    app.dependency_overrides[RequireEditor.dependency] = lambda: ClanRole.EDITOR
    if cmd_exc is not None:
        app.dependency_overrides[get_document_command_handler] = lambda: _FailingCmdHandler(cmd_exc)
    if query_exc is not None:
        app.dependency_overrides[get_document_query_handler] = lambda: _FailingQueryHandler(
            query_exc
        )
    return TestClient(app, raise_server_exceptions=False)


def test_get_document_storage_outage_is_503() -> None:
    client = _client(query_exc=StorageUnavailableError("presign failed: backend down"))
    resp = client.get(f"/api/v1/documents/{uuid.uuid4()}")
    assert resp.status_code == 503, resp.text
    assert resp.json()["error"]["code"] == "storage_unavailable"
    assert "backend down" not in resp.text  # raw storage detail must not leak


def test_get_document_missing_object_is_404() -> None:
    client = _client(query_exc=StorageNotFoundError("no such object: clans/x/y.jpg"))
    resp = client.get(f"/api/v1/documents/{uuid.uuid4()}")
    assert resp.status_code == 404, resp.text
    assert resp.json()["error"]["code"] == "storage_not_found"
    assert "no such object" not in resp.text


def test_upload_storage_outage_is_503() -> None:
    client = _client(cmd_exc=StorageUnavailableError("upload failed: bucket unreachable"))
    resp = client.post(
        "/api/v1/documents",
        files={"file": ("photo.jpg", b"binarydata", "image/jpeg")},
        data={"title": "Family photo", "document_type": "photo"},
    )
    assert resp.status_code == 503, resp.text
    assert resp.json()["error"]["code"] == "storage_unavailable"
    assert "bucket unreachable" not in resp.text
