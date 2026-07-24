"""H5 (review): document upload and clan export must not hold a pooled DB
connection while blocked on a multi-second Supabase Storage call, and the
pool's size/overflow must be env-tunable rather than hardcoded.

The oracle is deterministic (no timing): `TxnRecordingStorage` is a
`StoragePort` double whose every method records `session.in_transaction()` at
the instant it is called. `AsyncSession.in_transaction()` is True iff a
pooled connection is checked out in a live transaction — so a recorded `True`
during an external call is the H5 defect (the connection sits idle-in-txn for
the duration of the network round-trip). A recorded `False` means the
transaction had already been committed (or never begun) before the call, so
no pooled connection was held.

Both the command handler (`DocumentCommandHandler`) and the query handler
(`ExportQueryHandler`) are built directly over a real `AsyncSession` — mirrors
`test_clan_export_json.py`'s DI wiring, but constructed explicitly here (not
via FastAPI `dependency_overrides`) so the storage double can inspect the
EXACT session object the handler's repo/uow use. `SqlAlchemyUnitOfWork.session`
exposes that underlying `AsyncSession`.

Task 2 (not this task) fixes the defects these tests expose; this task is RED
by design for three of the five tests below.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.application.document.handlers import DocumentCommandHandler
from app.application.export.handlers import ExportQueryHandler
from app.domain.shared.exceptions import EntityNotFoundError
from app.domain.shared.value_objects import ActorInfo
from app.infrastructure.event_dispatcher import create_event_dispatcher
from app.infrastructure.persistence.document_repository import SqlAlchemyDocumentRepository
from app.infrastructure.persistence.export_query_port import SqlAlchemyExportQueryPort
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from app.services.clan_export import build_clan_export, to_json_bytes
from app.services.gedcom_export import build_gedcom

pytestmark = pytest.mark.integration

_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


class TxnRecordingStorage:
    """StoragePort double that records the request session's transaction state
    at the instant each network call is made. in_transaction() is True iff a
    pooled connection is checked out in a live txn — so a recorded True means an
    external call ran while holding a connection (the H5 defect)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.upload_in_txn: list[bool] = []
        self.presign_in_txn: list[bool] = []
        self.uploaded: list[str] = []

    async def upload(self, path: str, content: bytes, content_type: str | None) -> str:
        self.upload_in_txn.append(self._session.in_transaction())
        self.uploaded.append(path)
        return path

    async def delete(self, storage_path: str) -> bool:
        return True

    async def get_presigned_url(self, storage_path: str, expires_in: int = 3600) -> str:
        self.presign_in_txn.append(self._session.in_transaction())
        return f"https://signed.example/{storage_path}"


@pytest.fixture()
async def session_factory(
    migrated_db_url: str,
) -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(migrated_db_url)
    yield async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    await engine.dispose()


@pytest.fixture()
async def seeded(session_factory: async_sessionmaker[AsyncSession]) -> dict[str, uuid.UUID]:
    """A clan, an approved admin, a live person (with membership), and a
    second person soft-deleted AFTER being seeded + given a membership (so
    the person_in_clan join sees a real row that is merely filtered by
    is_deleted, matching the read paths — M3, review 2026-07-18)."""
    clan_id = uuid.uuid4()
    admin_id = uuid.uuid4()
    live_person_id = uuid.uuid4()
    deleted_person_id = uuid.uuid4()

    async with session_factory() as s:
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'Txn Pool Clan', :slug)"),
            {"id": clan_id, "slug": f"txn-pool-{clan_id.hex[:8]}"},
        )
        await s.execute(
            sa.text(
                "INSERT INTO user_profiles (id, email, display_name) VALUES (:id, :email, 'admin')"
            ),
            {"id": admin_id, "email": f"{admin_id.hex[:8]}@example.com"},
        )
        await s.execute(
            sa.text(
                "INSERT INTO user_clan_roles "
                "(user_id, clan_id, role, is_approved, approved_by, approved_at) "
                "VALUES (:uid, :cid, 'admin', true, :uid, now())"
            ),
            {"uid": admin_id, "cid": clan_id},
        )
        for pid, name in ((live_person_id, "Live Person"), (deleted_person_id, "Deleted Person")):
            await s.execute(
                sa.text(
                    "INSERT INTO persons "
                    "(id, full_name, gender, is_deleted, created_by_clan_id, created_by) "
                    "VALUES (:id, :name, 'unknown', false, :cid, :actor)"
                ),
                {"id": pid, "name": name, "cid": clan_id, "actor": admin_id},
            )
            await s.execute(
                sa.text(
                    "INSERT INTO clan_memberships (person_id, clan_id, is_founder) "
                    "VALUES (:pid, :cid, false)"
                ),
                {"pid": pid, "cid": clan_id},
            )
        # Soft-delete AFTER seeding + membership — the raw UPDATE the brief
        # calls for, rather than seeding is_deleted=true directly.
        await s.execute(
            sa.text("UPDATE persons SET is_deleted = true WHERE id = :id"),
            {"id": deleted_person_id},
        )
        await s.commit()

    return {
        "clan_id": clan_id,
        "admin_id": admin_id,
        "live_person_id": live_person_id,
        "deleted_person_id": deleted_person_id,
    }


