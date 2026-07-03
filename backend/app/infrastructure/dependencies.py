"""FastAPI dependency providers — the composition root.

Wires repositories, query ports, Unit of Work, and use-case handlers so that
route handlers receive fully assembled collaborators via ``Depends(…)``.

All imports are module-level (there is no circular dependency: the application
layer depends only on the domain, and nothing imports this module back). Each
provider only *wires* collaborators — no per-function imports. This keeps one
consistent pattern and makes a missing import a load-time ImportError caught by
tests, never a runtime ``NameError`` on the request path.
"""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.auth.handlers import (
    AuthCommandHandler,
    AuthQueryHandler,
    AuthSessionService,
    FCMTokenHandler,
)
from app.application.branch.handlers import BranchCommandHandler, BranchQueryHandler
from app.application.clan.handlers import ClanCommandHandler, ClanQueryHandler
from app.application.document.handlers import DocumentCommandHandler, DocumentQueryHandler
from app.application.event.handlers import EventCommandHandler, EventQueryHandler
from app.application.invitation.handlers import InvitationCommandHandler, InvitationQueryHandler
from app.application.me.handlers import MeQueryHandler
from app.application.person.claim_handlers import ClaimCommandHandler, ClaimQueryHandler
from app.application.person.handlers import PersonCommandHandler, PersonQueryHandler
from app.application.platform_admin.handlers import (
    PlatformAdminCommandHandler,
    PlatformAdminQueryHandler,
)
from app.application.relationship.handlers import (
    MarriageCommandHandler,
    MarriageQueryHandler,
    ParentChildCommandHandler,
    ParentChildQueryHandler,
)
from app.application.tree.handlers import TreeQueryHandler
from app.core.database import get_db
from app.domain.relationship.validator import RelationshipDomainValidator
from app.infrastructure.event_dispatcher import create_event_dispatcher
from app.infrastructure.persistence.auth_repository import (
    SqlAlchemyAuthQueryPort,
    SqlAlchemyAuthRepository,
    SqlAlchemyFCMTokenRepository,
)
from app.infrastructure.persistence.branch_repository import SqlAlchemyBranchRepository
from app.infrastructure.persistence.claim_repository import (
    SqlAlchemyClaimQueryPort,
    SqlAlchemyClaimRepository,
)
from app.infrastructure.persistence.clan_repository import SqlAlchemyClanRepository
from app.infrastructure.persistence.document_repository import SqlAlchemyDocumentRepository
from app.infrastructure.persistence.event_repository import SqlAlchemyEventRepository
from app.infrastructure.persistence.invitation_repository import SqlAlchemyInvitationRepository
from app.infrastructure.persistence.me_query_port import SqlAlchemyMeQueryPort
from app.infrastructure.persistence.person_query_port import SqlAlchemyPersonQueryPort
from app.infrastructure.persistence.person_repository import SqlAlchemyPersonRepository
from app.infrastructure.persistence.platform_admin_query_port import (
    SqlAlchemyPlatformAdminQueryPort,
)
from app.infrastructure.persistence.relationship_repository import (
    SqlAlchemyMarriageRepository,
    SqlAlchemyParentChildRepository,
    SqlAlchemyRelationshipQueryPort,
)
from app.infrastructure.persistence.tree_repository import SqlAlchemyTreeRepository
from app.infrastructure.storage.supabase_adapter import SupabaseStorageAdapter
from app.infrastructure.supabase_identity_provider import SupabaseIdentityProvider
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork


def get_unit_of_work(db: AsyncSession = Depends(get_db)) -> SqlAlchemyUnitOfWork:
    """Provide a Unit of Work scoped to the current request."""
    return SqlAlchemyUnitOfWork(db, create_event_dispatcher(db))


def _repo_uow(db: AsyncSession) -> SqlAlchemyUnitOfWork:
    """A UoW wrapping the request session, for repos used in read-only handlers
    (reads go through uow.session; no commit is issued)."""
    return SqlAlchemyUnitOfWork(db, create_event_dispatcher(db))


# ── Person handlers ──────────────────────────────────────────────


def get_person_command_handler(db: AsyncSession = Depends(get_db)) -> PersonCommandHandler:
    uow = SqlAlchemyUnitOfWork(db, create_event_dispatcher(db))
    return PersonCommandHandler(SqlAlchemyPersonRepository(uow), uow)


def get_person_query_handler(db: AsyncSession = Depends(get_db)) -> PersonQueryHandler:
    repo = SqlAlchemyPersonRepository(_repo_uow(db))
    return PersonQueryHandler(repo, SqlAlchemyPersonQueryPort(db))


# ── Claim handlers ──────────────────────────────────────────────


def get_claim_command_handler(db: AsyncSession = Depends(get_db)) -> ClaimCommandHandler:
    uow = SqlAlchemyUnitOfWork(db, create_event_dispatcher(db))
    return ClaimCommandHandler(SqlAlchemyClaimRepository(db), uow)


def get_claim_query_handler(db: AsyncSession = Depends(get_db)) -> ClaimQueryHandler:
    return ClaimQueryHandler(SqlAlchemyClaimQueryPort(db))


# ── Me handlers ─────────────────────────────────────────────────


def get_me_query_handler(db: AsyncSession = Depends(get_db)) -> MeQueryHandler:
    return MeQueryHandler(SqlAlchemyMeQueryPort(db))


# ── Platform Admin handlers ──────────────────────────────────────


def get_platform_admin_command_handler(
    db: AsyncSession = Depends(get_db),
) -> PlatformAdminCommandHandler:
    uow = SqlAlchemyUnitOfWork(db, create_event_dispatcher(db))
    return PlatformAdminCommandHandler(SqlAlchemyClanRepository(db), uow)


