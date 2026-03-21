"""FastAPI dependency providers for DDD infrastructure.

Wires together repositories, UoW, and use-case handlers so that route
handlers receive fully assembled collaborators via ``Depends(…)``.
"""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.person.handlers import PersonCommandHandler, PersonQueryHandler
from app.application.relationship.handlers import MarriageCommandHandler, ParentChildCommandHandler
from app.core.database import get_db
from app.domain.relationship.validator import RelationshipDomainValidator
from app.infrastructure.event_dispatcher import create_event_dispatcher
from app.infrastructure.persistence.person_repository import SqlAlchemyPersonRepository
from app.infrastructure.persistence.relationship_repository import (
    SqlAlchemyMarriageRepository,
    SqlAlchemyParentChildRepository,
    SqlAlchemyRelationshipQueryPort,
)
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork


async def get_unit_of_work(
    db: AsyncSession = Depends(get_db),
) -> SqlAlchemyUnitOfWork:
    """Provide a Unit of Work scoped to the current request."""
    dispatcher = create_event_dispatcher(db)
    return SqlAlchemyUnitOfWork(db, dispatcher)


# ── Person handlers ──────────────────────────────────────────────


async def get_person_command_handler(
    db: AsyncSession = Depends(get_db),
) -> PersonCommandHandler:
    dispatcher = create_event_dispatcher(db)
    uow = SqlAlchemyUnitOfWork(db, dispatcher)
    repo = SqlAlchemyPersonRepository(db)
    return PersonCommandHandler(repo, uow)


async def get_person_query_handler(
    db: AsyncSession = Depends(get_db),
) -> PersonQueryHandler:
    repo = SqlAlchemyPersonRepository(db)
    return PersonQueryHandler(repo)


# ── Relationship handlers ───────────────────────────────────────


def _build_relationship_validator(db: AsyncSession) -> RelationshipDomainValidator:
    query_port = SqlAlchemyRelationshipQueryPort(db)
    return RelationshipDomainValidator(query_port)


async def get_marriage_command_handler(
    db: AsyncSession = Depends(get_db),
) -> MarriageCommandHandler:
    dispatcher = create_event_dispatcher(db)
    uow = SqlAlchemyUnitOfWork(db, dispatcher)
    repo = SqlAlchemyMarriageRepository(db)
    validator = _build_relationship_validator(db)
    return MarriageCommandHandler(repo, uow, validator)


async def get_parent_child_command_handler(
    db: AsyncSession = Depends(get_db),
) -> ParentChildCommandHandler:
    dispatcher = create_event_dispatcher(db)
    uow = SqlAlchemyUnitOfWork(db, dispatcher)
    repo = SqlAlchemyParentChildRepository(db)
    validator = _build_relationship_validator(db)
    return ParentChildCommandHandler(repo, uow, validator)


# ── Clan handlers ────────────────────────────────────────────────


async def get_clan_command_handler(
    db: AsyncSession = Depends(get_db),
) -> "ClanCommandHandler":
    from app.application.clan.handlers import ClanCommandHandler
    from app.infrastructure.persistence.clan_repository import SqlAlchemyClanRepository

    dispatcher = create_event_dispatcher(db)
    uow = SqlAlchemyUnitOfWork(db, dispatcher)
    repo = SqlAlchemyClanRepository(db)
    return ClanCommandHandler(repo, uow)


# ── Tree handlers ───────────────────────────────────────────────


async def get_tree_query_handler(
    db: AsyncSession = Depends(get_db),
) -> "TreeQueryHandler":
    from app.application.tree.handlers import TreeQueryHandler
    from app.infrastructure.persistence.tree_repository import SqlAlchemyTreeRepository

    repo = SqlAlchemyTreeRepository(db)
    return TreeQueryHandler(repo)


# ── Branch handlers ─────────────────────────────────────────────


async def get_branch_command_handler(
    db: AsyncSession = Depends(get_db),
) -> "BranchCommandHandler":
    from app.application.branch.handlers import BranchCommandHandler
    from app.infrastructure.persistence.branch_repository import SqlAlchemyBranchRepository

    dispatcher = create_event_dispatcher(db)
    uow = SqlAlchemyUnitOfWork(db, dispatcher)
    repo = SqlAlchemyBranchRepository(db)
    return BranchCommandHandler(repo, uow)


async def get_branch_query_handler(
    db: AsyncSession = Depends(get_db),
) -> "BranchQueryHandler":
    from app.application.branch.handlers import BranchQueryHandler
    from app.infrastructure.persistence.branch_repository import SqlAlchemyBranchRepository

    repo = SqlAlchemyBranchRepository(db)
    return BranchQueryHandler(repo)


# ── Document handlers ───────────────────────────────────────────


async def get_document_command_handler(
    db: AsyncSession = Depends(get_db),
) -> "DocumentCommandHandler":
    from app.application.document.handlers import DocumentCommandHandler
    from app.infrastructure.persistence.document_repository import SqlAlchemyDocumentRepository
    from app.infrastructure.storage.supabase_adapter import SupabaseStorageAdapter

    dispatcher = create_event_dispatcher(db)
    uow = SqlAlchemyUnitOfWork(db, dispatcher)
    repo = SqlAlchemyDocumentRepository(db)
    storage = SupabaseStorageAdapter()
    return DocumentCommandHandler(repo, storage, uow)


async def get_document_query_handler(
    db: AsyncSession = Depends(get_db),
) -> "DocumentQueryHandler":
    from app.application.document.handlers import DocumentQueryHandler
    from app.infrastructure.persistence.document_repository import SqlAlchemyDocumentRepository
    from app.infrastructure.storage.supabase_adapter import SupabaseStorageAdapter

    repo = SqlAlchemyDocumentRepository(db)
    storage = SupabaseStorageAdapter()
    return DocumentQueryHandler(repo, storage)


# ── Event handlers ──────────────────────────────────────────────


async def get_event_command_handler(
    db: AsyncSession = Depends(get_db),
) -> "EventCommandHandler":
    from app.application.event.handlers import EventCommandHandler
    from app.infrastructure.persistence.event_repository import SqlAlchemyEventRepository

    dispatcher = create_event_dispatcher(db)
    uow = SqlAlchemyUnitOfWork(db, dispatcher)
    repo = SqlAlchemyEventRepository(db)
    return EventCommandHandler(repo, uow)


async def get_event_query_handler(
    db: AsyncSession = Depends(get_db),
) -> "EventQueryHandler":
    from app.application.event.handlers import EventQueryHandler
    from app.infrastructure.persistence.event_repository import SqlAlchemyEventRepository

    repo = SqlAlchemyEventRepository(db)
    return EventQueryHandler(repo)