def _actor(admin_id: uuid.UUID) -> ActorInfo:
    return ActorInfo(user_id=admin_id, role="admin")


# ── Upload: connection-hygiene ───────────────────────────────────────────────


async def test_upload_holds_no_connection_during_blob_upload(
    session_factory: async_sessionmaker[AsyncSession],
    seeded: dict[str, uuid.UUID],
) -> None:
    """H5: the storage blob upload is a multi-second external call. It must
    not run while a pooled connection sits idle-in-transaction. RED today:
    `person_in_clan` (a SELECT) autobegins the session's transaction, and
    upload() runs before the commit that would end it, so upload_in_txn
    records [True]."""
    async with session_factory() as session:
        dispatcher = create_event_dispatcher(session)
        uow = SqlAlchemyUnitOfWork(session, dispatcher)
        repo = SqlAlchemyDocumentRepository(uow)
        storage = TxnRecordingStorage(session)
        handler = DocumentCommandHandler(repo, storage, uow)

        await handler.upload(
            file_content=_PNG_BYTES,
            filename="giapha.png",
            content_type="image/png",
            title="Gia phả",
            document_type="certificate",
            clan_id=seeded["clan_id"],
            actor=_actor(seeded["admin_id"]),
            person_id=seeded["live_person_id"],
        )

    assert storage.upload_in_txn == [False]
    # Presign happens after the commit — already released, likely already
    # False today, but pinned here so a future regression is caught too.
    assert storage.presign_in_txn == [False]


async def test_upload_validates_before_uploading(
    session_factory: async_sessionmaker[AsyncSession],
    seeded: dict[str, uuid.UUID],
) -> None:
    """Correctness (expected to PASS today): a body-supplied person_id that
    doesn't resolve to a live membership in the acting clan (here,
    soft-deleted) must raise EntityNotFoundError('person_not_found') BEFORE
    any blob is uploaded — no wasted/orphaned storage write."""
    async with session_factory() as session:
        dispatcher = create_event_dispatcher(session)
        uow = SqlAlchemyUnitOfWork(session, dispatcher)
        repo = SqlAlchemyDocumentRepository(uow)
        storage = TxnRecordingStorage(session)
        handler = DocumentCommandHandler(repo, storage, uow)

        with pytest.raises(EntityNotFoundError) as exc_info:
            await handler.upload(
                file_content=_PNG_BYTES,
                filename="giapha.png",
                content_type="image/png",
                title="Gia phả",
                document_type="certificate",
                clan_id=seeded["clan_id"],
                actor=_actor(seeded["admin_id"]),
                person_id=seeded["deleted_person_id"],
            )

    assert exc_info.value.code == "person_not_found"
    assert storage.uploaded == []


