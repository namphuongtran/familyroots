"""Storage-safety guarantees for DocumentCommandHandler (review H2 + H3).

H2 — transaction/blob ordering:
  * delete is DB-first: the row is committed before the blob is removed, so a
    storage failure can only orphan a blob (reclaimable), never leave a row
    pointing at a missing object;
  * upload compensates: if metadata persistence fails after the blob is written,
    the just-uploaded blob is deleted so no orphan is leaked.
H3 — the storage key extension is sanitized so a crafted filename cannot escape
  the `clans/{clan_id}/documents/` tenancy prefix via `/` or `..`.
"""

import uuid

import pytest

from app.application.document.handlers import DocumentCommandHandler, _safe_extension
from app.domain.document.entity import Document
from app.domain.shared.value_objects import ActorInfo

# asyncio_mode = "auto" (pyproject) auto-collects the async tests; the sync
# parametrized test must NOT carry an asyncio mark, so none is set module-wide.


class Recorder:
    def __init__(self) -> None:
        self.calls: list[str] = []


class FakeStorage:
    def __init__(self, rec: Recorder, *, fail_delete: bool = False) -> None:
        self._rec = rec
        self.uploaded: list[str] = []
        self.deleted: list[str] = []
        self.fail_delete = fail_delete

    async def upload(self, path: str, content: bytes, content_type: str | None) -> str:
        self.uploaded.append(path)
        self._rec.calls.append("storage.upload")
        return path

    async def delete(self, storage_path: str) -> bool:
        self.deleted.append(storage_path)
        self._rec.calls.append("storage.delete")
        return not self.fail_delete

    async def get_presigned_url(self, storage_path: str, expires_in: int = 3600) -> str:
        return "https://signed/" + storage_path


class FakeRepo:
    def __init__(self, rec: Recorder, existing: Document | None = None) -> None:
        self._rec = rec
        self.saved: list[Document] = []
        self.deleted: list[Document] = []
        self._existing = existing

    async def person_in_clan(self, person_id: uuid.UUID, clan_id: uuid.UUID) -> bool:
        return True

    async def save(self, doc: Document) -> None:
        self.saved.append(doc)

    async def delete(self, doc: Document) -> None:
        self.deleted.append(doc)
        self._rec.calls.append("repo.delete")

    async def get_by_id(self, doc_id: uuid.UUID, clan_id: uuid.UUID) -> Document | None:
        return self._existing

    async def list_in_clan(self, *args: object, **kwargs: object) -> list[Document]:
        return []

    async def get_person_avatars(self, *args: object, **kwargs: object) -> list[Document]:
        return []


class FakeUow:
    def __init__(self, rec: Recorder, *, fail_commit: bool = False) -> None:
        self._rec = rec
        self.fail_commit = fail_commit
        self.committed = 0

    def track(self, aggregate: object) -> None:
        pass

    async def flush(self) -> None:
        pass

    async def rollback(self) -> None:
        pass

    async def commit(self) -> None:
        if self.fail_commit:
            raise RuntimeError("commit failed")
        self.committed += 1
        self._rec.calls.append("commit")


def _actor() -> ActorInfo:
    return ActorInfo.from_jwt({"sub": str(uuid.uuid4())}, "editor")


def _doc(clan_id: uuid.UUID) -> Document:
    return Document.create(
        clan_id=clan_id,
        actor=_actor(),
        title="t",
        document_type="photo",
        storage_path=f"clans/{clan_id}/documents/{uuid.uuid4()}.jpg",
        mime_type="image/jpeg",
        file_size_bytes=1024,
        original_filename="p.jpg",
    )


# ── H3: extension sanitization ────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("photo.jpg", "jpg"),
        ("x.JPEG", "jpeg"),
        ("archive.tar.gz", "gz"),
        ("noextension", "bin"),
        ("", "bin"),
        (None, "bin"),
        # traversal attempts — all `/` and `.` stripped, so the key can't escape.
        # (tail is taken after the LAST dot, then reduced to <=10 alnum chars)
        ("x.jpg/../../other-clan/evil", "otherclane"),
        ("a.j/pg", "jpg"),
        ("b.../..", "bin"),
    ],
)
def test_safe_extension_strips_path_chars(filename: str | None, expected: str) -> None:
    ext = _safe_extension(filename)
    assert ext == expected
    assert "/" not in ext and "." not in ext


async def test_upload_storage_key_cannot_escape_clan_prefix() -> None:
    rec = Recorder()
    storage = FakeStorage(rec)
    clan_id = uuid.uuid4()
    handler = DocumentCommandHandler(FakeRepo(rec), storage, FakeUow(rec))

    await handler.upload(
        file_content=b"x",
        filename="pwn.jpg/../../victim-clan/secret",
        content_type="image/jpeg",
        title="t",
        document_type="photo",
        clan_id=clan_id,
        actor=_actor(),
    )

    (path,) = storage.uploaded
    assert path.startswith(f"clans/{clan_id}/documents/")
    assert ".." not in path
    # fixed 3-level key: clans / {clan} / documents / {file}.{ext}
    assert path.count("/") == 3


# ── H2: upload compensation ───────────────────────────────────────────────────
async def test_upload_deletes_blob_when_commit_fails() -> None:
    rec = Recorder()
    storage = FakeStorage(rec)
    handler = DocumentCommandHandler(FakeRepo(rec), storage, FakeUow(rec, fail_commit=True))

    with pytest.raises(RuntimeError, match="commit failed"):
        await handler.upload(
            file_content=b"x",
            filename="p.jpg",
            content_type="image/jpeg",
            title="t",
            document_type="photo",
            clan_id=uuid.uuid4(),
            actor=_actor(),
        )

    # The orphan is compensated: the exact blob uploaded is the one deleted.
    assert storage.uploaded == storage.deleted
    assert len(storage.deleted) == 1


# ── H2: delete is DB-first ────────────────────────────────────────────────────
async def test_delete_commits_before_touching_storage() -> None:
    rec = Recorder()
    clan_id = uuid.uuid4()
    doc = _doc(clan_id)
    storage = FakeStorage(rec)
    repo = FakeRepo(rec, existing=doc)
    handler = DocumentCommandHandler(repo, storage, FakeUow(rec))

    await handler.delete(document_id=doc.id, clan_id=clan_id, actor=_actor())

    # DB row removed and committed strictly before the blob is deleted.
    assert rec.calls == ["repo.delete", "commit", "storage.delete"]
    assert storage.deleted == [doc.storage_path]


async def test_delete_succeeds_even_if_storage_delete_fails() -> None:
    rec = Recorder()
    clan_id = uuid.uuid4()
    doc = _doc(clan_id)
    repo = FakeRepo(rec, existing=doc)
    uow = FakeUow(rec)
    storage = FakeStorage(rec, fail_delete=True)
    handler = DocumentCommandHandler(repo, storage, uow)

    # A failing storage delete must NOT raise or roll back: the DB row removal is
    # already durable, and the blob failure is swallowed (logged as an orphan).
    await handler.delete(document_id=doc.id, clan_id=clan_id, actor=_actor())

    assert repo.deleted == [doc] and uow.committed == 1
    assert storage.deleted == [doc.storage_path]  # deletion was attempted, after commit
    assert rec.calls == ["repo.delete", "commit", "storage.delete"]
