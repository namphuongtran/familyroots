"""DocumentUploadHandler: sign, then confirm, with the bytes going straight to Storage.

ADR-068. Each case reads an outcome from the fake object store or the fake repository:
which objects exist after the call, which were moved or deleted, and which row was saved.
The path rule and the re-read at confirm are the two guards that matter most, because
the client sends the path back and the signed URL carries no type or size limit.

Negative controls, run 2026-10-11:
- with ``parse_staged_upload_path``'s clan prefix replaced by a wildcard, the cross-clan
  confirm case fails: the other clan's file is moved and saved;
- with the ``check_upload_file`` re-read at confirm removed, the type-mismatch and the
  over-limit cases fail: the file is moved into ``documents/`` and saved.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.application.document.upload import DocumentUploadHandler
from app.domain.document.entity import Document
from app.domain.document.repository import (
    DEFAULT_PRESIGN_TTL,
    SIGNED_UPLOAD_TTL,
    SignedUpload,
    StorageNotFoundError,
    StoredObject,
)
from app.domain.document.storage_paths import safe_extension
from app.domain.shared.exceptions import EntityNotFoundError, ValidationError
from app.domain.shared.value_objects import ActorInfo
from app.schemas.document import DocumentResponse

MB = 1024 * 1024


class FakeObjectStore:
    """An in-memory private bucket. ``put`` is what the browser's PUT does."""

    def __init__(self) -> None:
        self.objects: dict[str, StoredObject] = {}
        self.signed: list[str] = []
        self.moves: list[tuple[str, str]] = []
        self.deleted: list[str] = []

    def put(self, path: str, size_bytes: int, content_type: str | None) -> None:
        self.objects[path] = StoredObject(size_bytes=size_bytes, content_type=content_type)

    async def create_signed_upload(self, path: str) -> SignedUpload:
        self.signed.append(path)
        return SignedUpload(upload_url=f"https://storage.example/sign/{path}", token="tok")

    async def stat(self, path: str) -> StoredObject:
        if path not in self.objects:
            raise StorageNotFoundError(path)
        return self.objects[path]

    async def move(self, from_path: str, to_path: str) -> None:
        if from_path not in self.objects:
            raise StorageNotFoundError(from_path)
        self.objects[to_path] = self.objects.pop(from_path)
        self.moves.append((from_path, to_path))

    async def delete(self, storage_path: str) -> bool:
        self.objects.pop(storage_path, None)
        self.deleted.append(storage_path)
        return True

    async def get_presigned_url(self, storage_path: str, expires_in: int = 3600) -> str:
        return f"https://signed.example/{storage_path}"


class FakeRepo:
    def __init__(self, *, persons_in_clan: bool = True) -> None:
        self.saved: list[Document] = []
        self._persons_in_clan = persons_in_clan

    async def person_in_clan(self, person_id: uuid.UUID, clan_id: uuid.UUID) -> bool:
        return self._persons_in_clan

    async def save(self, doc: Document) -> None:
        self.saved.append(doc)


class FakeUow:
    def __init__(self, *, fail_commit: bool = False) -> None:
        self.fail_commit = fail_commit
        self.committed = 0

    async def rollback(self) -> None:
        pass

    async def commit(self) -> None:
        if self.fail_commit:
            raise RuntimeError("commit failed")
        self.committed += 1


def _handler(
    store: FakeObjectStore, repo: FakeRepo | None = None, uow: FakeUow | None = None
) -> DocumentUploadHandler:
    return DocumentUploadHandler(repo or FakeRepo(), store, uow or FakeUow())  # type: ignore[arg-type]


def _actor() -> ActorInfo:
    return ActorInfo.from_jwt({"sub": str(uuid.uuid4())}, "editor")


async def _staged(
    store: FakeObjectStore,
    clan_id: uuid.UUID,
    *,
    size_bytes: int = 1024,
    content_type: str | None = "image/jpeg",
    filename: str = "gia-pha.jpg",
) -> str:
    """Sign as the client would, then upload as the browser would."""
    signed = await _handler(store).sign(
        clan_id=clan_id, filename=filename, content_type="image/jpeg", size_bytes=size_bytes
    )
    store.put(signed.storage_path, size_bytes, content_type)
    return signed.storage_path


async def _confirm(
    store: FakeObjectStore,
    clan_id: uuid.UUID,
    storage_path: str,
    *,
    repo: FakeRepo | None = None,
    uow: FakeUow | None = None,
    max_file_size_bytes: int = 50 * MB,
    person_id: uuid.UUID | None = None,
) -> DocumentResponse:
    return await _handler(store, repo, uow).confirm(
        clan_id=clan_id,
        actor=_actor(),
        storage_path=storage_path,
        title="Gia phả",
        document_type="photo",
        original_filename="gia-pha.jpg",
        person_id=person_id,
        max_file_size_bytes=max_file_size_bytes,
    )


