"""Alembic environment configuration — single schema.

No multi-schema complexity. Alembic manages the public schema only.
Clan isolation is enforced in the application/repository layer; RLS is a planned
defense-in-depth addition (not yet active).
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

import app.models  # noqa: F401 — registers all ORM tables on Base.metadata
from app.core.config import settings
from app.models.base import Base

config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL.replace("+asyncpg", ""))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def include_object(object_, name, type_, reflected, compare_to):
    """Limit autogenerate to tables/columns/FKs/unique constraints.

    Indexes (incl. expression/partial/trigram), check constraints, and the
    f_unaccent function are maintained as raw SQL in the baseline migration and
    are not reliably round-tripped by autogenerate, so we exclude them from the
    diff. This keeps the autogen-diff regression test meaningful.
    """
    return type_ not in ("index", "check_constraint")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
