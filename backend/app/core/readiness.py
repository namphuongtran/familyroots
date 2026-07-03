"""Runtime readiness — is the database schema migrated to head?

A fresh runtime DB with no schema previously surfaced only as per-request 500s
("relation does not exist") and a paused auth provider only as failing requests.
These checks turn misconfiguration into a boot-time signal (fail-fast in
production, a loud warning in dev) and a ``/health`` field, instead of a
mystery to debug one endpoint at a time.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# backend/ (this file lives at backend/app/core/readiness.py). Resolved from the
# file location, not the CWD, so it works however the process is launched.
_BACKEND_DIR = Path(__file__).resolve().parents[2]

MIGRATIONS_CURRENT = "current"
MIGRATIONS_BEHIND = "behind"
MIGRATIONS_UNKNOWN = "unknown"


@lru_cache
def expected_head() -> str | None:
    """Head revision id from the migration scripts (filesystem read, cached).

    ``ScriptDirectory`` only parses the version files — it does not run
    ``env.py`` — so this is safe to call without a database."""
    try:
        cfg = Config(str(_BACKEND_DIR / "alembic.ini"))
        cfg.set_main_option("script_location", str(_BACKEND_DIR / "migrations"))
        return ScriptDirectory.from_config(cfg).get_current_head()
    except Exception:
        return None


async def migration_status(db: AsyncSession) -> str:
    """Compare the DB's ``alembic_version`` against the scripts' head.

    Returns ``current`` | ``behind`` | ``unknown`` (scripts unreadable). A missing
    ``alembic_version`` table means the DB was never migrated → ``behind``."""
    head = expected_head()
    if head is None:
        return MIGRATIONS_UNKNOWN
    try:
        result = await db.execute(text("SELECT version_num FROM alembic_version"))
        current = result.scalar()
    except Exception:
        # Aborted transaction state must not leak into the caller's session.
        await db.rollback()
        return MIGRATIONS_BEHIND
    return MIGRATIONS_CURRENT if current == head else MIGRATIONS_BEHIND