# ── The extension that goes into a key ───────────────────────────────────────


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
    ext = safe_extension(filename)
    assert ext == expected
    assert "/" not in ext and "." not in ext


# ── Sign ─────────────────────────────────────────────────────────────────────


async def test_sign_puts_the_key_in_this_clans_staging_folder_whatever_the_filename() -> None:
    store = FakeObjectStore()
    clan_id = uuid.uuid4()

    signed = await _handler(store).sign(
        clan_id=clan_id,
        filename="pwn.jpg/../../victim-clan/secret",
        content_type="image/jpeg",
        size_bytes=10,
    )

    assert store.signed == [signed.storage_path]
    assert signed.storage_path.startswith(f"clans/{clan_id}/uploads/")
    assert ".." not in signed.storage_path
    assert signed.storage_path.count("/") == 3  # clans / {clan} / uploads / {file}.{ext}
    assert signed.upload_url == f"https://storage.example/sign/{signed.storage_path}"


@pytest.mark.parametrize(
    ("content_type", "size_bytes", "code"),
    [
        ("text/html", 10, "invalid_mime_type"),
        ("application/x-msdownload", 10, "invalid_mime_type"),
        ("image/jpeg", 50 * MB + 1, "file_too_large"),
    ],
)
async def test_sign_refuses_a_declared_file_that_breaks_a_rule_and_signs_nothing(
    content_type: str, size_bytes: int, code: str
) -> None:
    store = FakeObjectStore()
    with pytest.raises(ValidationError) as exc_info:
        await _handler(store).sign(
            clan_id=uuid.uuid4(),
            filename="f.bin",
            content_type=content_type,
            size_bytes=size_bytes,
            max_file_size_bytes=50 * MB,
        )
    assert exc_info.value.code == code
    assert store.signed == []


# ── Confirm: the path rule ───────────────────────────────────────────────────


async def test_confirm_moves_the_staged_file_into_documents_and_saves_what_storage_holds() -> None:
    store = FakeObjectStore()
    repo = FakeRepo()
    clan_id = uuid.uuid4()
    staged = await _staged(store, clan_id, size_bytes=20 * MB, content_type="image/png")

    response = await _confirm(store, clan_id, staged, repo=repo)

    expected = staged.replace("/uploads/", "/documents/")
    assert store.moves == [(staged, expected)]
    assert set(store.objects) == {expected}
    (doc,) = repo.saved
    # The stored facts, not the declaration: signed as image/jpeg, stored as image/png.
    assert (doc.storage_path, doc.file_size_bytes, doc.mime_type) == (
        expected,
        20 * MB,
        "image/png",
    )
    assert doc.original_filename == "gia-pha.jpg"
    assert response.presigned_url == f"https://signed.example/{expected}"


async def test_confirm_refuses_another_clans_staged_path_and_leaves_its_file_alone() -> None:
    store = FakeObjectStore()
    repo = FakeRepo()
    clan_a, clan_b = uuid.uuid4(), uuid.uuid4()
    theirs = await _staged(store, clan_b)

    with pytest.raises(ValidationError) as exc_info:
        await _confirm(store, clan_a, theirs, repo=repo)

    assert exc_info.value.code == "document.upload_path_invalid"
    assert set(store.objects) == {theirs}
    assert store.moves == [] and store.deleted == [] and repo.saved == []


def _paths_that_are_not_a_staged_upload(clan_id: uuid.UUID) -> list[str]:
    file_id = uuid.uuid4()
    return [
        f"clans/{clan_id}/documents/{file_id}.jpg",  # a confirmed document's blob
        f"clans/{clan_id}/avatars/{file_id}",
        f"clans/{clan_id}/uploads/../documents/{file_id}.jpg",
        f"clans/{clan_id}/uploads/{file_id}.jpg/../../x.jpg",
        f"clans/{clan_id}/uploads/{str(file_id).upper()}.jpg",
        f"clans/{clan_id}/uploads/{file_id}.JPG",
        f"clans/{clan_id}/uploads/{file_id}",
        f"clans/{clan_id}/uploads/{file_id}.jpg ",
        f"/clans/{clan_id}/uploads/{file_id}.jpg",
        f"clans/{str(clan_id).upper()}/uploads/{file_id}.jpg",
        f"clans/{clan_id}/uploads/sub/{file_id}.jpg",
        f"clans/{clan_id}/uploads/{file_id}.toolongextension",
    ]


async def test_confirm_refuses_every_path_that_is_not_a_staged_upload_of_this_clan() -> None:
    clan_id = uuid.uuid4()
    for path in _paths_that_are_not_a_staged_upload(clan_id):
        store = FakeObjectStore()
        store.put(path, 10, "image/jpeg")
        repo = FakeRepo()
        with pytest.raises(ValidationError) as exc_info:
            await _confirm(store, clan_id, path, repo=repo)
        assert exc_info.value.code == "document.upload_path_invalid", path
        assert set(store.objects) == {path}, path
        assert repo.saved == [], path


