# Storage Taxonomy + Off-load (PR-I) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the storage layer non-blocking and truthful — off-load the blocking Supabase SDK calls, and classify storage failures into 503 (unavailable) / 404 (not found) instead of opaque 500s — plus fix the presign expiry, reorder `set_avatar`, and delete the dead `services/storage.py`.

**Architecture:** Mirror the identity provider's error taxonomy. Add framework-free `StorageError` subclasses next to `StoragePort` (domain), classify SDK/transport failures in the adapter (`_classify_storage`) while wrapping every blocking SDK call in `asyncio.to_thread`, and register 503/404 exception handlers paralleling `identity_unavailable_handler`.

**Tech Stack:** FastAPI, SQLAlchemy 2 async/psycopg, PostgreSQL, `supabase`/`storage3` SDK, pytest(-asyncio) against dockerized Postgres, `asyncio.to_thread`.

## Global Constraints

- Domain layer stays framework-free (no SQLAlchemy/FastAPI/SDK imports in `app/domain/**`) — enforced by import-linter.
- Error envelope is the stable `{"error": {"code", "message", "detail"}}` shape; add new i18n codes to ALL FOUR locales (vi/en/zh/fr).
- Off-load mechanism is `asyncio.to_thread` (owner decision) — do NOT migrate to the async Supabase client.
- Taxonomy mirrors identity: `StorageUnavailableError` → 503 `storage_unavailable`; `StorageNotFoundError` → 404 `storage_not_found`; a genuinely unexpected error stays a loud 500 (never silently downgraded).
- `delete()` on the port stays a best-effort `bool` (it runs post-commit as compensation and must never raise a 503 for an already-committed delete). Only `upload` and `get_presigned_url` classify+raise.
- Branch `fix/storage-taxonomy-offload` (already checked out). Do NOT `git add -A` — stage only named files. Run `./scripts/check.sh` before each commit. Commands run from `backend/`.

---

### Task 1: Domain storage errors + presign TTL constant

