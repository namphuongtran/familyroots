"""Migration 015: version columns + spouse_order partial unique index."""

import os
import re
import uuid
from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

pytestmark = pytest.mark.integration


@pytest.fixture()
def seeded_clan_and_persons(sync_engine: sa.Engine) -> Iterator[tuple[uuid.UUID, ...]]:
    """One clan + three persons + memberships, inserted with raw SQL.

    Mirrors the minimal insert helpers in tests/integration/test_tenant_isolation.py
    (_add_clan / _add_person / _add_membership).
    """
    clan_id = uuid.uuid4()
    p1, p2, p3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    actor = uuid.uuid4()
    with sync_engine.begin() as conn:
        conn.execute(
            sa.text("INSERT INTO clans (id, name, slug, is_active) VALUES (:id, :n, :sl, :a)"),
            {"id": clan_id, "n": f"C{clan_id.hex[:6]}", "sl": f"c-{clan_id.hex[:8]}", "a": True},
        )
        for pid in (p1, p2, p3):
            conn.execute(
                sa.text(
                    "INSERT INTO persons (id, full_name, gender, created_by_clan_id, created_by) "
                    "VALUES (:id, 'P', 'unknown', :cid, :cb)"
                ),
                {"id": pid, "cid": clan_id, "cb": actor},
            )
            conn.execute(
                sa.text("INSERT INTO clan_memberships (person_id, clan_id) VALUES (:p, :c)"),
                {"p": pid, "c": clan_id},
            )
    yield clan_id, p1, p2, p3


def test_version_columns_exist_default_1(sync_engine: sa.Engine) -> None:
    insp = sa.inspect(sync_engine)
    for table in ("persons", "marriages", "parent_child"):
        cols = {c["name"]: c for c in insp.get_columns(table)}
        assert "version" in cols, f"{table}.version missing"
        assert cols["version"]["nullable"] is False
        assert re.fullmatch(r"'?1'?(::integer)?", str(cols["version"]["default"]))


def test_spouse_order_unique_index_blocks_duplicates(
    sync_engine: sa.Engine, seeded_clan_and_persons: tuple[uuid.UUID, ...]
) -> None:
    """Two active marriages of the same person1 with the same spouse_order must
    violate uq_marriages_spouse_order. Divorced rows and soft-deleted rows must NOT
    collide with an active married row at the same spouse_order (the partial index
    predicate is ``WHERE ... AND is_deleted = false AND status = 'married'``)."""
    clan_id, p1, p2, p3 = seeded_clan_and_persons
    ins = sa.text(
        """INSERT INTO marriages
           (id, person1_id, person2_id, created_by_clan_id, status, spouse_order,
            is_deleted, created_by)
           VALUES (:id, :p1, :p2, :clan, :status, :so, :deleted, :actor)"""
    )
    actor = str(uuid.uuid4())
    with sync_engine.begin() as conn:
        conn.execute(
            ins,
            {
                "id": str(uuid.uuid4()),
                "p1": p1,
                "p2": p2,
                "clan": clan_id,
                "status": "married",
                "so": 1,
                "deleted": False,
                "actor": actor,
            },
        )
    with pytest.raises(sa.exc.IntegrityError), sync_engine.begin() as conn:
        conn.execute(
            ins,
            {
                "id": str(uuid.uuid4()),
                "p1": p1,
                "p2": p3,
                "clan": clan_id,
                "status": "married",
                "so": 1,
                "deleted": False,
                "actor": actor,
            },
        )
    # divorced row with same order is allowed
    with sync_engine.begin() as conn:
        conn.execute(
            ins,
            {
                "id": str(uuid.uuid4()),
                "p1": p1,
                "p2": p3,
                "clan": clan_id,
                "status": "divorced",
                "so": 1,
                "deleted": False,
                "actor": actor,
            },
        )
    # soft-deleted married row with same order is allowed (partial index predicate
    # excludes is_deleted = true rows, so it does not collide with the live row above)
    with sync_engine.begin() as conn:
        conn.execute(
            ins,
            {
                "id": str(uuid.uuid4()),
                "p1": p1,
                "p2": p3,
                "clan": clan_id,
                "status": "married",
                "so": 1,
                "deleted": True,
                "actor": actor,
            },
        )


def test_upgrade_fails_on_existing_spouse_order_duplicates(
    migrated_db_url: str,
    sync_engine: sa.Engine,
    seeded_clan_and_persons: tuple[uuid.UUID, ...],
) -> None:
    """015's pre-check must abort the upgrade (RuntimeError listing the offending
    rows) rather than silently create the unique index when existing data already
    violates spouse_order uniqueness for active married rows."""
    clan_id, p1, p2, p3 = seeded_clan_and_persons
    cfg = Config("alembic.ini")
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", migrated_db_url)
    os.environ["DATABASE_URL"] = migrated_db_url

    # Roll back below 015 so marriages has no version column / unique index yet,
    # then plant a pre-existing duplicate the pre-check must catch on re-upgrade.
    command.downgrade(cfg, "014_drop_date_approx")

    dup_id1, dup_id2 = str(uuid.uuid4()), str(uuid.uuid4())
    ins = sa.text(
        """INSERT INTO marriages
           (id, person1_id, person2_id, created_by_clan_id, status, spouse_order,
            is_deleted, created_by)
           VALUES (:id, :p1, :p2, :clan, 'married', 1, false, :actor)"""
    )
    actor = str(uuid.uuid4())
    try:
        with sync_engine.begin() as conn:
            conn.execute(ins, {"id": dup_id1, "p1": p1, "p2": p2, "clan": clan_id, "actor": actor})
            conn.execute(ins, {"id": dup_id2, "p1": p1, "p2": p3, "clan": clan_id, "actor": actor})

        with pytest.raises(RuntimeError, match="spouse_order duplicates"):
            command.upgrade(cfg, "head")
    finally:
        with sync_engine.begin() as conn:
            conn.execute(sa.text("DELETE FROM marriages WHERE id = :id"), {"id": dup_id1})
            conn.execute(sa.text("DELETE FROM marriages WHERE id = :id"), {"id": dup_id2})
        command.upgrade(cfg, "head")
