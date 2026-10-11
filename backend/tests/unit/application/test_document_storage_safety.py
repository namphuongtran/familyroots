"""Storage-safety guarantees for DocumentCommandHandler (review H2).

Delete is a soft-delete (ADR-019): mark_deleted + repo.save flags the row and commits;
the blob is never touched by delete at all — it survives until the retention purge job,
reclaimable/recoverable via restore.

Upload's guarantees (the H2 compensation and the H3 key sanitizing) moved with upload
itself to ``DocumentUploadHandler``: ``test_document_upload_handler.py`` (ADR-068).
"""

import uuid

from app.application.document.handlers import DocumentCommandHandler
from app.domain.document.entity import Document
from app.domain.shared.value_objects import ActorInfo


class Recorder:
    def __init__(self) -> None:
        self.calls: list[str] = []


class FakeStorage:
    def __init__(self, rec: Recorder, *, fail_delete: bool = False) -> None:
        self._rec = rec
        self.deleted: list[str] = []
        self.fail_delete = fail_delete

    async def delete(self, storage_path: str) -> bool:
        self.deleted.append(storage_path)
        self._rec.calls.append("storage.delete")
        return not self.fail_delete

    async def get_presigned_url(self, storage_path: str, expires_in: int = 3600) -> str:
        return "https://signed/" + storage_path

    async def publish_public(
        self, *, source_path: str, destination_path: str, content_type: str | None
    ) -> str:
        # ADR-036 avatar publish — not exercised by this module.
        raise AssertionError("publish_public called unexpectedly")


class FakeRepo:
    def __init__(self, rec: Recorder, existing: Document | None = None) -> None:
        self._rec = rec
        self.saved: list[Document] = []
        self._existing = existing

    async def person_in_clan(self, person_id: uuid.UUID, clan_id: uuid.UUID) -> bool:
        return True

    async def save(self, doc: Document) -> None:
        self.saved.append(doc)
        self._rec.calls.append("repo.save")

    async def get_by_id(self, doc_id: uuid.UUID, clan_id: uuid.UUID) -> Document | None:
        return self._existing

    async def get_deleted(self, doc_id: uuid.UUID, clan_id: uuid.UUID) -> Document | None:
        return self._existing

    async def list_in_clan(self, *args: object, **kwargs: object) -> list[Document]:
        return []

    async def get_person_avatars(self, *args: object, **kwargs: object) -> list[Document]:
        return []


class FakePersonRepo:
    """PersonRepository stand-in. Only `set_avatar` touches it (ADR-036) and no test
    in this module calls that, so any access here means the wiring drifted."""

    def __getattr__(self, name: str) -> object:
        raise AssertionError(f"unexpected person-repository call: {name}")


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


# ── ADR-019: delete is a soft-delete that never touches storage ──────────────
async def test_delete_soft_deletes_and_never_touches_storage() -> None:
    """Re-pointed (was H2 DB-first-then-storage): delete now flags the row
    (mark_deleted + repo.save) and commits; the blob is left for the retention
    purge job, so storage.delete must not be called at all."""
    rec = Recorder()
    clan_id = uuid.uuid4()
    doc = _doc(clan_id)
    storage = FakeStorage(rec)
    repo = FakeRepo(rec, existing=doc)
    handler = DocumentCommandHandler(repo, storage, FakeUow(rec), FakePersonRepo())  # type: ignore[arg-type]

    await handler.delete(document_id=doc.id, clan_id=clan_id, actor=_actor())

    assert rec.calls == ["repo.save", "commit"]
    assert storage.deleted == []
    assert repo.saved == [doc]
    assert doc.is_deleted is True
    assert doc.deleted_at is not None


async def test_delete_succeeds_even_if_storage_would_have_failed() -> None:
    """Re-pointed (was: delete tolerates a failing storage.delete). Since delete
    no longer calls storage at all, a storage outage (fail_delete=True) can no
    longer affect it — this asserts storage genuinely stays untouched."""
    rec = Recorder()
    clan_id = uuid.uuid4()
    doc = _doc(clan_id)
    repo = FakeRepo(rec, existing=doc)
    uow = FakeUow(rec)
    storage = FakeStorage(rec, fail_delete=True)
    handler = DocumentCommandHandler(repo, storage, uow, FakePersonRepo())  # type: ignore[arg-type]

    await handler.delete(document_id=doc.id, clan_id=clan_id, actor=_actor())

    assert repo.saved == [doc] and uow.committed == 1
    assert storage.deleted == []  # never attempted — blob survives until purge
    assert rec.calls == ["repo.save", "commit"]
