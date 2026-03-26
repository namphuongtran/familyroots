"""Unit tests for Document domain entity."""

import uuid

import pytest

from app.domain.document.entity import Document
from app.domain.document.events import DocumentCreated, DocumentDeleted
from app.domain.shared.exceptions import BusinessRuleViolation, ValidationError
from app.domain.shared.value_objects import ActorInfo

# ── Document.create ──────────────────────────────────────────────


class TestDocumentCreate:
    def test_create_sets_fields(self) -> None:
        actor = ActorInfo(user_id=uuid.uuid4(), role="editor")
        clan_id = uuid.uuid4()
        doc = Document.create(
            clan_id=clan_id,
            actor=actor,
            title="Death Certificate",
            document_type="certificate",
            storage_path="clans/abc/documents/xyz.pdf",
            mime_type="application/pdf",
            file_size_bytes=1024,
        )
        assert doc.title == "Death Certificate"
        assert doc.document_type == "certificate"
        assert doc.clan_id == clan_id
        assert doc.created_by == actor.user_id

    def test_create_emits_event(self) -> None:
        actor = ActorInfo(user_id=uuid.uuid4(), role="editor")
        doc = Document.create(
            clan_id=uuid.uuid4(),
            actor=actor,
            title="Photo",
            document_type="photo",
            storage_path="test.jpg",
            mime_type="image/jpeg",
        )
        events = doc.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], DocumentCreated)
        assert events[0].document_id == doc.id
        assert events[0].action == "document.upload"

    def test_create_rejects_invalid_doc_type(self) -> None:
        actor = ActorInfo(user_id=uuid.uuid4(), role="editor")
        with pytest.raises(ValidationError, match="invalid_document_type"):
            Document.create(
                clan_id=uuid.uuid4(),
                actor=actor,
                title="Test",
                document_type="invalid_type",
                storage_path="test.bin",
            )

    def test_create_rejects_invalid_mime(self) -> None:
        actor = ActorInfo(user_id=uuid.uuid4(), role="editor")
        with pytest.raises(ValidationError, match="invalid_mime_type"):
            Document.create(
                clan_id=uuid.uuid4(),
                actor=actor,
                title="Test",
                document_type="photo",
                storage_path="test.exe",
                mime_type="application/x-executable",
            )

    def test_create_rejects_oversized_file(self) -> None:
        actor = ActorInfo(user_id=uuid.uuid4(), role="editor")
        with pytest.raises(ValidationError, match="file_too_large"):
            Document.create(
                clan_id=uuid.uuid4(),
                actor=actor,
                title="Test",
                document_type="video",
                storage_path="test.mp4",
                mime_type="video/mp4",
                file_size_bytes=100 * 1024 * 1024,  # 100 MB
            )


# ── Document.set_avatar ──────────────────────────────────────────


class TestDocumentAvatar:
    def test_set_avatar_on_photo(self) -> None:
        actor = ActorInfo(user_id=uuid.uuid4(), role="editor")
        doc = Document.create(
            clan_id=uuid.uuid4(),
            actor=actor,
            title="Profile Pic",
            document_type="photo",
            storage_path="test.jpg",
            person_id=uuid.uuid4(),
        )
        doc.set_avatar()
        assert doc.is_avatar is True

    def test_set_avatar_rejects_non_photo(self) -> None:
        actor = ActorInfo(user_id=uuid.uuid4(), role="editor")
        doc = Document.create(
            clan_id=uuid.uuid4(),
            actor=actor,
            title="Certificate",
            document_type="certificate",
            storage_path="test.pdf",
            person_id=uuid.uuid4(),
        )
        with pytest.raises(BusinessRuleViolation, match="only_photo_can_be_avatar"):
            doc.set_avatar()

    def test_set_avatar_rejects_unlinked_doc(self) -> None:
        actor = ActorInfo(user_id=uuid.uuid4(), role="editor")
        doc = Document.create(
            clan_id=uuid.uuid4(),
            actor=actor,
            title="Photo",
            document_type="photo",
            storage_path="test.jpg",
            # No person_id
        )
        with pytest.raises(BusinessRuleViolation, match="document_not_linked_to_person"):
            doc.set_avatar()

    def test_unset_avatar(self) -> None:
        actor = ActorInfo(user_id=uuid.uuid4(), role="editor")
        doc = Document.create(
            clan_id=uuid.uuid4(),
            actor=actor,
            title="Photo",
            document_type="photo",
            storage_path="test.jpg",
            person_id=uuid.uuid4(),
        )
        doc.set_avatar()
        assert doc.is_avatar is True
        doc.unset_avatar()
        assert doc.is_avatar is False


# ── Document.mark_deleted ────────────────────────────────────────


class TestDocumentDelete:
    def test_mark_deleted_emits_event(self) -> None:
        actor = ActorInfo(user_id=uuid.uuid4(), role="admin")
        doc = Document.create(
            clan_id=uuid.uuid4(),
            actor=actor,
            title="Test",
            document_type="photo",
            storage_path="test.jpg",
        )
        doc.collect_events()

        doc.mark_deleted(actor)
        events = doc.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], DocumentDeleted)
        assert events[0].action == "document.delete"
        assert events[0].resource_id == doc.id
