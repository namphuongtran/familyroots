"""Migration 015: version columns + spouse_order partial unique index."""

import uuid
from collections.abc import Iterator

import pytest
import sqlalchemy as sa

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
        assert "1" in str(cols["version"]["default"])


def test_spouse_order_unique_index_blocks_duplicates(
    sync_engine: sa.Engine, seeded_clan_and_persons: tuple[uuid.UUID, ...]
) -> None:
    """Two active marriages of the same person1 with the same spouse_order must
    violate uq_marriages_spouse_order. Divorced/soft-deleted rows must NOT collide."""
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
