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

from app.core.config import Settings, settings
from app.core.rls import register_rls_session_events, set_request_clan_id

# NOTE: if DATABASE_URL is ever pointed at a transaction-mode connection pooler
# (e.g. Supabase's pgbouncer on :6543), psycopg v3's automatic server-side
# prepared statements break with DuplicatePreparedStatement. In that case add
# connect_args={"prepare_threshold": None}. A direct Postgres (current Render
# setup) does not need it.


def make_engine(settings: Settings) -> AsyncEngine:
    """Build the async engine, sourcing pool size/overflow from Settings
    (ADR-028/H5) so they are env-tunable. Defaults (10/20) match the
    previous hardcoded values, so out-of-box behavior is unchanged."""
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
