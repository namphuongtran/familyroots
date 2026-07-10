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
