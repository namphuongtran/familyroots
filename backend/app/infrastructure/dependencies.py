"""FastAPI dependency providers for DDD infrastructure.

Wires together repositories, UoW, and use-case handlers so that route
handlers receive fully assembled collaborators via ``Depends(…)``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from app.application.auth.handlers import (
        AuthCommandHandler,
        AuthQueryHandler,
        FCMTokenHandler,
        SupabaseAuthService,
    )
    from app.application.branch.handlers import BranchCommandHandler, BranchQueryHandler
    from app.application.clan.handlers import ClanCommandHandler, ClanQueryHandler
    from app.application.document.handlers import DocumentCommandHandler, DocumentQueryHandler
    from app.application.event.handlers import EventCommandHandler, EventQueryHandler
    from app.application.invitation.handlers import InvitationCommandHandler, InvitationQueryHandler
    from app.application.me.handlers import MeQueryHandler
    from app.application.person.claim_handlers import ClaimCommandHandler, ClaimQueryHandler
    from app.application.platform_admin.handlers import (
        PlatformAdminCommandHandler,
        PlatformAdminQueryHandler,
    )
    from app.application.relationship.handlers import MarriageQueryHandler, ParentChildQueryHandler
    from app.application.tree.handlers import TreeQueryHandler

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


def get_unit_of_work(
    db: AsyncSession = Depends(get_db),
) -> SqlAlchemyUnitOfWork:
    """Provide a Unit of Work scoped to the current request."""
    dispatcher = create_event_dispatcher(db)
    return SqlAlchemyUnitOfWork(db, dispatcher)


# ── Person handlers ──────────────────────────────────────────────


def get_person_command_handler(
    db: AsyncSession = Depends(get_db),
) -> PersonCommandHandler:
    dispatcher = create_event_dispatcher(db)
    uow = SqlAlchemyUnitOfWork(db, dispatcher)
    repo = SqlAlchemyPersonRepository(db)
    return PersonCommandHandler(repo, uow)


def get_person_query_handler(
    db: AsyncSession = Depends(get_db),
) -> PersonQueryHandler:
    from app.infrastructure.persistence.person_query_port import SqlAlchemyPersonQueryPort

    repo = SqlAlchemyPersonRepository(db)
    query_port = SqlAlchemyPersonQueryPort(db)
    return PersonQueryHandler(repo, query_port)


# ── Claim handlers ──────────────────────────────────────────────


def get_claim_command_handler(
    db: AsyncSession = Depends(get_db),
) -> ClaimCommandHandler:
    from app.application.person.claim_handlers import ClaimCommandHandler
    from app.infrastructure.event_dispatcher import create_event_dispatcher
    from app.infrastructure.persistence.claim_repository import SqlAlchemyClaimRepository
    from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork

    repo = SqlAlchemyClaimRepository(db)
    dispatcher = create_event_dispatcher(db)
    uow = SqlAlchemyUnitOfWork(db, dispatcher)
    return ClaimCommandHandler(repo, uow)


def get_claim_query_handler(
    db: AsyncSession = Depends(get_db),
) -> ClaimQueryHandler:
    from app.application.person.claim_handlers import ClaimQueryHandler
    from app.infrastructure.persistence.claim_repository import SqlAlchemyClaimQueryPort

    query_port = SqlAlchemyClaimQueryPort(db)
    return ClaimQueryHandler(query_port)


# ── Me handlers ─────────────────────────────────────────────────


def get_me_query_handler(
    db: AsyncSession = Depends(get_db),
) -> MeQueryHandler:
    from app.infrastructure.persistence.me_query_port import SqlAlchemyMeQueryPort

    query_port = SqlAlchemyMeQueryPort(db)
    return MeQueryHandler(query_port)


# ── Platform Admin handlers ──────────────────────────────────────


def get_platform_admin_command_handler(
    db: AsyncSession = Depends(get_db),
) -> PlatformAdminCommandHandler:
    from app.application.platform_admin.handlers import PlatformAdminCommandHandler
    from app.infrastructure.event_dispatcher import create_event_dispatcher
    from app.infrastructure.persistence.clan_repository import SqlAlchemyClanRepository
    from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork

    dispatcher = create_event_dispatcher(db)
    uow = SqlAlchemyUnitOfWork(db, dispatcher)
    repo = SqlAlchemyClanRepository(db)
    return PlatformAdminCommandHandler(repo, uow)


def get_platform_admin_query_handler(
    db: AsyncSession = Depends(get_db),
) -> PlatformAdminQueryHandler:
    from app.application.platform_admin.handlers import PlatformAdminQueryHandler
    from app.infrastructure.persistence.platform_admin_query_port import (
        SqlAlchemyPlatformAdminQueryPort,
    )

    query_port = SqlAlchemyPlatformAdminQueryPort(db)
    return PlatformAdminQueryHandler(query_port)


# ── Auth handlers ───────────────────────────────────────────────


def get_auth_command_handler(
    db: AsyncSession = Depends(get_db),
) -> AuthCommandHandler:
    from app.infrastructure.event_dispatcher import create_event_dispatcher
    from app.infrastructure.persistence.auth_repository import SqlAlchemyAuthRepository
    from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork

    repo = SqlAlchemyAuthRepository(db)
    dispatcher = create_event_dispatcher(db)
    uow = SqlAlchemyUnitOfWork(db, dispatcher)
    return AuthCommandHandler(repo, uow)


def get_auth_query_handler(
    db: AsyncSession = Depends(get_db),
) -> AuthQueryHandler:
    from app.infrastructure.persistence.auth_repository import SqlAlchemyAuthQueryPort

    query_port = SqlAlchemyAuthQueryPort(db)
    return AuthQueryHandler(query_port)


def get_fcm_token_handler(
    db: AsyncSession = Depends(get_db),
) -> FCMTokenHandler:
    from app.infrastructure.persistence.auth_repository import SqlAlchemyFCMTokenRepository

    repo = SqlAlchemyFCMTokenRepository(db)
    return FCMTokenHandler(repo)


def get_supabase_auth_service() -> SupabaseAuthService:
    from app.application.auth.handlers import SupabaseAuthService

    return SupabaseAuthService()


# ── Relationship handlers ───────────────────────────────────────


def _build_relationship_validator(db: AsyncSession) -> RelationshipDomainValidator:
    query_port = SqlAlchemyRelationshipQueryPort(db)
    return RelationshipDomainValidator(query_port)


def get_marriage_command_handler(
    db: AsyncSession = Depends(get_db),
) -> MarriageCommandHandler:
    dispatcher = create_event_dispatcher(db)
    uow = SqlAlchemyUnitOfWork(db, dispatcher)
    repo = SqlAlchemyMarriageRepository(db)
    validator = _build_relationship_validator(db)
    return MarriageCommandHandler(repo, uow, validator)


def get_parent_child_command_handler(
    db: AsyncSession = Depends(get_db),
) -> ParentChildCommandHandler:
    dispatcher = create_event_dispatcher(db)
    uow = SqlAlchemyUnitOfWork(db, dispatcher)
    repo = SqlAlchemyParentChildRepository(db)
    validator = _build_relationship_validator(db)
    return ParentChildCommandHandler(repo, uow, validator)


def get_marriage_query_handler(
    db: AsyncSession = Depends(get_db),
) -> MarriageQueryHandler:
    from app.application.relationship.handlers import MarriageQueryHandler

    repo = SqlAlchemyMarriageRepository(db)
    return MarriageQueryHandler(repo)


def get_parent_child_query_handler(
    db: AsyncSession = Depends(get_db),
) -> ParentChildQueryHandler:
    from app.application.relationship.handlers import ParentChildQueryHandler

    repo = SqlAlchemyParentChildRepository(db)
    return ParentChildQueryHandler(repo)


# ── Clan handlers ────────────────────────────────────────────────


def get_clan_command_handler(
    db: AsyncSession = Depends(get_db),
) -> ClanCommandHandler:
    from app.application.clan.handlers import ClanCommandHandler
    from app.infrastructure.persistence.clan_repository import SqlAlchemyClanRepository

    dispatcher = create_event_dispatcher(db)
    uow = SqlAlchemyUnitOfWork(db, dispatcher)
    repo = SqlAlchemyClanRepository(db)
    return ClanCommandHandler(repo, uow)


def get_clan_query_handler(
    db: AsyncSession = Depends(get_db),
) -> ClanQueryHandler:
    from app.application.clan.handlers import ClanQueryHandler
    from app.infrastructure.persistence.clan_repository import SqlAlchemyClanRepository

    repo = SqlAlchemyClanRepository(db)
    return ClanQueryHandler(repo)


# ── Tree handlers ───────────────────────────────────────────────


def get_tree_query_handler(
    db: AsyncSession = Depends(get_db),
) -> TreeQueryHandler:
    from app.application.tree.handlers import TreeQueryHandler
    from app.infrastructure.persistence.tree_repository import SqlAlchemyTreeRepository

    repo = SqlAlchemyTreeRepository(db)
    return TreeQueryHandler(repo)


# ── Branch handlers ─────────────────────────────────────────────


def get_branch_command_handler(
    db: AsyncSession = Depends(get_db),
) -> BranchCommandHandler:
    from app.application.branch.handlers import BranchCommandHandler
    from app.infrastructure.persistence.branch_repository import SqlAlchemyBranchRepository

    dispatcher = create_event_dispatcher(db)
    uow = SqlAlchemyUnitOfWork(db, dispatcher)
    repo = SqlAlchemyBranchRepository(db)
    return BranchCommandHandler(repo, uow)


def get_branch_query_handler(
    db: AsyncSession = Depends(get_db),
) -> BranchQueryHandler:
    from app.application.branch.handlers import BranchQueryHandler
    from app.infrastructure.persistence.branch_repository import SqlAlchemyBranchRepository

    repo = SqlAlchemyBranchRepository(db)
    return BranchQueryHandler(repo)


# ── Document handlers ───────────────────────────────────────────


def get_document_command_handler(
    db: AsyncSession = Depends(get_db),
) -> DocumentCommandHandler:
    from app.application.document.handlers import DocumentCommandHandler
    from app.infrastructure.persistence.document_repository import SqlAlchemyDocumentRepository
    from app.infrastructure.storage.supabase_adapter import SupabaseStorageAdapter

    dispatcher = create_event_dispatcher(db)
    uow = SqlAlchemyUnitOfWork(db, dispatcher)
    repo = SqlAlchemyDocumentRepository(db)
    storage = SupabaseStorageAdapter()
    return DocumentCommandHandler(repo, storage, uow)


def get_document_query_handler(
    db: AsyncSession = Depends(get_db),
) -> DocumentQueryHandler:
    from app.application.document.handlers import DocumentQueryHandler
    from app.infrastructure.persistence.document_repository import SqlAlchemyDocumentRepository
    from app.infrastructure.storage.supabase_adapter import SupabaseStorageAdapter

    repo = SqlAlchemyDocumentRepository(db)
    storage = SupabaseStorageAdapter()
    return DocumentQueryHandler(repo, storage)


# ── Event handlers ──────────────────────────────────────────────


def get_event_command_handler(
    db: AsyncSession = Depends(get_db),
) -> EventCommandHandler:
    from app.application.event.handlers import EventCommandHandler
    from app.infrastructure.persistence.event_repository import SqlAlchemyEventRepository

    dispatcher = create_event_dispatcher(db)
    uow = SqlAlchemyUnitOfWork(db, dispatcher)
    repo = SqlAlchemyEventRepository(db)
    return EventCommandHandler(repo, uow)


def get_event_query_handler(
    db: AsyncSession = Depends(get_db),
) -> EventQueryHandler:
    from app.application.event.handlers import EventQueryHandler
    from app.infrastructure.persistence.event_repository import SqlAlchemyEventRepository

    repo = SqlAlchemyEventRepository(db)
    return EventQueryHandler(repo)


# ── Invitation handlers ─────────────────────────────────────────


def get_invitation_command_handler(
    db: AsyncSession = Depends(get_db),
) -> InvitationCommandHandler:
    from app.application.invitation.handlers import InvitationCommandHandler
    from app.infrastructure.event_dispatcher import create_event_dispatcher
    from app.infrastructure.persistence.invitation_repository import (
        SqlAlchemyInvitationRepository,
    )
    from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork

    repo = SqlAlchemyInvitationRepository(db)
    uow = SqlAlchemyUnitOfWork(db, create_event_dispatcher(db))
    return InvitationCommandHandler(repo, uow)


def get_invitation_query_handler(
    db: AsyncSession = Depends(get_db),
) -> InvitationQueryHandler:
    from app.application.invitation.handlers import InvitationQueryHandler
    from app.infrastructure.persistence.invitation_repository import (
        SqlAlchemyInvitationRepository,
    )

    return InvitationQueryHandler(SqlAlchemyInvitationRepository(db))
