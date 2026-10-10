"""Async SQLAlchemy engine and session management.

Single schema — no search_path switching. clan_id isolation is enforced in the
application/repository layer (explicit clan_id filtering on every clan-scoped read) as
the PRIMARY guarantee. RLS layer-2 (SP-3, ADR-008) is defense-in-depth: request sessions
(``AsyncRequestSessionLocal``/``RlsSession``) drop to the non-bypass role + set the
``app.clan_id`` GUC per transaction (see ``app/core/rls.py``); system sessions
(``AsyncSessionLocal``) stay privileged and bypass. Phase 1 enforces ``documents``.
"""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.core.config import Settings, settings
from app.core.rls import register_rls_session_events, set_request_clan_id


def make_engine(settings: Settings) -> AsyncEngine:
    """Build the async engine in one of two shapes, chosen by ``DB_EXTERNAL_POOLER``.

    - **False** (default; a direct Postgres or Docker's ``pgdb``): a QueuePool whose size and
      overflow come from ``DB_POOL_SIZE``/``DB_MAX_OVERFLOW`` (ADR-028/H5), defaults 10/20.
    - **True** (behind a transaction pooler — Supabase's Supavisor on :6543, from Vercel
      Functions; ADR-065): ``NullPool``, because the pooler is the pool, and
      ``prepare_threshold=None``, because psycopg 3's automatic server-side prepared
      statements break when consecutive transactions land on different server connections.
      The pool-size settings do not apply. ``Settings.DB_EXTERNAL_POOLER`` carries the full
      reasoning.
    """
    if settings.DB_EXTERNAL_POOLER:
        return create_async_engine(
            settings.DATABASE_URL,
            poolclass=NullPool,
            connect_args={"prepare_threshold": None},
            echo=settings.APP_DEBUG,
        )
    return create_async_engine(
        settings.DATABASE_URL,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_recycle=300,
        pool_pre_ping=True,
        echo=settings.APP_DEBUG,
    )


engine = make_engine(settings)

# SYSTEM sessions (lifespan, scheduler, document-purge) — privileged, no RLS seam, so
# these cross-clan/system writers legitimately bypass RLS (SP-3 Phase 1, ADR-008).
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class RlsSession(Session):
    """Request-path sync Session. A distinct subclass so the RLS ``after_begin`` seam
    (SET LOCAL ROLE + app.clan_id GUC) attaches ONLY to request transactions, never to
    the system ``AsyncSessionLocal``/scheduler sessions (option A — explicit split)."""


register_rls_session_events(RlsSession)

# REQUEST sessions — drop to the non-bypass role + set the clan GUC per transaction.
AsyncRequestSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    sync_session_class=RlsSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI request dependency — an async session whose transactions run under the
    RLS request role (SET LOCAL ROLE + app.clan_id), so DB-level clan isolation applies
    behind the primary application-layer filters."""
    async with AsyncRequestSessionLocal() as session:
        try:
            yield session
        finally:
            # Belt-and-suspenders: each request runs in its own task/context, but clear
            # the clan ContextVar so a stale value can never bleed into a reused context.
            set_request_clan_id(None)


async def get_system_db() -> AsyncIterator[AsyncSession]:
    """Privileged (non-RLS) request dependency for flows that legitimately span clans and
    have no single clan context — identity claims (a claimant resolving a person by global
    id) and platform-admin (cross-clan metrics). Uses the system session (no RLS seam), so
    it bypasses RLS exactly like the scheduler/purge. Only these cross-clan handlers use
    it; every clan-scoped handler uses ``get_db`` (RLS-enforced)."""
    async with AsyncSessionLocal() as session:
        yield session
