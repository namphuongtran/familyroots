"""Track-B B2: document routes surface storage failures as clean 503/404 envelopes.

The storage classifier (_classify_storage) and the handler envelopes are unit-tested in
isolation, but nothing drove a REAL route and asserted the mapping end-to-end — so a
regression that unwraps a storage call site (letting a raw httpx/KeyError escape) would
silently become a 500 with nothing catching it. This drives GET /documents/{id},
POST /documents/uploads (sign) and POST /documents (confirm) through create_app()
(which registers the storage handlers) with a storage-backed handler that raises,
and asserts the 503 storage_unavailable / 503 storage_bucket_not_configured /
404 storage_not_found envelopes — with no raw storage detail leaked.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi.testclient import TestClient

from app.core.permissions import ClanRole, RequireEditor, RequireViewer
from app.core.security import get_current_clan_id, get_current_user
from app.domain.document.repository import (
    StorageBucketNotConfiguredError,
    StorageNotFoundError,
    StorageUnavailableError,
)
from app.infrastructure.dependencies import (
    get_document_query_handler,
    get_document_upload_handler,
)
from app.main import create_app
from app.services.translator import load_translations


class _FailingUploadHandler:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def sign(self, **_: Any) -> Any:
        raise self._exc

    async def confirm(self, **_: Any) -> Any:
        raise self._exc


class _FailingQueryHandler:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def get(self, **_: Any) -> Any:
        raise self._exc


def _client(
    *, upload_exc: Exception | None = None, query_exc: Exception | None = None
) -> TestClient:
    load_translations()
    app = create_app()
    # Bypass auth + RBAC (a DB lookup); the point under test is storage-error mapping.
    app.dependency_overrides[get_current_user] = lambda: {"sub": str(uuid.uuid4())}
    app.dependency_overrides[get_current_clan_id] = lambda: uuid.uuid4()
    app.dependency_overrides[RequireViewer.dependency] = lambda: ClanRole.VIEWER
    app.dependency_overrides[RequireEditor.dependency] = lambda: ClanRole.EDITOR
    if upload_exc is not None:
        app.dependency_overrides[get_document_upload_handler] = lambda: _FailingUploadHandler(
            upload_exc
        )
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


_SIGN_BODY = {"filename": "photo.jpg", "content_type": "image/jpeg", "size_bytes": 10}


def _confirm_body() -> dict[str, str]:
    return {
        "storage_path": f"clans/{uuid.uuid4()}/uploads/{uuid.uuid4()}.jpg",
        "title": "Family photo",
        "document_type": "photo",
    }


def test_sign_storage_outage_is_503() -> None:
    client = _client(upload_exc=StorageUnavailableError("sign failed: bucket unreachable"))
    resp = client.post("/api/v1/documents/uploads", json=_SIGN_BODY)
    assert resp.status_code == 503, resp.text
    assert resp.json()["error"]["code"] == "storage_unavailable"
    assert "bucket unreachable" not in resp.text


def test_confirm_storage_outage_is_503() -> None:
    client = _client(upload_exc=StorageUnavailableError("move failed: bucket unreachable"))
    resp = client.post("/api/v1/documents", json=_confirm_body())
    assert resp.status_code == 503, resp.text
    assert resp.json()["error"]["code"] == "storage_unavailable"
    assert "bucket unreachable" not in resp.text


def test_get_document_missing_bucket_is_503_not_404() -> None:
    """A missing private bucket used to reach the client as 404 storage_not_found,
    telling it the document was gone (#177). It is the server's configuration."""
    client = _client(
        query_exc=StorageBucketNotConfiguredError("bucket 'family-roots-files' does not exist")
    )
    resp = client.get(f"/api/v1/documents/{uuid.uuid4()}")
    assert resp.status_code == 503, resp.text
    assert resp.json()["error"]["code"] == "storage_bucket_not_configured"
    assert "family-roots-files" not in resp.text


def test_confirm_missing_bucket_is_503_not_404() -> None:
    client = _client(
        upload_exc=StorageBucketNotConfiguredError("bucket 'family-roots-files' does not exist")
    )
    resp = client.post("/api/v1/documents", json=_confirm_body())
    assert resp.status_code == 503, resp.text
    assert resp.json()["error"]["code"] == "storage_bucket_not_configured"
    assert "family-roots-files" not in resp.text