# ── Confirm: the re-read of what Storage holds ───────────────────────────────


@pytest.mark.parametrize(
    ("size_bytes", "content_type", "code"),
    [
        (1024, "text/html", "invalid_mime_type"),  # signed as image/jpeg, stored as HTML
        (1024, None, "invalid_mime_type"),  # stored with no type at all
        (2 * MB, "image/jpeg", "file_too_large"),  # over the limit under test
    ],
)
async def test_confirm_refuses_a_stored_file_that_breaks_a_rule_and_deletes_it(
    size_bytes: int, content_type: str | None, code: str
) -> None:
    store = FakeObjectStore()
    repo = FakeRepo()
    clan_id = uuid.uuid4()
    staged = await _staged(store, clan_id, size_bytes=size_bytes, content_type=content_type)

    with pytest.raises(ValidationError) as exc_info:
        await _confirm(store, clan_id, staged, repo=repo, max_file_size_bytes=1 * MB)

    assert exc_info.value.code == code
    assert store.objects == {}
    assert store.deleted == [staged]
    assert store.moves == [] and repo.saved == []


async def test_confirm_of_a_path_nothing_was_uploaded_to_is_not_found() -> None:
    store = FakeObjectStore()
    clan_id = uuid.uuid4()
    signed = await _handler(store).sign(
        clan_id=clan_id, filename="a.jpg", content_type="image/jpeg", size_bytes=10
    )

    with pytest.raises(EntityNotFoundError) as exc_info:
        await _confirm(store, clan_id, signed.storage_path)
    assert exc_info.value.code == "document.upload_not_found"


async def test_a_second_confirm_of_one_path_is_not_found_and_saves_no_second_row() -> None:
    store = FakeObjectStore()
    repo = FakeRepo()
    clan_id = uuid.uuid4()
    staged = await _staged(store, clan_id)
    await _confirm(store, clan_id, staged, repo=repo)

    with pytest.raises(EntityNotFoundError) as exc_info:
        await _confirm(store, clan_id, staged, repo=repo)

    assert exc_info.value.code == "document.upload_not_found"
    assert len(repo.saved) == 1


async def test_confirm_that_loses_the_move_race_is_not_found_and_saves_nothing() -> None:
    """Two confirms of one path can both pass stat; only one move can succeed."""

    class LosingStore(FakeObjectStore):
        async def move(self, from_path: str, to_path: str) -> None:
            raise StorageNotFoundError(from_path)

    store = LosingStore()
    repo = FakeRepo()
    clan_id = uuid.uuid4()
    staged = await _staged(store, clan_id)

    with pytest.raises(EntityNotFoundError) as exc_info:
        await _confirm(store, clan_id, staged, repo=repo)
    assert exc_info.value.code == "document.upload_not_found"
    assert repo.saved == []


async def test_confirm_refuses_a_person_of_another_clan_before_touching_storage() -> None:
    store = FakeObjectStore()
    clan_id = uuid.uuid4()
    staged = await _staged(store, clan_id)

    with pytest.raises(EntityNotFoundError) as exc_info:
        await _confirm(
            store, clan_id, staged, repo=FakeRepo(persons_in_clan=False), person_id=uuid.uuid4()
        )
    assert exc_info.value.code == "person_not_found"
    # Kept, so the client can confirm again with the right person.
    assert set(store.objects) == {staged}
    assert store.moves == []


async def test_confirm_deletes_the_moved_blob_when_the_commit_fails() -> None:
    store = FakeObjectStore()
    clan_id = uuid.uuid4()
    staged = await _staged(store, clan_id)

    with pytest.raises(RuntimeError, match="commit failed"):
        await _confirm(store, clan_id, staged, uow=FakeUow(fail_commit=True))

    moved = staged.replace("/uploads/", "/documents/")
    assert store.deleted == [moved]
    assert store.objects == {}


# ── Deadlines the client schedules off ───────────────────────────────────────


def _seconds_from_now(moment: datetime | None) -> float:
    assert moment is not None
    return (moment - datetime.now(UTC)).total_seconds()


async def test_sign_states_the_signed_urls_two_hour_deadline() -> None:
    signed = await _handler(FakeObjectStore()).sign(
        clan_id=uuid.uuid4(), filename="a.jpg", content_type="image/jpeg", size_bytes=10
    )
    assert SIGNED_UPLOAD_TTL - 60 <= _seconds_from_now(signed.expires_at) <= SIGNED_UPLOAD_TTL


async def test_confirm_states_the_presigned_urls_expiry() -> None:
    store = FakeObjectStore()
    clan_id = uuid.uuid4()
    response = await _confirm(store, clan_id, await _staged(store, clan_id))
    expires_at = response.presigned_url_expires_at
    assert DEFAULT_PRESIGN_TTL - 60 <= _seconds_from_now(expires_at) <= DEFAULT_PRESIGN_TTL
