"""Runtime readiness — is the database schema migrated to head?

A fresh runtime DB with no schema previously surfaced only as per-request 500s
("relation does not exist") and a paused auth provider only as failing requests.
These checks turn misconfiguration into a boot-time signal (fail-fast in
production, a loud warning in dev) and a ``/health`` field, instead of a
mystery to debug one endpoint at a time.
"""

from __future__ import annotations

from functools import lru_cache
from importlib import resources

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# The migration scripts travel *inside* the distribution as the top-level
# ``migrations`` package, so this module finds them by import rather than by
# counting directories upwards from its own file. ``pyproject.toml``'s
# ``[tool.hatch.build.targets.wheel] packages`` is what puts them in the wheel,
# and ``tests/unit/test_wheel_carries_migration_scripts.py`` is what proves it.
#
# S-075: the previous form was ``Path(__file__).resolve().parents[2]``, under a
# comment reading "resolved from the file location, not the CWD, so it works
# however the process is launched". That is true of *launching* and false of
# *installing*. ``backend/Dockerfile`` runs ``uv sync --no-editable``, so in the
# image this module sits at
# ``/app/.venv/lib/python3.14/site-packages/app/core/readiness.py`` and
# ``parents[2]`` is ``site-packages``, which holds no ``migrations`` directory.
# ``expected_head()`` returned ``None``, ``migration_status()`` returned
# ``unknown``, and ``app/main.py`` refused to boot under ``APP_ENV=production``
# however healthy the database was. Measured 2026-08-22 from a built image.
_MIGRATIONS_PACKAGE = "migrations"

MIGRATIONS_CURRENT = "current"
MIGRATIONS_BEHIND = "behind"
MIGRATIONS_UNKNOWN = "unknown"


@lru_cache
def expected_head() -> str | None:
    """Head revision id from the migration scripts (filesystem read, cached).

    ``ScriptDirectory`` only parses the version files — it does not run
    ``env.py`` — so this is safe to call without a database.

    ``alembic.ini`` is deliberately not read here. Its ``[alembic]`` section
    carries only ``script_location``, which this function supplies itself, plus
    options that apply to generating revisions rather than reading them. Not
    reading it removes the last reason for this module to know where the
    project root is."""
    try:
        with resources.as_file(resources.files(_MIGRATIONS_PACKAGE)) as scripts_dir:
            cfg = Config()
            cfg.set_main_option("script_location", str(scripts_dir))
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
