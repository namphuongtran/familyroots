"""upload sets a real future expiry; set_avatar publishes a permanent public URL.

ADR-036 changed set_avatar from "flip a flag, then mint a throwaway 30-day presigned
URL" into the single writer of ``persons.avatar_url``. These tests pin the properties
that make that safe:

* the stored URL is the published permanent one, never a presigned URL;
* the destination path stays inside the acting clan's prefix;
* the blob copy happens with no DB transaction open (ADR-028);
* every storage failure fails **closed** — no half-set avatar, no dead URL.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from app.application.document.handlers import DocumentCommandHandler
from app.domain.document.entity import Document
from app.domain.document.repository import (
    DEFAULT_PRESIGN_TTL,
    StorageBucketNotConfiguredError,
    StorageUnavailableError,
)
from app.domain.person.entity import Person
from app.domain.shared.exceptions import BusinessRuleViolation
from app.domain.shared.value_objects import ActorInfo


class _FakeStorage:
    def __init__(
        self,
        *,
        presign_raises: bool = False,
        publish_raises: Exception | None = None,
        publish_returns: str | None = None,
    ) -> None:
        self.presign_raises = presign_raises
        self.publish_raises = publish_raises
        self.publish_returns = publish_returns
        self.presign_calls: list[str] = []
        self.published: list[tuple[str, str, str | None]] = []

    async def upload(self, path: str, content: bytes, content_type: str | None) -> str:
        return path

    async def delete(self, storage_path: str) -> bool:
        return True

    async def get_presigned_url(
        self, storage_path: str, expires_in: int = DEFAULT_PRESIGN_TTL
    ) -> str:
        self.presign_calls.append(storage_path)
        if self.presign_raises:
            raise StorageUnavailableError("down")
        return "https://signed.example/url?token=abc123&expires=999"

    async def publish_public(
        self, *, source_path: str, destination_path: str, content_type: str | None
    ) -> str:
        if self.publish_raises is not None:
            raise self.publish_raises
        self.published.append((source_path, destination_path, content_type))
        if self.publish_returns is not None:
            return self.publish_returns
        return f"https://proj.supabase.co/storage/v1/object/public/avatars/{destination_path}"


class _FakeUoW:
    def __init__(self) -> None:
        self.commits = 0
        self.calls: list[str] = []

    def track(self, agg: Any) -> None: ...
    async def flush(self) -> None: ...

    async def rollback(self) -> None:
        self.calls.append("rollback")

    async def commit(self) -> None:
        self.calls.append("commit")
        self.commits += 1


class _FakeDocumentRepo:
    """Minimal DocumentRepository double covering only what upload/set_avatar touch.

    Holds one pre-existing "photo" Document (linked to a person) so
    ``set_avatar`` can validate person-linkage and type without hitting a
    real database.
    """

    def __init__(self, *, storage_path: str | None = None) -> None:
        self.clan_id = uuid.uuid4()
        self.actor_id = uuid.uuid4()
        self.person_id = uuid.uuid4()
        self.saved: list[Document] = []

        self._existing_photo = Document.create(
            clan_id=self.clan_id,
            actor=ActorInfo(user_id=self.actor_id, role="editor"),
            title="existing avatar candidate",
            document_type="photo",
            storage_path=storage_path or f"clans/{self.clan_id}/documents/existing.jpg",
            mime_type="image/jpeg",
            file_size_bytes=1024,
            original_filename="existing.jpg",
            person_id=self.person_id,
        )
        self.existing_photo_id = self._existing_photo.id

    async def person_in_clan(self, person_id: uuid.UUID, clan_id: uuid.UUID) -> bool:
        return True

    async def save(self, doc: Document) -> None:
        self.saved.append(doc)

    async def get_by_id(self, document_id: uuid.UUID, clan_id: uuid.UUID) -> Document | None:
        if document_id == self._existing_photo.id:
            return self._existing_photo
        return None

    async def list_in_clan(self, *args: object, **kwargs: object) -> list[Document]:
        return []

    async def get_person_avatars(self, *args: object, **kwargs: object) -> list[Document]:
        return []


class _FakePersonRepo:
    """PersonRepository double holding one live member of the acting clan."""

    def __init__(self, person_id: uuid.UUID, *, member: bool = True) -> None:
        self.person = Person(id=person_id, full_name="Nguyễn Văn A")
        self._member = member
        self.saved: list[Person] = []

    async def get_in_clan(
        self, person_id: uuid.UUID, clan_id: uuid.UUID, include_deleted: bool = False
    ) -> Person | None:
        if not self._member or person_id != self.person.id:
            return None
        return self.person

    async def save(self, person: Person, *, expected_version: int | None = None) -> None:
        self.saved.append(person)


@pytest.fixture
def document_repo_fake() -> _FakeDocumentRepo:
    return _FakeDocumentRepo()


def _handler(
    repo: _FakeDocumentRepo,
    storage: _FakeStorage,
    uow: _FakeUoW,
    person_repo: _FakePersonRepo | None = None,
) -> DocumentCommandHandler:
    return DocumentCommandHandler(
        repo,  # type: ignore[arg-type]
        storage,
        uow,
        person_repo or _FakePersonRepo(repo.person_id),  # type: ignore[arg-type]
    )


async def _set_avatar(handler: DocumentCommandHandler, repo: _FakeDocumentRepo) -> str:
    return await handler.set_avatar(
        document_id=repo.existing_photo_id,
        clan_id=repo.clan_id,
        actor=ActorInfo(user_id=repo.actor_id, role="editor"),
    )


@pytest.mark.asyncio
async def test_upload_expiry_is_now_plus_ttl(document_repo_fake: Any) -> None:
    handler = _handler(document_repo_fake, _FakeStorage(), _FakeUoW())
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
    assert resp.presigned_url_expires_at is not None
    delta = resp.presigned_url_expires_at - datetime.now(UTC)
    assert DEFAULT_PRESIGN_TTL - 60 <= delta.total_seconds() <= DEFAULT_PRESIGN_TTL + 60


@pytest.mark.asyncio
async def test_set_avatar_publishes_and_stamps_the_permanent_url(
    document_repo_fake: _FakeDocumentRepo,
) -> None:
    storage = _FakeStorage()
    uow = _FakeUoW()
    person_repo = _FakePersonRepo(document_repo_fake.person_id)
    handler = _handler(document_repo_fake, storage, uow, person_repo)

    url = await _set_avatar(handler, document_repo_fake)

    source, destination, content_type = storage.published[0]
    assert source == document_repo_fake._existing_photo.storage_path
    # Clan-scoped, stable per person — the public bucket keeps the same tenancy prefix.
    assert destination == f"clans/{document_repo_fake.clan_id}/avatars/{person_repo.person.id}"
    assert content_type == "image/jpeg"
    assert person_repo.person.avatar_url == url
    assert person_repo.saved == [person_repo.person]
    assert uow.commits == 1


@pytest.mark.asyncio
async def test_set_avatar_never_mints_a_presigned_url(
    document_repo_fake: _FakeDocumentRepo,
) -> None:
    """The 30-day presign that used to be computed and thrown away is gone. A
    presign here would be a URL with an expiry sitting one assignment away from a
    permanent column."""
    storage = _FakeStorage()
    handler = _handler(document_repo_fake, storage, _FakeUoW())

    await _set_avatar(handler, document_repo_fake)

    assert storage.presign_calls == []


@pytest.mark.asyncio
async def test_set_avatar_releases_the_db_connection_before_copying_the_blob(
    document_repo_fake: _FakeDocumentRepo,
) -> None:
    """ADR-028: the multi-second blob copy must not hold a pooled connection."""
    storage = _FakeStorage()
    uow = _FakeUoW()
    handler = _handler(document_repo_fake, storage, uow)

    await _set_avatar(handler, document_repo_fake)

    assert uow.calls == ["rollback", "commit"]


@pytest.mark.asyncio
async def test_set_avatar_fails_closed_when_the_public_bucket_is_missing(
    document_repo_fake: _FakeDocumentRepo,
) -> None:
    """No bucket → no avatar. Writing is_avatar=true with no reachable object would
    leave a person pointing at nothing, permanently."""
    storage = _FakeStorage(publish_raises=StorageBucketNotConfiguredError("no bucket"))
    uow = _FakeUoW()
    person_repo = _FakePersonRepo(document_repo_fake.person_id)
    handler = _handler(document_repo_fake, storage, uow, person_repo)

    with pytest.raises(StorageBucketNotConfiguredError):
        await _set_avatar(handler, document_repo_fake)

    assert uow.commits == 0
    assert person_repo.person.avatar_url is None
    assert person_repo.saved == []
    assert document_repo_fake.saved == []


@pytest.mark.asyncio
async def test_set_avatar_refuses_a_presigned_url_returned_by_storage(
    document_repo_fake: _FakeDocumentRepo,
) -> None:
    """Negative control for the durability invariant: if the adapter ever handed back
    a signed URL, the domain must refuse it rather than let the column rot."""
    storage = _FakeStorage(publish_returns="https://proj.supabase.co/x.jpg?token=abc&exp=1")
    uow = _FakeUoW()
    person_repo = _FakePersonRepo(document_repo_fake.person_id)
    handler = _handler(document_repo_fake, storage, uow, person_repo)

    with pytest.raises(BusinessRuleViolation) as err:
        await _set_avatar(handler, document_repo_fake)

    assert err.value.code == "person.avatar_url_not_permanent"
    assert person_repo.person.avatar_url is None
    assert uow.commits == 0


@pytest.mark.asyncio
async def test_set_avatar_refuses_a_source_path_outside_the_acting_clan() -> None:
    """Clan-isolation backstop. A document row whose storage key does not sit under
    the acting clan's prefix must never be copied into a world-readable bucket."""
    repo = _FakeDocumentRepo(storage_path="clans/00000000-0000-0000-0000-000000000009/docs/x.jpg")
    storage = _FakeStorage()
    uow = _FakeUoW()
    handler = _handler(repo, storage, uow)

    with pytest.raises(BusinessRuleViolation) as err:
        await _set_avatar(handler, repo)

    assert err.value.code == "document.avatar_source_outside_clan"
    assert storage.published == []  # nothing became public
    assert uow.commits == 0


@pytest.mark.asyncio
async def test_set_avatar_404s_when_the_person_is_not_in_the_acting_clan(
    document_repo_fake: _FakeDocumentRepo,
) -> None:
    from app.domain.shared.exceptions import EntityNotFoundError

    storage = _FakeStorage()
    uow = _FakeUoW()
    person_repo = _FakePersonRepo(document_repo_fake.person_id, member=False)
    handler = _handler(document_repo_fake, storage, uow, person_repo)

    with pytest.raises(EntityNotFoundError):
        await _set_avatar(handler, document_repo_fake)

    assert storage.published == []
    assert uow.commits == 0
