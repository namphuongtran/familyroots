"""Schema baseline: the migrated DB must match the ORM models (SP-1)."""

import os
from typing import Any

import sqlalchemy as sa
from alembic import command
from alembic.config import Config


def _include_object(object_, name, type_, reflected, compare_to):
    """Mirror of migrations/env.py include_object (kept local to avoid importing
    env.py, which executes Alembic context at module top-level)."""
    return type_ not in ("index", "check_constraint")


# The drift classes that silently ship model/DB divergence: missing/renamed tables or
# columns, foreign keys, unique/other table constraints, and nullability. Indexes and
# CHECK constraints are excluded by _include_object; modify_type / modify_default are
# deliberately NOT gated (SQLAlchemy renders those with representation noise — varchar
# length, server_default text — that isn't real drift). Note: type drift is therefore
# intentionally uncovered.
_DRIFT_OPS = {
    "add_table",
    "remove_table",
    "add_column",
    "remove_column",
    "add_fk",
    "remove_fk",
    "add_constraint",
    "remove_constraint",
    "modify_nullable",
}


def _drift(diffs: list[Any]) -> list[Any]:
    """Filter compare_metadata() output to the gated drift ops.

    compare_metadata yields table/fk/constraint ops as flat tuples but COLUMN-level
    modifications (modify_nullable/type/default) wrapped in a per-column LIST — so we
    must flatten first, or every modify_* diff is silently skipped (a tuple-only
    filter makes the nullability gate dead code)."""
    flat = [x for d in diffs for x in (d if isinstance(d, list) else [d])]
    return [d for d in flat if isinstance(d, tuple) and d and d[0] in _DRIFT_OPS]


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


def test_clan_fks_are_restrict(sync_engine: sa.Engine) -> None:
    """M10: every clan-owned FK is RESTRICT; persons/audit_logs stay SET NULL.

    The schema-drift gate does not compare FK ``ondelete`` rules, so this pins the
    clan-delete policy directly against pg_constraint. Asserting the exact partition
    also forces any FUTURE clan-referencing table to make a conscious RESTRICT-vs-
    SET-NULL choice here rather than silently defaulting.
    """
    with sync_engine.connect() as conn:
        rows = conn.execute(
            sa.text(
                "SELECT t.relname, c.confdeltype "
                "FROM pg_constraint c JOIN pg_class t ON c.conrelid = t.oid "
                "WHERE c.contype = 'f' AND c.confrelid = 'clans'::regclass"
            )
        ).fetchall()
    by_table: dict[str, str] = {row[0]: row[1] for row in rows}

    restrict = {
        "change_requests",
        "clan_settings",
        "marriages",
        "user_clan_roles",
        "clan_invitations",
        "branches",
        "clan_memberships",
        "notification_log",
        "parent_child",
        "documents",
        "events",
    }
    set_null = {"persons", "audit_logs"}  # de-provenanced / retained, not destroyed

    # every clan-referencing table is accounted for — a new one forces a decision
    assert set(by_table) == restrict | set_null, by_table
    for t in restrict:
        assert by_table[t] == "r", f"{t} clan FK must be RESTRICT, got {by_table[t]!r}"
    for t in set_null:
        assert by_table[t] == "n", f"{t} clan FK must be SET NULL, got {by_table[t]!r}"


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

    assert _drift(diffs) == [], f"unexpected schema drift: {_drift(diffs)}"


def test_drift_filter_flattens_column_level_diffs() -> None:
    """Negative control for the gate itself: column-level modifications arrive
    list-wrapped, so a tuple-only filter would skip them. Guards against anyone
    "simplifying" _drift back to `d for d in diffs` and silently disabling the
    nullability/type gate."""
    # shape compare_metadata actually returns for a single nullability change
    diffs = [
        [("modify_nullable", None, "persons", "nationality", {}, True, False)],
        ("add_table", object()),  # a flat tuple, for good measure
    ]
    caught = _drift(diffs)
    assert any(d[0] == "modify_nullable" for d in caught), caught
    assert any(d[0] == "add_table" for d in caught), caught