async def test_upload_happy_path_persists_and_returns_presigned(
    session_factory: async_sessionmaker[AsyncSession],
    seeded: dict[str, uuid.UUID],
) -> None:
    """Correctness (expected to PASS today): a live person_id uploads
    successfully — the document row is committed and a presigned URL is
    returned."""
    async with session_factory() as session:
        dispatcher = create_event_dispatcher(session)
        uow = SqlAlchemyUnitOfWork(session, dispatcher)
        repo = SqlAlchemyDocumentRepository(uow)
        storage = TxnRecordingStorage(session)
        handler = DocumentCommandHandler(repo, storage, uow)

        response = await handler.upload(
            file_content=_PNG_BYTES,
            filename="giapha.png",
            content_type="image/png",
            title="Gia phả",
            document_type="certificate",
            clan_id=seeded["clan_id"],
            actor=_actor(seeded["admin_id"]),
            person_id=seeded["live_person_id"],
        )

    assert storage.uploaded == [response.storage_path]
    assert response.presigned_url == f"https://signed.example/{response.storage_path}"

    async with session_factory() as verify_session:
        result = await verify_session.execute(
            sa.text("SELECT title, is_deleted FROM documents WHERE id = :id"),
            {"id": response.id},
        )
        row = result.mappings().one()
    assert row["title"] == "Gia phả"
    assert row["is_deleted"] is False


# ── Export: connection-hygiene ───────────────────────────────────────────────


async def test_export_holds_no_connection_during_presign(
    session_factory: async_sessionmaker[AsyncSession],
    seeded: dict[str, uuid.UUID],
) -> None:
    """H5: the export's manifest presigning loops over every document doing a
    multi-second external call per document. It must not run while a pooled
    connection sits idle-in-transaction. RED today: the port's read queries
    autobegin the session's transaction and it is never committed/closed
    before `_presign_manifest` runs, so presign_in_txn records [True, True]
    for the two seeded documents."""
    clan_id = seeded["clan_id"]
    admin_id = seeded["admin_id"]
    doc_ids = [uuid.uuid4(), uuid.uuid4()]
    async with session_factory() as s:
        for i, doc_id in enumerate(doc_ids):
            await s.execute(
                sa.text(
                    "INSERT INTO documents "
                    "(id, clan_id, title, document_type, storage_path, created_by) "
                    "VALUES (:id, :cid, :title, 'certificate', :path, :actor)"
                ),
                {
                    "id": doc_id,
                    "cid": clan_id,
                    "title": f"Doc {i}",
                    "path": f"clans/{clan_id}/documents/{doc_id}.png",
                    "actor": admin_id,
                },
            )
        await s.commit()

    async with session_factory() as session:
        port = SqlAlchemyExportQueryPort(session)
        storage = TxnRecordingStorage(session)
        handler = ExportQueryHandler(port, storage, build_clan_export, to_json_bytes, build_gedcom)

        filename, media_type, body = await handler.export_clan(clan_id, fmt="json")

    assert storage.presign_in_txn == [False, False]

    import json

    archive = json.loads(body)
    manifest_paths = {m["storage_path"] for m in archive["documents_manifest"]}
    assert manifest_paths == {
        f"clans/{clan_id}/documents/{doc_ids[0]}.png",
        f"clans/{clan_id}/documents/{doc_ids[1]}.png",
    }
    assert all(
        m["download_url"].startswith("https://signed.example/")
        for m in archive["documents_manifest"]
    )
    assert media_type == "application/json"
    assert filename.endswith(".json")


# ── Pool tunability ───────────────────────────────────────────────────────────


def test_pool_settings_are_env_tunable() -> None:
    """H5: the engine's pool size/overflow are hardcoded in
    `app/core/database.py` (`pool_size=10, max_overflow=20`) rather than
    read from Settings. RED today: `app.core.database.make_engine` and
    `Settings.DB_POOL_SIZE`/`DB_MAX_OVERFLOW` don't exist yet (Task 2 adds
    them) — this fails at the import/attribute-access below.

    Pure — builds an engine but never connects, so no live DB is needed;
    QueuePool exposes `.size()` and `._max_overflow` synchronously."""
    from app.core.config import Settings
    from app.core.database import make_engine

    settings = Settings(
        DB_POOL_SIZE=7,
        DB_MAX_OVERFLOW=3,
        DATABASE_URL="postgresql+psycopg://postgres:password@localhost:5432/family_roots",
    )
    engine = make_engine(settings)

    # White-box probe of the (Async)QueuePool: `.size()` is QueuePool-specific and
    # `_max_overflow` is private — neither is on the base `Pool` type mypy infers for
    # `engine.pool`, so ignore attr-defined here rather than weaken the assertion.
    assert engine.pool.size() == 7  # type: ignore[attr-defined]
    assert engine.pool._max_overflow == 3  # type: ignore[attr-defined]
