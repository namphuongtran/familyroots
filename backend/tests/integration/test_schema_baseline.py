"""Schema baseline: the migrated DB must match the ORM models (SP-1)."""

import os

import sqlalchemy as sa
from alembic import command
from alembic.config import Config


def _include_object(object_, name, type_, reflected, compare_to):
    """Mirror of migrations/env.py include_object (kept local to avoid importing
    env.py, which executes Alembic context at module top-level)."""
    return type_ not in ("index", "check_constraint")


def _inspector(engine: sa.Engine) -> sa.Inspector:
    return sa.inspect(engine)


def test_persons_uses_created_by_clan_id(sync_engine: sa.Engine) -> None:
    cols = {c["name"] for c in _inspector(sync_engine).get_columns("persons")}
    assert "created_by_clan_id" in cols
    assert "origin_clan_id" not in cols


def test_identity_claims_uses_reviewer_note(sync_engine: sa.Engine) -> None:
    cols = {c["name"] for c in _inspector(sync_engine).get_columns("identity_claims")}
    assert "reviewer_note" in cols
    assert "reasoning" not in cols


def test_no_enum_types_remain(sync_engine: sa.Engine) -> None:
    with sync_engine.connect() as conn:
        rows = conn.execute(
            sa.text(
                "SELECT typname FROM pg_type WHERE typname IN "
                "('gender_type','document_type','event_type','clan_role','notification_status')"
            )
        ).fetchall()
    assert rows == []


def test_edge_person_fks_are_restrict(sync_engine: sa.Engine) -> None:
    # confdeltype 'r' = RESTRICT in pg_constraint
    with sync_engine.connect() as conn:
        rows = conn.execute(
            sa.text(
                "SELECT c.conname, c.confdeltype "
                "FROM pg_constraint c JOIN pg_class t ON c.conrelid = t.oid "
                "WHERE c.contype = 'f' AND t.relname IN ('marriages','parent_child') "
                "AND c.confrelid = 'persons'::regclass"
            )
        ).fetchall()
    assert len(rows) == 4
    assert all(deltype == "r" for _, deltype in rows), rows


def test_invitation_has_status_and_accepted_by(sync_engine: sa.Engine) -> None:
    cols = {c["name"] for c in _inspector(sync_engine).get_columns("clan_invitations")}
    assert {"status", "accepted_by"} <= cols
    indexes = {i["name"] for i in _inspector(sync_engine).get_indexes("clan_invitations")}
    assert "uq_clan_invitations_pending" in indexes


def test_person_insert_and_select_roundtrip(sync_engine: sa.Engine) -> None:
    """A real INSERT/SELECT on persons proves the app's columns exist."""
    with sync_engine.begin() as conn:
        clan_id = conn.execute(
            sa.text(
                "INSERT INTO clans (name, slug) VALUES ('Test', 'test-clan-roundtrip') RETURNING id"
            )
        ).scalar_one()
        person_id = conn.execute(
            sa.text(
                "INSERT INTO persons (full_name, gender, created_by_clan_id, created_by) "
                "VALUES ('Nguyễn Văn A', 'male', :clan, gen_random_uuid()) RETURNING id"
            ),
            {"clan": clan_id},
        ).scalar_one()
        got = conn.execute(
            sa.text("SELECT full_name FROM persons WHERE id = :id"), {"id": person_id}
        ).scalar_one()
    assert got == "Nguyễn Văn A"


def test_migration_round_trip(migrated_db_url: str) -> None:
    """downgrade base then upgrade head must succeed on the already-migrated DB."""
    cfg = Config("alembic.ini")
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", migrated_db_url)
    os.environ["DATABASE_URL"] = migrated_db_url
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")


def test_autogenerate_has_no_table_or_column_diff(migrated_db_url: str) -> None:
    """After upgrade, autogenerate must not want to add/drop/alter tables or columns."""
    os.environ["DATABASE_URL"] = migrated_db_url

    from alembic.autogenerate import compare_metadata
    from alembic.runtime.migration import MigrationContext

    from app.models.base import Base

    engine = sa.create_engine(migrated_db_url)
    with engine.connect() as conn:
        mc = MigrationContext.configure(
            conn,
            opts={"include_object": _include_object, "compare_type": True},
        )
        diffs = compare_metadata(mc, Base.metadata)
    engine.dispose()

    # Target exactly the drift class that broke the app: missing/renamed tables or
    # columns. Indexes/checks are excluded by _include_object; we deliberately do
    # not gate on modify_* (server-default/type representation noise).
    drift_ops = {"add_table", "remove_table", "add_column", "remove_column"}
    drift = [d for d in diffs if isinstance(d, tuple) and d and d[0] in drift_ops]
    assert drift == [], f"unexpected schema drift: {drift}"