**Files:**
- Modify: `app/domain/document/repository.py` (add error hierarchy + `DEFAULT_PRESIGN_TTL` above `class StoragePort`; use the constant as `get_presigned_url`'s default)
- Test: `tests/unit/domain/test_storage_errors.py` (new)

**Interfaces:**
- Produces: `DEFAULT_PRESIGN_TTL: int = 3600`; `StorageError(Exception)`; `StorageUnavailableError(StorageError)`; `StorageNotFoundError(StorageError)` — all importable from `app.domain.document.repository`.

- [ ] **Step 1: Write the failing test** — create `tests/unit/domain/test_storage_errors.py`:

```python
"""The storage error hierarchy mirrors the identity provider's taxonomy."""

from app.domain.document.repository import (
    DEFAULT_PRESIGN_TTL,
    StorageError,
    StorageNotFoundError,
    StorageUnavailableError,
)


def test_storage_error_hierarchy() -> None:
    assert issubclass(StorageUnavailableError, StorageError)
    assert issubclass(StorageNotFoundError, StorageError)
    assert StorageError is not StorageUnavailableError


def test_default_presign_ttl() -> None:
    assert DEFAULT_PRESIGN_TTL == 3600
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/unit/domain/test_storage_errors.py -v`
Expected: FAIL — `ImportError: cannot import name 'StorageError' from 'app.domain.document.repository'`.

- [ ] **Step 3: Add the errors + constant** — in `app/domain/document/repository.py`, insert immediately ABOVE `class StoragePort(Protocol):`:

```python
DEFAULT_PRESIGN_TTL = 3600  # seconds — default presigned-URL lifetime


class StorageError(Exception):
    """Base class for storage-adapter failures (provider-agnostic)."""


class StorageUnavailableError(StorageError):
    """Storage backend unreachable or misconfigured — surfaced as HTTP 503.

    Covers provider 5xx, transport failures (DNS/connection/TLS/timeout), and a
    rejected API key (our configuration). Never conflate an outage with a code
    bug (500) or with a missing object (404)."""


class StorageNotFoundError(StorageError):
    """The requested storage object does not exist — surfaced as HTTP 404."""
```

Then change the `get_presigned_url` signature default in `StoragePort` from `expires_in: int = 3600` to `expires_in: int = DEFAULT_PRESIGN_TTL`.

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/unit/domain/test_storage_errors.py -v`
Expected: PASS (2 tests). Also `uv run lint-imports` still 5/5 (domain stays framework-free — these are plain `Exception` subclasses).

- [ ] **Step 5: Commit**

```bash
git add app/domain/document/repository.py tests/unit/domain/test_storage_errors.py
git commit -m "feat(backend): domain storage error taxonomy + presign TTL constant (PR-I)"
```

---

### Task 2: Adapter — off-load + classify

**Files:**
- Modify: `app/infrastructure/storage/supabase_adapter.py` (add `_classify_storage`; wrap all 3 SDK calls in `asyncio.to_thread`; classify+raise on `upload`/`get_presigned_url`; keep `delete` best-effort bool)
- Test: `tests/unit/infrastructure/test_storage_error_classification.py` (new)

**Interfaces:**
- Consumes: `DEFAULT_PRESIGN_TTL`, `StorageError`, `StorageUnavailableError`, `StorageNotFoundError` from Task 1; `storage3.exceptions.StorageApiError` (ctor `StorageApiError(message, code, status)`, `.to_dict()` → `{'name','code','message','status'}`).
- Produces: `_classify_storage(exc: Exception) -> Exception` in the adapter module; the three port methods now off-loaded.

- [ ] **Step 1: Write the failing classification test** — create `tests/unit/infrastructure/test_storage_error_classification.py`:

```python
"""_classify_storage maps SDK/transport failures to the storage taxonomy.

Mirrors tests/unit/infrastructure/test_identity_error_classification.py: a
missing object → 404 type, anything infrastructural → 503 type, an unexpected
error → returned unchanged so it stays a loud 500.
"""

import pytest
from storage3.exceptions import StorageApiError

from app.domain.document.repository import StorageNotFoundError, StorageUnavailableError
from app.infrastructure.storage.supabase_adapter import _classify_storage


@pytest.mark.parametrize(
    "exc, expected_type",
    [
        (StorageApiError("Object not found", "not_found", 404), StorageNotFoundError),
        (StorageApiError("boom", "internal_error", 500), StorageUnavailableError),
        (StorageApiError("bad key", "invalid_api_key", 401), StorageUnavailableError),
        (ConnectionError("dns failure"), StorageUnavailableError),
        (TimeoutError("timed out"), StorageUnavailableError),
    ],
)
def test_classify_maps_to_storage_error(exc: Exception, expected_type: type) -> None:
    assert isinstance(_classify_storage(exc), expected_type)


def test_classify_reraises_unexpected_4xx_unchanged() -> None:
    # A duplicate/400 is a genuine bug on our uuid+upsert=false paths — keep it loud.
    dup = StorageApiError("Duplicate", "duplicate", 409)
    assert _classify_storage(dup) is dup
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/unit/infrastructure/test_storage_error_classification.py -v`
Expected: FAIL — `ImportError: cannot import name '_classify_storage'`.

- [ ] **Step 3: Rewrite the adapter** — replace the whole body of `app/infrastructure/storage/supabase_adapter.py` with:

```python
"""Supabase implementation of the StoragePort protocol.

Keeps the application/domain layers free of Supabase SDK imports. The blocking
storage3 SDK is synchronous, so every call is off-loaded with asyncio.to_thread
to avoid freezing the event loop; failures are classified into the domain
StorageError taxonomy (mirroring the identity provider).
"""

from __future__ import annotations

import asyncio
import logging

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
        info: dict[str, object] = {}
        try:
            info = exc.to_dict()
        except Exception:  # noqa: BLE001 - defensive: never let classification raise
            pass
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
        # Best-effort: called post-commit as compensation, so it must never raise
        # (a 503 here would be for an already-committed DB delete). Swallow + log.
        try:
            client = get_service_client()
            await asyncio.to_thread(
                client.storage.from_(settings.SUPABASE_STORAGE_BUCKET).remove, [storage_path]
            )
            return True
        except Exception as e:  # noqa: BLE001 - best-effort compensation
            logger.error("Storage delete failed: %s (path=%s)", e, storage_path)
            return False

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
        return result["signedURL"]
```

- [ ] **Step 4: Add an adapter-level raise test** — append to `tests/unit/infrastructure/test_storage_error_classification.py`:

```python
from unittest.mock import MagicMock

import pytest


@pytest.mark.asyncio
async def test_get_presigned_url_raises_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.infrastructure.storage import supabase_adapter as mod

    bucket = MagicMock()
    bucket.create_signed_url.side_effect = StorageApiError("Object not found", "not_found", 404)
    client = MagicMock()
    client.storage.from_.return_value = bucket
    monkeypatch.setattr(mod, "get_service_client", lambda: client)

    with pytest.raises(StorageNotFoundError):
        await mod.SupabaseStorageAdapter().get_presigned_url("clans/x/documents/y.jpg")


@pytest.mark.asyncio
async def test_upload_raises_unavailable_on_5xx(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.infrastructure.storage import supabase_adapter as mod

    bucket = MagicMock()
    bucket.upload.side_effect = StorageApiError("boom", "internal_error", 500)
    client = MagicMock()
    client.storage.from_.return_value = bucket
    monkeypatch.setattr(mod, "get_service_client", lambda: client)

    with pytest.raises(StorageUnavailableError):
        await mod.SupabaseStorageAdapter().upload("p", b"data", "image/jpeg")
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/infrastructure/test_storage_error_classification.py -v`
Expected: PASS (7). `MagicMock` is safe for `asyncio.to_thread` (it calls the sync callable in a thread).

- [ ] **Step 6: Commit**

```bash
git add app/infrastructure/storage/supabase_adapter.py tests/unit/infrastructure/test_storage_error_classification.py
git commit -m "feat(backend): off-load storage SDK via to_thread + classify errors (PR-I)"
```

---

### Task 3: HTTP handlers + i18n + registration

**Files:**
- Modify: `app/core/exceptions.py` (add `storage_unavailable_handler`, `storage_not_found_handler`)
- Modify: `app/main.py` (import + register both)
- Modify: `app/i18n/vi.json`, `app/i18n/en.json`, `app/i18n/zh.json`, `app/i18n/fr.json` (add `error.storage_unavailable`, `error.storage_not_found`)
- Test: `tests/unit/test_storage_error_handlers.py` (new)

**Interfaces:**
- Consumes: `StorageUnavailableError`, `StorageNotFoundError` from Task 1.
- Produces: two ASGI exception handlers returning the standard envelope with codes `storage_unavailable` (503) / `storage_not_found` (404).

- [ ] **Step 1: Write the failing test** — create `tests/unit/test_storage_error_handlers.py`:

```python
"""Storage errors map to 503/404 envelopes, and the handlers are registered."""

import json

import pytest
from starlette.requests import Request

from app.core.exceptions import storage_not_found_handler, storage_unavailable_handler
from app.domain.document.repository import StorageNotFoundError, StorageUnavailableError
from app.main import create_app
from app.services.translator import load_translations


def _req() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/x", "headers": []})


@pytest.mark.asyncio
async def test_unavailable_handler_returns_503_envelope() -> None:
    load_translations()
    resp = await storage_unavailable_handler(_req(), StorageUnavailableError("down"))
    assert resp.status_code == 503
    body = json.loads(resp.body)
    assert body["error"]["code"] == "storage_unavailable"
    assert body["error"]["message"] and body["error"]["message"] != "error.storage_unavailable"


@pytest.mark.asyncio
async def test_not_found_handler_returns_404_envelope() -> None:
    load_translations()
    resp = await storage_not_found_handler(_req(), StorageNotFoundError("missing"))
    assert resp.status_code == 404
    body = json.loads(resp.body)
    assert body["error"]["code"] == "storage_not_found"
    assert body["error"]["message"] and body["error"]["message"] != "error.storage_not_found"


def test_handlers_are_registered() -> None:
    app = create_app()
    assert StorageUnavailableError in app.exception_handlers
    assert StorageNotFoundError in app.exception_handlers
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/unit/test_storage_error_handlers.py -v`
Expected: FAIL — `ImportError: cannot import name 'storage_unavailable_handler'`.

- [ ] **Step 3: Add the handlers** — in `app/core/exceptions.py`, add after `identity_unavailable_handler` (mirror its shape):

```python
async def storage_unavailable_handler(request: Request, exc: Exception) -> JSONResponse:
    """Surface storage-backend outages/misconfiguration as 503, in one place."""
    from app.services.translator import t

    logger.error("Storage unavailable on %s %s: %s", request.method, request.url.path, exc)
    code = "storage_unavailable"
    return JSONResponse(
        status_code=503,
        content={"error": {"code": code, "message": t(f"error.{code}"), "detail": {}}},
    )


async def storage_not_found_handler(request: Request, exc: Exception) -> JSONResponse:
    """A referenced storage object does not exist — surface as 404, not 500."""
    from app.services.translator import t

    code = "storage_not_found"
    return JSONResponse(
        status_code=404,
        content={"error": {"code": code, "message": t(f"error.{code}"), "detail": {}}},
    )
```

- [ ] **Step 4: Register them** — in `app/main.py`, add to the imports from `app.core.exceptions` (alongside `identity_unavailable_handler`): `storage_not_found_handler, storage_unavailable_handler`; add near the top-level imports: `from app.domain.document.repository import StorageNotFoundError, StorageUnavailableError`; and add beside the `identity_unavailable_handler` registration:

```python
    application.add_exception_handler(StorageUnavailableError, storage_unavailable_handler)
    application.add_exception_handler(StorageNotFoundError, storage_not_found_handler)
```

- [ ] **Step 5: Add i18n keys** — in each of `app/i18n/{vi,en,zh,fr}.json`, add next to the existing `error.*` keys:

```
vi: "error.storage_unavailable": "Kho lưu trữ tạm thời không khả dụng",  "error.storage_not_found": "Không tìm thấy tệp"
en: "error.storage_unavailable": "Storage is temporarily unavailable",   "error.storage_not_found": "File not found"
zh: "error.storage_unavailable": "存储暂时不可用",                          "error.storage_not_found": "未找到文件"
fr: "error.storage_unavailable": "Stockage temporairement indisponible",  "error.storage_not_found": "Fichier introuvable"
```

(Match each file's existing JSON formatting — the keys are flat, comma-separated.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_storage_error_handlers.py tests/unit/test_i18n_coverage.py -v`
Expected: PASS (the i18n-coverage guard stays green because the new keys exist in all four locales).

- [ ] **Step 7: Commit**

```bash
git add app/core/exceptions.py app/main.py app/i18n/vi.json app/i18n/en.json app/i18n/zh.json app/i18n/fr.json tests/unit/test_storage_error_handlers.py
git commit -m "feat(backend): 503/404 storage exception handlers + i18n (PR-I)"
```

---

### Task 4: Presign expiry + set_avatar reorder + remove dead module

**Files:**
- Modify: `app/application/document/handlers.py` (import `timedelta` + `DEFAULT_PRESIGN_TTL` + `StorageError`; fix expiry in `upload`; reorder `set_avatar`)
- Delete: `app/services/storage.py`
- Test: `tests/unit/application/test_document_handler_storage.py` (new)

**Interfaces:**
- Consumes: `DEFAULT_PRESIGN_TTL`, `StorageError` from Task 1; `StoragePort` (existing).

- [ ] **Step 1: Write the failing tests** — create `tests/unit/application/test_document_handler_storage.py`:

```python
"""upload sets a real future expiry; set_avatar tolerates a storage outage."""

from datetime import UTC, datetime
from typing import Any

import pytest

from app.application.document.handlers import DocumentCommandHandler
from app.domain.document.repository import DEFAULT_PRESIGN_TTL, StorageUnavailableError
from app.domain.shared.value_objects import ActorInfo


class _FakeStorage:
    def __init__(self, *, presign_raises: bool = False) -> None:
        self.presign_raises = presign_raises

    async def upload(self, path: str, content: bytes, content_type: str | None) -> str:
        return path

    async def delete(self, storage_path: str) -> bool:
        return True

    async def get_presigned_url(self, storage_path: str, expires_in: int = DEFAULT_PRESIGN_TTL) -> str:
        if self.presign_raises:
            raise StorageUnavailableError("down")
        return "https://signed.example/url"


class _FakeUoW:
    def __init__(self) -> None:
        self.commits = 0

    def track(self, agg: Any) -> None: ...
    async def flush(self) -> None: ...
    async def commit(self) -> None:
        self.commits += 1


@pytest.mark.asyncio
async def test_upload_expiry_is_now_plus_ttl(document_repo_fake: Any) -> None:
    handler = DocumentCommandHandler(document_repo_fake, _FakeStorage(), _FakeUoW())
    resp = await handler.upload(
        file_content=b"\xff\xd8\xff",  # minimal JPEG magic
        filename="a.jpg",
        content_type="image/jpeg",
        title="t",
        document_type="photo",
        clan_id=document_repo_fake.clan_id,
        actor=ActorInfo(user_id=document_repo_fake.actor_id, role="editor"),
    )
    # DocumentResponse.presigned_url_expires_at is typed `datetime | None`, so Pydantic
    # has already coerced the handler's isoformat string into a tz-aware datetime —
    # read it directly (do NOT call datetime.fromisoformat on it).
    delta = resp.presigned_url_expires_at - datetime.now(UTC)
    assert DEFAULT_PRESIGN_TTL - 60 <= delta.total_seconds() <= DEFAULT_PRESIGN_TTL + 60


@pytest.mark.asyncio
async def test_set_avatar_returns_none_when_presign_fails(document_repo_fake: Any) -> None:
    uow = _FakeUoW()
    handler = DocumentCommandHandler(
        document_repo_fake, _FakeStorage(presign_raises=True), uow
    )
    result = await handler.set_avatar(
        document_id=document_repo_fake.existing_photo_id,
        clan_id=document_repo_fake.clan_id,
        actor=ActorInfo(user_id=document_repo_fake.actor_id, role="editor"),
    )
    assert result is None
    assert uow.commits == 1  # the avatar change committed despite the presign outage
```

Note: `document_repo_fake` is a fixture the implementer must build (a minimal `DocumentRepository` double: `person_in_clan`→True, `save`/`delete` no-ops, `get_by_id`/`_get_or_raise` returns a photo `Document` with `is_avatar` settable, `get_person_avatars`→[]). Mirror any existing document-handler test doubles under `tests/unit/` if present; otherwise define the fixture in this file with the minimal surface the two tests touch (`person_in_clan`, `save`, `get_by_id`, `get_person_avatars`). The `Document` entity is real (`app.domain.document.entity.Document`); build one via `Document.create(...)` with a linked `person_id` and `document_type="photo"` so `set_avatar()` passes.

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/unit/application/test_document_handler_storage.py -v`
Expected: FAIL — `test_upload_expiry...` fails because `presigned_url_expires_at` is currently `datetime.now(UTC)` (delta ≈ 0, not ≈ 3600); `test_set_avatar...` fails because `set_avatar` currently calls presign BEFORE commit, so the raise aborts before `uow.commit` (commits == 0) and propagates instead of returning `None`.

- [ ] **Step 3a: Fix the upload expiry** — in `app/application/document/handlers.py`, update the imports to `from datetime import UTC, datetime, timedelta` and add `from app.domain.document.repository import DEFAULT_PRESIGN_TTL, DocumentRepository, StorageError, StoragePort` (merge with the existing repository import). Change the `upload` return's expiry line from:

```python
            presigned_url_expires_at=datetime.now(UTC).isoformat(),
```

to:

```python
            presigned_url_expires_at=(
                datetime.now(UTC) + timedelta(seconds=DEFAULT_PRESIGN_TTL)
            ).isoformat(),
```

- [ ] **Step 3b: Reorder set_avatar** — in `set_avatar`, move the presign to AFTER the commit and tolerate a storage outage. Replace the tail of the method (from the `presigned = ...` line through `return presigned`) with:

```python
        # Commit the avatar change (audit + doc + old-avatar clears) FIRST — a
        # pure-DB write must not be gated on a read-side storage call. Then fetch
        # the presigned URL best-effort; a storage outage returns None, not a 503.
        await emit_audit_event(
            self._uow,
            action="document.set_avatar",
            resource_type="document",
            resource_id=doc.id,
            actor=actor,
            clan_id=clan_id,
            new_value={"is_avatar": True, "person_id": str(doc.person_id)},
        )
        try:
            return await self._storage.get_presigned_url(doc.storage_path, expires_in=86400 * 30)
        except StorageError:
            logger.warning("Avatar set but presign failed for %s", doc.storage_path)
            return None
```

(Delete the old `presigned = await self._storage.get_presigned_url(...)` line that ran before `emit_audit_event`, and the old `return presigned`.)

- [ ] **Step 4: Delete the dead module** — confirm no importers, then remove it:

```bash
grep -rn "services.storage\|services/storage\|from app.services import storage" app/ tests/
git rm app/services/storage.py
```

Expected grep: no hits (0 importers). If any hit appears, STOP and report — do not delete.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/application/test_document_handler_storage.py -v`
Expected: PASS (2).

- [ ] **Step 6: Full gate**

Run: `./scripts/check.sh`
Expected: `Gate passed.` (ruff format+check, import-linter 5/5, mypy strict, full pytest against dockerized Postgres). Fix any ruff/mypy issues (e.g. unused imports) before committing.

- [ ] **Step 7: Commit**

```bash
git add app/application/document/handlers.py
git rm app/services/storage.py
git add tests/unit/application/test_document_handler_storage.py
git commit -m "fix(backend): presign expiry + set_avatar ordering; drop dead services/storage.py (PR-I)"
```

---

## Self-review notes (author)

- **Spec coverage:** §1 domain errors → Task 1; §2 adapter off-load+classify → Task 2; §3 HTTP handlers+i18n → Task 3; §4 presign expiry (S1-4) + set_avatar (S1-5) + dead module (S1-7) → Task 4; §5 tests distributed across tasks (classification unit, handler unit+registration, adapter-raise, expiry, set_avatar). All covered.
- **Not re-doing done work:** delete ordering/compensation/sanitize are already on main — untouched here.
- **Type consistency:** `_classify_storage(exc) -> Exception`; `StorageError`/`StorageUnavailableError`/`StorageNotFoundError` and `DEFAULT_PRESIGN_TTL` names used identically across Tasks 1–4; `delete` stays `-> bool`.
- **YAGNI:** no async-client migration, no orphan sweeper, no constraint-code granularity — all explicitly out of scope in the spec.
