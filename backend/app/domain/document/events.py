"""Domain events for the Document bounded context."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from app.domain.shared.events import AuditableEvent


@dataclass(frozen=True)
class DocumentCreated(AuditableEvent):
    """Emitted when a new document is uploaded."""

    document_id: uuid.UUID = field(default_factory=uuid.uuid4)
    title: str = ""
    document_type: str = ""

    def __post_init__(self) -> None:
        if not self.action:
            object.__setattr__(self, "action", "document.upload")
        if not self.resource_type:
            object.__setattr__(self, "resource_type", "document")
        if self.resource_id is None:
            object.__setattr__(self, "resource_id", self.document_id)


@dataclass(frozen=True)
class DocumentDeleted(AuditableEvent):
    """Emitted when a document is deleted."""

    document_id: uuid.UUID = field(default_factory=uuid.uuid4)

    def __post_init__(self) -> None:
        if not self.action:
            object.__setattr__(self, "action", "document.delete")
        if not self.resource_type:
            object.__setattr__(self, "resource_type", "document")
        if self.resource_id is None:
            object.__setattr__(self, "resource_id", self.document_id)
