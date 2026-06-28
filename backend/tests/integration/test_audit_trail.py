"""Audit-trail enforcement: branch / event / document writes must emit AuditLog rows.

These contexts emit AuditableEvents on their aggregates but previously never called
uow.track(), so commit() collected nothing and no AuditLog row was written (C9 +
siblings, 2026-06-28 design review). If a future change drops the track() call, the
relevant test here fails — this is the CI enforcement that replaces the implicit,
forgettable contract.
"""

import uuid
from collections.abc import AsyncGenerator
from datetime import date
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.application.branch.handlers import BranchCommandHandler
from app.application.document.handlers import DocumentCommandHandler
from app.application.event.handlers import EventCommandHandler
from app.domain.shared.value_objects import ActorInfo
from app.infrastructure.event_dispatcher import create_event_dispatcher
from app.infrastructure.persistence.branch_repository import SqlAlchemyBranchRepository
from app.infrastructure.persistence.document_repository import SqlAlchemyDocumentRepository
from app.infrastructure.persistence.event_repository import SqlAlchemyEventRepository
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


class _FakeStorage:
    """Minimal StoragePort stand-in (no real Supabase calls)."""

    async def upload(self, path: str, content: bytes, content_type: str | None) -> str:
        return path

    async def get_presigned_url(self, storage_path: str, expires_in: int = 3600) -> str:
        return f"https://example.test/{storage_path}"

    async def delete(self, storage_path: str) -> bool:
        return True


@pytest.fixture()
async def async_engine(migrated_db_url: str) -> AsyncGenerator[AsyncEngine]:
    engine = create_async_engine(migrated_db_url)
    yield engine
    await engine.dispose()


async def _seed_clan(s: AsyncSession, clan_id: uuid.UUID) -> None:
    await s.execute(
        sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, :n, :sl)"),
        {"id": clan_id, "n": f"C{clan_id.hex[:6]}", "sl": f"c-{clan_id.hex[:8]}"},
    )
    await s.commit()


async def _audit_count(s: AsyncSession, clan_id: uuid.UUID, resource_type: str) -> int:
    return (
        await s.execute(
            sa.text("SELECT count(*) FROM audit_logs WHERE clan_id = :c AND resource_type = :rt"),
            {"c": clan_id, "rt": resource_type},
        )
    ).scalar() or 0


def _uow(session: AsyncSession) -> SqlAlchemyUnitOfWork:
    return SqlAlchemyUnitOfWork(session, create_event_dispatcher(session))


async def test_branch_create_writes_audit_log(async_engine: AsyncEngine) -> None:
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    clan_id, actor = uuid.uuid4(), uuid.uuid4()
    async with maker() as s:
        await _seed_clan(s, clan_id)
        handler = BranchCommandHandler(SqlAlchemyBranchRepository(s), _uow(s))
        await handler.create(
            clan_id=clan_id, actor=ActorInfo.from_jwt({"sub": str(actor)}, "editor"), name="Main"
        )
        assert await _audit_count(s, clan_id, "branch") == 1


async def test_event_create_writes_audit_log(async_engine: AsyncEngine) -> None:
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    clan_id, actor = uuid.uuid4(), uuid.uuid4()
    async with maker() as s:
        await _seed_clan(s, clan_id)
        handler = EventCommandHandler(SqlAlchemyEventRepository(s), _uow(s))
        await handler.create(
            clan_id=clan_id,
            actor=ActorInfo.from_jwt({"sub": str(actor)}, "editor"),
            person_id=None,
            event_type="custom",
            title="Reunion",
            description=None,
            event_date=date(2026, 1, 1),
            is_lunar_calendar=False,
            is_recurring=False,
            notify_days_before=None,
        )
        assert await _audit_count(s, clan_id, "event") == 1


async def test_document_upload_writes_audit_log(async_engine: AsyncEngine) -> None:
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    clan_id, actor = uuid.uuid4(), uuid.uuid4()
    async with maker() as s:
        await _seed_clan(s, clan_id)
        handler = DocumentCommandHandler(SqlAlchemyDocumentRepository(s), _FakeStorage(), _uow(s))
        result: Any = await handler.upload(
            file_content=b"x",
            filename="p.jpg",
            content_type="image/jpeg",
            title="Photo",
            document_type="photo",
            clan_id=clan_id,
            actor=ActorInfo.from_jwt({"sub": str(actor)}, "editor"),
        )
        assert result.id is not None
        assert await _audit_count(s, clan_id, "document") == 1
