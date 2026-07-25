"""H5 — person search must be index-backed, not a full sequential scan.

The prior query filtered/sorted on ``unaccent(lower(full_name))`` while the GIN
trigram index is on ``public.f_unaccent(full_name)`` — a different expression, so
the index was unusable and every clan search did a sequential scan (+ per-row
``similarity()``). birth_name had no trigram index at all.

Two complementary, planner-independent checks:
  1. (DB) With ``enable_seqscan = off``, an isolated predicate on each column's
     ``public.f_unaccent(...)`` expression uses the matching trigram index — proving
     the expression the code now uses is genuinely index-backed (and that migration
     009's birth_name index exists). We isolate the predicate because the full query's
     plan is planner-dependent (the clan join could reach persons by PK either way).
  2. (static) The real search SQL filters/sorts on that same ``public.f_unaccent(...)``
     expression and no longer on the index-defeating ``unaccent(lower(...))`` — this is
     the guard that fails if the query expression regresses.
"""

import uuid
from collections.abc import AsyncGenerator

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.infrastructure.event_dispatcher import create_event_dispatcher
from app.infrastructure.persistence.person_repository import _SEARCH_SQL, SqlAlchemyPersonRepository
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork


def test_trigram_indexes_are_usable_for_search_expression(sync_engine: sa.Engine) -> None:
    """Planner-robust: an EMPTY/unanalyzed persons table makes the planner pick a cheaper
    index (e.g. the keyset btree with a filter) regardless of enable_seqscan, so this
    used to pass only mid-suite. We seed enough rows with a term that ANALYZE sees as rare
    and ANALYZE the table, so the GIN trigram index is genuinely the cheapest path for the
    leading-wildcard ILIKE (the btree keyset index cannot serve `%q%`). Seed rows are
    cleaned up and stats restored in `finally`."""
    checks = [
        ("full_name", "idx_persons_fullname_trgm"),
        ("birth_name", "idx_persons_birthname_trgm"),
    ]
    clan_id, actor = uuid.uuid4(), uuid.uuid4()
    with sync_engine.connect() as conn:
        try:
            conn.execute(
                sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'Trgm', :slug)"),
                {"id": clan_id, "slug": f"trgm-{clan_id.hex[:8]}"},
            )
            # ~400 rows whose names do NOT contain the search term, so ANALYZE learns the
            # term is rare → the GIN trigram lookup is far cheaper than scanning the whole
            # keyset index and filtering.
            conn.execute(
                sa.text(
                    "INSERT INTO persons (id, full_name, birth_name, gender, "
                    "created_by_clan_id, created_by) "
                    "SELECT gen_random_uuid(), 'Person ' || g, 'Birth ' || g, 'unknown', "
                    ":c, :a FROM generate_series(1, 400) AS g"
                ),
                {"c": clan_id, "a": actor},
            )
            conn.commit()
            conn.execute(sa.text("ANALYZE persons"))

            conn.execute(sa.text("SET enable_seqscan = off"))
            for col, index_name in checks:
                rows = conn.execute(
                    sa.text(
                        f"EXPLAIN SELECT p.id FROM persons p WHERE public.f_unaccent(p.{col}) "
                        f"ILIKE '%' || public.f_unaccent(:q) || '%'"
                    ),
                    {"q": "nguyen"},
                ).fetchall()
                plan = "\n".join(r[0] for r in rows)
                assert index_name in plan, (col, plan)
                assert "Seq Scan on persons" not in plan, (col, plan)
        finally:
            conn.rollback()  # drop the SET and any open state
            conn.execute(
                sa.text("DELETE FROM persons WHERE created_by_clan_id = :c"), {"c": clan_id}
            )
            conn.execute(sa.text("DELETE FROM clans WHERE id = :c"), {"c": clan_id})
            conn.commit()
            conn.execute(sa.text("ANALYZE persons"))  # restore stats to the empty table


def test_search_sql_uses_the_indexed_expression() -> None:
    assert "public.f_unaccent(p.full_name)" in _SEARCH_SQL
    assert "public.f_unaccent(p.birth_name)" in _SEARCH_SQL
    # the pre-fix, index-defeating expression must not reappear
    assert "lower(" not in _SEARCH_SQL


@pytest.fixture()
async def async_engine(migrated_db_url: str) -> AsyncGenerator[AsyncEngine]:
    engine = create_async_engine(migrated_db_url)
    yield engine
    await engine.dispose()


@pytest.mark.asyncio
async def test_search_is_accent_folding_and_case_insensitive(async_engine: AsyncEngine) -> None:
    """Functional check that the index-aligned query still returns the right rows:
    an unaccented, differently-cased term matches accented names on both full_name
    and birth_name (the semantics that must survive dropping ``unaccent(lower(...))``)."""
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    clan_id, actor = uuid.uuid4(), uuid.uuid4()
    p_full, p_birth = uuid.uuid4(), uuid.uuid4()
    try:
        async with maker() as s:
            await s.execute(
                sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'S', :slug)"),
                {"id": clan_id, "slug": f"srch-{clan_id.hex[:8]}"},
            )
            # accented full_name; accented birth_name on a second person
            await s.execute(
                sa.text(
                    "INSERT INTO persons (id, full_name, gender, created_by_clan_id, created_by) "
                    "VALUES (:id, 'José Ramírez', 'male', :c, :a)"
                ),
                {"id": p_full, "c": clan_id, "a": actor},
            )
            await s.execute(
                sa.text(
                    "INSERT INTO persons (id, full_name, birth_name, gender, "
                    "created_by_clan_id, created_by) "
                    "VALUES (:id, 'Maria', 'Bích', 'female', :c, :a)"
                ),
                {"id": p_birth, "c": clan_id, "a": actor},
            )
            for pid in (p_full, p_birth):
                await s.execute(
                    sa.text("INSERT INTO clan_memberships (person_id, clan_id) VALUES (:p, :c)"),
                    {"p": pid, "c": clan_id},
                )
            await s.commit()

            repo = SqlAlchemyPersonRepository(SqlAlchemyUnitOfWork(s, create_event_dispatcher(s)))
            # unaccented + lowercase query matches the accented, capitalised full_name
            by_full = await repo.search(clan_id, "jose ramirez")
            assert p_full in {r.id for r in by_full}
            # uppercase, unaccented query matches the accented birth_name
            by_birth = await repo.search(clan_id, "BICH")
            assert p_birth in {r.id for r in by_birth}
    finally:
        async with maker() as s:
            await s.execute(
                sa.text("DELETE FROM clan_memberships WHERE clan_id = :c"), {"c": clan_id}
            )
            await s.execute(
                sa.text("DELETE FROM persons WHERE created_by_clan_id = :c"), {"c": clan_id}
            )
            await s.execute(sa.text("DELETE FROM clans WHERE id = :c"), {"c": clan_id})
            await s.commit()
