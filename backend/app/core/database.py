"""Async SQLAlchemy engine and session management.

Single schema — no search_path switching. clan_id isolation is handled
by Supabase RLS at the database level and explicit filtering at the
application level.
"""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=10,
    max_overflow=20,
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
