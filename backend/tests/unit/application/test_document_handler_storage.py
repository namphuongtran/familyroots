"""upload sets a real future expiry; set_avatar tolerates a storage outage."""

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from app.application.document.handlers import DocumentCommandHandler
from app.domain.document.entity import Document
from app.domain.document.repository import DEFAULT_PRESIGN_TTL, StorageUnavailableError
from app.domain.shared.value_objects import ActorInfo


class _FakeStorage:
    def __init__(self, *, presign_raises: bool = False) -> None:
        self.presign_raises = presign_raises

    async def upload(self, path: str, content: bytes, content_type: str | None) -> str:
        return path

    async def delete(self, storage_path: str) -> bool:
        return True

    async def get_presigned_url(
        self, storage_path: str, expires_in: int = DEFAULT_PRESIGN_TTL
    ) -> str:
        if self.presign_raises:
            raise StorageUnavailableError("down")
        return "https://signed.example/url"


class _FakeUoW:
    def __init__(self) -> None:
        self.commits = 0

    def track(self, agg: Any) -> None: ...
    async def flush(self) -> None: ...
    async def rollback(self) -> None: ...
    async def commit(self) -> None:
        self.commits += 1


class _FakeDocumentRepo:
    """Minimal DocumentRepository double covering only what upload/set_avatar touch.

    Holds one pre-existing "photo" Document (linked to a person) so
    ``set_avatar`` can validate person-linkage and type without hitting a
    real database.
    """

    def __init__(self) -> None:
        self.clan_id = uuid.uuid4()
        self.actor_id = uuid.uuid4()
        self.person_id = uuid.uuid4()
        self.saved: list[Document] = []

        self._existing_photo = Document.create(
            clan_id=self.clan_id,
            actor=ActorInfo(user_id=self.actor_id, role="editor"),
            title="existing avatar candidate",
            document_type="photo",
            storage_path=f"clans/{self.clan_id}/documents/existing.jpg",
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

    async def delete(self, doc: Document) -> None:
        pass

    async def get_by_id(self, document_id: uuid.UUID, clan_id: uuid.UUID) -> Document | None:
        if document_id == self._existing_photo.id:
            return self._existing_photo
        return None

    async def list_in_clan(self, *args: object, **kwargs: object) -> list[Document]:
        return []

    async def get_person_avatars(self, *args: object, **kwargs: object) -> list[Document]:
        return []


@pytest.fixture
def document_repo_fake() -> _FakeDocumentRepo:
    return _FakeDocumentRepo()


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
    assert resp.presigned_url_expires_at is not None
    delta = resp.presigned_url_expires_at - datetime.now(UTC)
    assert DEFAULT_PRESIGN_TTL - 60 <= delta.total_seconds() <= DEFAULT_PRESIGN_TTL + 60


@pytest.mark.asyncio
async def test_set_avatar_returns_none_when_presign_fails(document_repo_fake: Any) -> None:
    uow = _FakeUoW()
    handler = DocumentCommandHandler(document_repo_fake, _FakeStorage(presign_raises=True), uow)
    result = await handler.set_avatar(
        document_id=document_repo_fake.existing_photo_id,
        clan_id=document_repo_fake.clan_id,
        actor=ActorInfo(user_id=document_repo_fake.actor_id, role="editor"),
    )
    assert result is None
    assert uow.commits == 1  # the avatar change committed despite the presign outage
