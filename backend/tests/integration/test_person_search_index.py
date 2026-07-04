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

import sqlalchemy as sa

from app.infrastructure.persistence.person_repository import _SEARCH_SQL


def test_trigram_indexes_are_usable_for_search_expression(sync_engine: sa.Engine) -> None:
    checks = [
        ("full_name", "idx_persons_fullname_trgm"),
        ("birth_name", "idx_persons_birthname_trgm"),
    ]
    with sync_engine.connect() as conn:
        conn.execute(sa.text("SET enable_seqscan = off"))
        for col, index_name in checks:
            rows = conn.execute(
                sa.text(
                    f"EXPLAIN SELECT p.id FROM persons p "
                    f"WHERE public.f_unaccent(p.{col}) ILIKE '%' || public.f_unaccent(:q) || '%'"
                ),
                {"q": "nguyen"},
            ).fetchall()
            plan = "\n".join(r[0] for r in rows)
            assert index_name in plan, (col, plan)
            assert "Seq Scan on persons" not in plan, (col, plan)


def test_search_sql_uses_the_indexed_expression() -> None:
    assert "public.f_unaccent(p.full_name)" in _SEARCH_SQL
    assert "public.f_unaccent(p.birth_name)" in _SEARCH_SQL
    # the pre-fix, index-defeating expression must not reappear
    assert "lower(" not in _SEARCH_SQL
