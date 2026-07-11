"""Migration 012: date precision/display columns are backfilled from `approx` (SP-1).

Real-DB test: downgrade the already-migrated head (see ``migrated_db_url`` fixture
in tests/integration/conftest.py, mirroring test_schema_baseline.py /
test_path_tiebreak.py) to just before 012, seed rows via raw SQL (precision/display
columns don't exist yet at that revision), then re-upgrade to head and assert the
migration's CASE backfill produced the expected precision per the brief:
  - person birth/death: `approx=true` + date -> 'circa'; date present, no approx ->
    'exact'; date NULL -> 'unknown'.
  - events: event_date is NOT NULL -> always 'exact'.
  - marriages: marriage_date/divorce_date nullable -> 'exact' when present else
    'unknown'.
"""

import os
import uuid
from datetime import date

import sqlalchemy as sa
from alembic import command
from alembic.config import Config

_PRE_REVISION = "011_path_tiebreak"


def _downgrade_to_pre_012(db_url: str) -> None:
    cfg = Config("alembic.ini")
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", db_url)
    os.environ["DATABASE_URL"] = db_url
    command.downgrade(cfg, _PRE_REVISION)


def _upgrade_to_head(db_url: str) -> None:
    cfg = Config("alembic.ini")
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", db_url)
    os.environ["DATABASE_URL"] = db_url
    command.upgrade(cfg, "head")


def _clan(conn: sa.Connection) -> uuid.UUID:
    clan_id = uuid.uuid4()
    conn.execute(
        sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'Test', :slug)"),
        {"id": clan_id, "slug": f"c-{clan_id.hex[:8]}"},
    )
    return clan_id


def _person(
    conn: sa.Connection,
    clan_id: uuid.UUID,
    *,
    birth_date: date | None,
    birth_date_approx: bool,
    death_date: date | None,
    death_date_approx: bool,
) -> uuid.UUID:
    person_id = uuid.uuid4()
    conn.execute(
        sa.text(
            "INSERT INTO persons "
            "(id, full_name, gender, created_by_clan_id, created_by, "
            "birth_date, birth_date_approx, death_date, death_date_approx) "
            "VALUES (:id, 'P', 'male', :clan, gen_random_uuid(), "
            ":bd, :bda, :dd, :dda)"
        ),
        {
            "id": person_id,
            "clan": clan_id,
            "bd": birth_date,
            "bda": birth_date_approx,
            "dd": death_date,
            "dda": death_date_approx,
        },
    )
    return person_id


def test_backfill_precision_from_approx_and_dates(migrated_db_url: str) -> None:
    _downgrade_to_pre_012(migrated_db_url)

    engine = sa.create_engine(migrated_db_url)
    try:
        with engine.begin() as conn:
            clan_id = _clan(conn)

            circa_id = _person(
                conn,
                clan_id,
                birth_date=date(1950, 1, 1),
                birth_date_approx=True,
                death_date=None,
                death_date_approx=False,
            )
            exact_id = _person(
                conn,
                clan_id,
                birth_date=date(1960, 5, 1),
                birth_date_approx=False,
                death_date=date(2020, 1, 1),
                death_date_approx=False,
            )
            unknown_id = _person(
                conn,
                clan_id,
                birth_date=None,
                birth_date_approx=False,
                death_date=None,
                death_date_approx=False,
            )

            event_id = conn.execute(
                sa.text(
                    "INSERT INTO events "
                    "(clan_id, person_id, event_type, title, event_date, created_by) "
                    "VALUES (:clan, :person, 'birthday', 'T', :d, gen_random_uuid()) "
                    "RETURNING id"
                ),
                {"clan": clan_id, "person": exact_id, "d": date(2000, 1, 1)},
            ).scalar_one()

            married_id = conn.execute(
                sa.text(
                    "INSERT INTO marriages "
                    "(person1_id, person2_id, created_by_clan_id, created_by, marriage_date) "
                    "VALUES (:p1, :p2, :clan, gen_random_uuid(), :md) RETURNING id"
                ),
                {"p1": circa_id, "p2": exact_id, "clan": clan_id, "md": date(1975, 6, 1)},
            ).scalar_one()
            unmarried_dates_id = conn.execute(
                sa.text(
                    "INSERT INTO marriages "
                    "(person1_id, person2_id, created_by_clan_id, created_by) "
                    "VALUES (:p1, :p2, :clan, gen_random_uuid()) RETURNING id"
                ),
                {"p1": circa_id, "p2": unknown_id, "clan": clan_id},
            ).scalar_one()
    finally:
        engine.dispose()

    _upgrade_to_head(migrated_db_url)

    engine = sa.create_engine(migrated_db_url)
    try:
        with engine.connect() as conn:
            persons = {
                r.id: r
                for r in conn.execute(
                    sa.text(
                        "SELECT id, birth_date_precision, death_date_precision FROM persons "
                        "WHERE id IN (:a, :b, :c)"
                    ),
                    {"a": circa_id, "b": exact_id, "c": unknown_id},
                )
            }
            event_precision = conn.execute(
                sa.text("SELECT event_date_precision FROM events WHERE id = :id"),
                {"id": event_id},
            ).scalar_one()
            marriages = {
                r.id: r
                for r in conn.execute(
                    sa.text(
                        "SELECT id, marriage_date_precision, divorce_date_precision "
                        "FROM marriages WHERE id IN (:a, :b)"
                    ),
                    {"a": married_id, "b": unmarried_dates_id},
                )
            }
    finally:
        engine.dispose()

    assert persons[circa_id].birth_date_precision == "circa"
    assert persons[circa_id].death_date_precision == "unknown"
    assert persons[exact_id].birth_date_precision == "exact"
    assert persons[exact_id].death_date_precision == "exact"
    assert persons[unknown_id].birth_date_precision == "unknown"
    assert persons[unknown_id].death_date_precision == "unknown"

    assert event_precision == "exact"

    assert marriages[married_id].marriage_date_precision == "exact"
    assert marriages[married_id].divorce_date_precision == "unknown"
    assert marriages[unmarried_dates_id].marriage_date_precision == "unknown"
    assert marriages[unmarried_dates_id].divorce_date_precision == "unknown"


def test_new_columns_present_at_head(sync_engine: sa.Engine) -> None:
    insp = sa.inspect(sync_engine)
    person_cols = {c["name"] for c in insp.get_columns("persons")}
    event_cols = {c["name"] for c in insp.get_columns("events")}
    marriage_cols = {c["name"] for c in insp.get_columns("marriages")}

    assert {
        "birth_date_precision",
        "birth_date_display",
        "death_date_precision",
        "death_date_display",
    } <= person_cols
    assert {"event_date_precision", "event_date_display"} <= event_cols
    assert {
        "marriage_date_precision",
        "marriage_date_display",
        "divorce_date_precision",
        "divorce_date_display",
    } <= marriage_cols
