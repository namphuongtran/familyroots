"""Async SQLAlchemy engine and session management.

Single schema — no search_path switching. clan_id isolation is enforced in the
application/repository layer (explicit clan_id filtering on every clan-scoped
read). DB-level RLS is a planned defense-in-depth addition (SP-3C), not yet active.
"""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

# NOTE: if DATABASE_URL is ever pointed at a transaction-mode connection pooler
# (e.g. Supabase's pgbouncer on :6543), psycopg v3's automatic server-side
# prepared statements break with DuplicatePreparedStatement. In that case add
# connect_args={"prepare_threshold": None}. A direct Postgres (current Render
# setup) does not need it.
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_recycle=300,
    pool_pre_ping=True,
    echo=settings.APP_DEBUG,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency — yield an async database session."""
    async with AsyncSessionLocal() as session:
        yield session
