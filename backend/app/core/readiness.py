"""Runtime readiness — is the database schema migrated to this code's head?

A fresh runtime DB with no schema previously surfaced only as per-request 500s
("relation does not exist") and a paused auth provider only as failing requests.
These checks turn misconfiguration into a boot-time signal (fail-fast in
production, a loud warning in dev) and a ``/health`` field, instead of a
mystery to debug one endpoint at a time.
"""

from __future__ import annotations

from dataclasses import dataclass
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
# The previous form was ``Path(__file__).resolve().parents[2]``, under a
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
MIGRATIONS_AHEAD = "ahead"
MIGRATIONS_UNKNOWN = "unknown"

# The statuses a deployment boots and serves under (ADR-070). ``ahead`` is the previous
# deployment during a release: ``release.yml`` migrates before the new deployment goes live,
# and every migration keeps the code already live working (``docs/ops/migrations.md``).
MIGRATIONS_SERVABLE = frozenset({MIGRATIONS_CURRENT, MIGRATIONS_AHEAD})


@dataclass(frozen=True)
class _Scripts:
    head: str
    revisions: frozenset[str]


@lru_cache
def _read_scripts() -> _Scripts | None:
    """Head and every revision id from the migration scripts (filesystem read, cached).

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
            scripts = ScriptDirectory.from_config(cfg)
            head = scripts.get_current_head()
            if head is None:
                return None
            revisions = frozenset(script.revision for script in scripts.walk_revisions())
            return _Scripts(head=head, revisions=revisions)
    except Exception:
        return None


def expected_head() -> str | None:
    """Head revision id from the migration scripts, or ``None`` when they are unreadable."""
    scripts = _read_scripts()
    return None if scripts is None else scripts.head


@dataclass(frozen=True)
class MigrationReading:
    """A status, and the two revisions it was decided from."""

    status: str
    # ``alembic_version.version_num``. ``None`` when the table is missing or empty, or when the
    # scripts could not be read and the database was not asked.
    database: str | None
    # The scripts' head. ``None`` when they could not be read.
    head: str | None


async def read_migrations(db: AsyncSession) -> MigrationReading:
    """Place the DB's ``alembic_version`` against this code's own migration scripts.

    - ``current``: it is the scripts' head.
    - ``behind``: it is a revision the scripts know but not their head, or there is
      none. A missing ``alembic_version`` table means the DB was never migrated.
    - ``ahead``: it is a revision the scripts do not know. Code cannot see a
      migration written after it, so "a revision I don't know" is the whole test,
      and a revision that never reached ``main`` reads the same way. Production
      migrates only from tags ADR-067's ``verify-ref`` traced to ``main`` (ADR-070).
    - ``unknown``: the scripts are unreadable."""
    scripts = _read_scripts()
    if scripts is None:
        return MigrationReading(status=MIGRATIONS_UNKNOWN, database=None, head=None)
    try:
        result = await db.execute(text("SELECT version_num FROM alembic_version"))
        database = result.scalar()
    except Exception:
        # Aborted transaction state must not leak into the caller's session.
        await db.rollback()
        return MigrationReading(status=MIGRATIONS_BEHIND, database=None, head=scripts.head)
    if database == scripts.head:
        status = MIGRATIONS_CURRENT
    elif database is None or database in scripts.revisions:
        status = MIGRATIONS_BEHIND
    else:
        status = MIGRATIONS_AHEAD
    return MigrationReading(status=status, database=database, head=scripts.head)


async def migration_status(db: AsyncSession) -> str:
    """``current`` | ``behind`` | ``ahead`` | ``unknown``, as ``read_migrations`` decides them."""
    return (await read_migrations(db)).status
