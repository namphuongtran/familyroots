"""Fail when a second, unexecuted set of table DDL appears under `infra/`.

Seed S-064. `infra/supabase/migrations/` held a hand-written mirror of the baseline schema:
four SQL files, 1045 lines, maintained by hand beside the Alembic chain. Nothing ran it and no
check read it. `backend/tests/integration/test_schema_baseline.py` compares the ORM to Alembic;
`test_migrations_doc_matches_alembic.py` compares `docs/ops/migrations.md` to Alembic. Neither
opens a file under `infra/`.

**What it had drifted into, measured 2026-08-22** by applying both sets to the same Postgres 18
server and diffing `information_schema`: 27 columns present at Alembic head and absent there,
8 columns present only there, one extra table (`user_devices`), and tree-traversal functions
with no clan predicate — `003_path_finder.sql` declared `p_clan_id` on line 11 and never used
it, and `002_tree_functions.sql` never mentioned `created_by_clan_id`. Two of its 8 extra
columns were `persons.origin_clan_id` and `identity_claims.reasoning`, the pre-rename names
that `tests/integration/test_schema_baseline.py:51-60` asserts must **not** exist. Bootstrapping
from it produced the schema that file was written to forbid. The set was deleted rather than
regenerated: a parallel copy that nothing executes earns its keep only if something checks it,
and Alembic is already the source of truth by written decision (`docs/ops/migrations.md`).

**What this guard asserts, and why it is not a check on a file name.** A test that asserted
"`infra/supabase/migrations/` does not exist" would pin the path, not the property. The property
is that no table DDL lives outside the Alembic chain, so this reads every `.sql` file under
`infra/` and fails on any `CREATE TABLE`. A new `infra/supabase/schema.sql` fails it just as the
old directory would. `infra/supabase/rls_policies.sql` survives deletion and does not trip this
guard, because it creates no table — it is a separate, unreviewed liability and `infra/README.md`
records what is known about it.

**On detector fragility.** A scanner that silently matches nothing would go green forever. Two
tests below drive `_creates_a_table` against synthetic SQL, so its ability both to match and to
refuse is pinned independently of what `infra/` currently holds, and a third asserts the sweep
actually reaches files rather than an empty list.

Note: `.github/workflows/backend-ci.yml` was given an `infra/**` path filter in the same commit.
Without it this test could not run on a pull request that only touched `infra/`, which is the
one change it exists to catch.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = _BACKEND_ROOT.parent
_INFRA_ROOT = _REPO_ROOT / "infra"

# `CREATE TABLE`, `CREATE TABLE IF NOT EXISTS`, `CREATE UNLOGGED TABLE`, and so on.
_CREATE_TABLE = re.compile(r"\bCREATE\s+(?:\w+\s+)*TABLE\b", re.IGNORECASE)
_LINE_COMMENT = re.compile(r"--[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def _strip_comments(sql: str) -> str:
    """Remove `--` line comments and `/* */` block comments.

    Without this, a commented-out example would be read as real DDL. `infra/supabase/seed.sql`
    is entirely comments, so the guard would fail on it the moment anyone pasted a `CREATE
    TABLE` into the example block.
    """
    return _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("", sql))


def _creates_a_table(sql: str) -> bool:
    return _CREATE_TABLE.search(_strip_comments(sql)) is not None


def _sql_files_under_infra() -> list[Path]:
    return sorted(_INFRA_ROOT.rglob("*.sql"))


def test_no_sql_file_under_infra_creates_a_table() -> None:
    offenders = [p for p in _sql_files_under_infra() if _creates_a_table(p.read_text())]
    assert offenders == [], (
        "These files under infra/ declare table DDL: "
        + ", ".join(str(p.relative_to(_REPO_ROOT)) for p in offenders)
        + ". The Alembic chain in backend/migrations/ is the only source of truth for the "
        "schema (docs/ops/migrations.md). A second copy that nothing executes drifts silently; "
        "infra/supabase/migrations/ was deleted by seed S-064 for exactly that reason. Put the "
        "DDL in a new Alembic revision instead."
    )


def test_the_infra_sweep_actually_reaches_files() -> None:
    """A glob that returns nothing would make the guard above vacuously green forever."""
    assert _INFRA_ROOT.is_dir(), f"{_INFRA_ROOT} is missing; the guard above cannot mean anything"
    assert _sql_files_under_infra(), (
        f"No .sql file found under {_INFRA_ROOT}. If that is now correct, delete this test "
        "rather than leaving a sweep that can never fail."
    )


@pytest.mark.parametrize(
    "sql",
    [
        "CREATE TABLE public.persons (id UUID PRIMARY KEY);",
        "create table if not exists public.x (id int);",
        "CREATE UNLOGGED TABLE scratch (id int);",
        "ALTER TABLE x ADD COLUMN y int;\nCREATE TABLE z (id int);",
    ],
)
def test_the_detector_finds_table_ddl_it_is_given(sql: str) -> None:
    assert _creates_a_table(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "-- CREATE TABLE public.persons (id UUID);",
        "/* CREATE TABLE public.persons (id UUID); */",
        "ALTER TABLE public.persons ENABLE ROW LEVEL SECURITY;",
        'CREATE POLICY "p" ON public.persons FOR SELECT USING (true);',
        "INSERT INTO public.clans (id) VALUES ('...');",
        "",
    ],
)
def test_the_detector_refuses_sql_that_creates_no_table(sql: str) -> None:
    assert not _creates_a_table(sql)
