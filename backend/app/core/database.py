"""Async SQLAlchemy engine and session management.

Single schema — no search_path switching. clan_id isolation is enforced in the
application/repository layer (explicit clan_id filtering on every clan-scoped
read). DB-level RLS is a planned defense-in-depth addition (SP-3C), not yet active.
"""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings, settings

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

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency — yield an async database session."""
    async with AsyncSessionLocal() as session:
        yield session