def get_platform_admin_query_handler(
    db: AsyncSession = Depends(get_db),
) -> PlatformAdminQueryHandler:
    return PlatformAdminQueryHandler(SqlAlchemyPlatformAdminQueryPort(db))


# ── Auth handlers ───────────────────────────────────────────────


def get_auth_command_handler(db: AsyncSession = Depends(get_db)) -> AuthCommandHandler:
    uow = SqlAlchemyUnitOfWork(db, create_event_dispatcher(db))
    return AuthCommandHandler(
        SqlAlchemyAuthRepository(db),
        uow,
        SupabaseIdentityProvider(),
        SqlAlchemyAuthQueryPort(db),
    )


def get_auth_query_handler(db: AsyncSession = Depends(get_db)) -> AuthQueryHandler:
    return AuthQueryHandler(SqlAlchemyAuthQueryPort(db))


def get_fcm_token_handler(db: AsyncSession = Depends(get_db)) -> FCMTokenHandler:
    return FCMTokenHandler(SqlAlchemyFCMTokenRepository(db))


def get_auth_session_service() -> AuthSessionService:
    return AuthSessionService(SupabaseIdentityProvider())


# ── Relationship handlers ───────────────────────────────────────


def _build_relationship_validator(db: AsyncSession) -> RelationshipDomainValidator:
    return RelationshipDomainValidator(SqlAlchemyRelationshipQueryPort(db))


def get_marriage_command_handler(db: AsyncSession = Depends(get_db)) -> MarriageCommandHandler:
    uow = SqlAlchemyUnitOfWork(db, create_event_dispatcher(db))
    repo = SqlAlchemyMarriageRepository(uow)
    return MarriageCommandHandler(repo, uow, _build_relationship_validator(db))


def get_parent_child_command_handler(
    db: AsyncSession = Depends(get_db),
) -> ParentChildCommandHandler:
    uow = SqlAlchemyUnitOfWork(db, create_event_dispatcher(db))
    repo = SqlAlchemyParentChildRepository(uow)
    return ParentChildCommandHandler(repo, uow, _build_relationship_validator(db))


def get_marriage_query_handler(db: AsyncSession = Depends(get_db)) -> MarriageQueryHandler:
    return MarriageQueryHandler(SqlAlchemyMarriageRepository(_repo_uow(db)))


def get_parent_child_query_handler(
    db: AsyncSession = Depends(get_db),
) -> ParentChildQueryHandler:
    return ParentChildQueryHandler(SqlAlchemyParentChildRepository(_repo_uow(db)))


# ── Clan handlers ────────────────────────────────────────────────


def get_clan_command_handler(db: AsyncSession = Depends(get_db)) -> ClanCommandHandler:
    uow = SqlAlchemyUnitOfWork(db, create_event_dispatcher(db))
    return ClanCommandHandler(SqlAlchemyClanRepository(db), uow)


def get_clan_query_handler(db: AsyncSession = Depends(get_db)) -> ClanQueryHandler:
    return ClanQueryHandler(SqlAlchemyClanRepository(db))


# ── Tree handlers ───────────────────────────────────────────────


def get_tree_query_handler(db: AsyncSession = Depends(get_db)) -> TreeQueryHandler:
    return TreeQueryHandler(SqlAlchemyTreeRepository(db))


# ── Branch handlers ─────────────────────────────────────────────


def get_branch_command_handler(db: AsyncSession = Depends(get_db)) -> BranchCommandHandler:
    uow = SqlAlchemyUnitOfWork(db, create_event_dispatcher(db))
    return BranchCommandHandler(SqlAlchemyBranchRepository(uow), uow)


def get_branch_query_handler(db: AsyncSession = Depends(get_db)) -> BranchQueryHandler:
    return BranchQueryHandler(SqlAlchemyBranchRepository(_repo_uow(db)))


# ── Document handlers ───────────────────────────────────────────


def get_document_command_handler(db: AsyncSession = Depends(get_db)) -> DocumentCommandHandler:
    uow = SqlAlchemyUnitOfWork(db, create_event_dispatcher(db))
    return DocumentCommandHandler(SqlAlchemyDocumentRepository(uow), SupabaseStorageAdapter(), uow)


def get_document_query_handler(db: AsyncSession = Depends(get_db)) -> DocumentQueryHandler:
    repo = SqlAlchemyDocumentRepository(_repo_uow(db))
    return DocumentQueryHandler(repo, SupabaseStorageAdapter())


# ── Event handlers ──────────────────────────────────────────────


def get_event_command_handler(db: AsyncSession = Depends(get_db)) -> EventCommandHandler:
    uow = SqlAlchemyUnitOfWork(db, create_event_dispatcher(db))
    return EventCommandHandler(SqlAlchemyEventRepository(uow), uow)


def get_event_query_handler(db: AsyncSession = Depends(get_db)) -> EventQueryHandler:
    return EventQueryHandler(SqlAlchemyEventRepository(_repo_uow(db)))


# ── Invitation handlers ─────────────────────────────────────────


def get_invitation_command_handler(
    db: AsyncSession = Depends(get_db),
) -> InvitationCommandHandler:
    uow = SqlAlchemyUnitOfWork(db, create_event_dispatcher(db))
    return InvitationCommandHandler(SqlAlchemyInvitationRepository(db), uow)


def get_invitation_query_handler(db: AsyncSession = Depends(get_db)) -> InvitationQueryHandler:
    return InvitationQueryHandler(SqlAlchemyInvitationRepository(db))
