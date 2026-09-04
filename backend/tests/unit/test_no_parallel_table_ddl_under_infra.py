"""Fail when a second, unexecuted set of schema or security DDL appears under `infra/`.

**The module name is narrower than what this file asserts, and the name is kept on purpose.**
Prose in two files names the module: `docs/ops/migrations.md:222,240` and
`test_migrations_doc_matches_alembic.py:40`. Renaming the module would strand both. A
rename is worth doing when whoever owns those files is next in them.

**One of those pointers was wrong, and it is corrected here on 2026-08-26.** This
docstring said `docs/ops/migrations.md:187`. Read at source, line 187 of
`migrations.md` is prose about a package being neither importable nor installed, and it
did not name this module. A line number into a file that grows at the top is the wrong
anchor for a section.

## Part 1 — table DDL (2026-08-22)

`infra/supabase/migrations/` held a hand-written mirror of the baseline schema: four SQL files,
1045 lines, maintained by hand beside the Alembic chain. Nothing ran it and no check read it.
`backend/tests/integration/test_schema_baseline.py` compares the ORM to Alembic;
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

## Part 2 — policy DDL (2026-08-22)

**Part 1's guard was not wide enough, and the file it let through was the more dangerous one.**
`infra/supabase/rls_policies.sql` survived it because it declared no table. It declared 20
policies — 19 on 9 `public` tables and one on `storage.objects` — plus 3 helper functions in
the `auth` schema. Part 1's own docstring recorded it as "a separate, unreviewed liability".
A later review deleted it and widened this guard so the next one cannot land.

**Why a policy file is worse than a table file, measured 2026-08-22 on a fresh `alembic upgrade
head` (Postgres 18, 20 policies over 13 RLS-enabled tables).** A table file fails loudly: you
cannot `CREATE TABLE persons` twice. A policy file **composes**. Every policy Postgres creates
without `AS RESTRICTIVE` is PERMISSIVE, and permissive policies for the same command and role
are **OR**'d. So applying a second policy set does not replace the shipped one — it *widens* it,
silently, and the widest clause wins.

That was not hypothetical for the deleted file:

- Applied to plain Postgres it stopped at statement 1, `ERROR: schema "auth" does not exist`.
  That is what made it look harmless.
- Given a stub `auth.uid()` — which a real Supabase project supplies for free — 31 of its 32
  statements applied cleanly on top of the shipped set, taking `public` from 20 policies to 39.
  It stopped only at the last statement, on `storage`, which Supabase also supplies.
- The added `persons_insert_editor_above` carried `WITH CHECK (auth.user_clan_role() IN
  ('admin','editor'))` and **no clan predicate at all**, alongside the shipped `persons_ins`
  and its `WITH CHECK (created_by_clan_id = current_setting('app.clan_id'))`. Both PERMISSIVE,
  both `{public}`, both INSERT. A user approved `editor` in clan A only, on a session whose
  `app.clan_id` was clan A, inserted a row owned by clan B and it was accepted. Dropping that
  one policy and repeating the identical insert produced `ERROR: new row violates row-level
  security policy for table "persons"`.

It also contradicted an accepted decision at its root. ADR-008 § 2 (`docs/decisions/
008-rls-defense-in-depth.md:304-308`) chooses app-specific GUCs "not `request.jwt.claims`/
`auth.uid()` which require Supabase's `auth` schema", and ADR-047 re-affirms that half of § 2
as shipped. Every policy in the deleted file keyed on `auth.uid()`.

## What these guards assert, and why neither is a check on a file name

A test that asserted "`infra/supabase/rls_policies.sql` does not exist" would pin the path, not
the property. The properties are that **no table DDL** and **no RLS or policy DDL** live outside
the Alembic chain, so both sweeps read every `.sql` file under `infra/` and match on the
statement. A new `infra/supabase/schema.sql` or `infra/anything/hardening.sql` is caught the
same way the deleted files would be.

## The asymmetry these two guards leave behind (2026-08-22)

**Both sweeps above watch a directory where SQL never ran.** Everything under `infra/` is
inert: nothing in the tree reads it and no workflow applies it, which is exactly why the two
deletions could remove two files from it without changing any behaviour. The one place SQL
genuinely executes is `scripts/` — `scripts/restore_drill.sh:149` feeds
`scripts/restore_bootstrap_role.sql` to `psql` against a live database — and no check here
reads it. That finding was written down rather than widening these sweeps, because widening
them would have closed two seeds in one change.

`test_scripts_sql_is_sanctioned.py` closes it, and it could not be this file's rule applied to
a second directory: `restore_bootstrap_role.sql` **is** DDL and must stay, so that guard
allow-lists files by name with the DDL classes their ADR sanctions, defaults every other class
to deny, and forbids privilege escalation in any file regardless of the allow-list. Read its
docstring before adding anything to either guard.

## On detector fragility

A scanner that silently matches nothing would go green forever. Six parametrised tests below
drive `_creates_a_table` and `_declares_policy_ddl` against synthetic SQL, so each one's ability
both to match and to refuse is pinned independently of what `infra/` currently holds, and a
seventh asserts the sweep actually reaches files rather than an empty list.

Note: `.github/workflows/backend-ci.yml` was given an `infra/**` path filter in the same commit
as Part 1. Without it these tests could not run on a pull request that only touched `infra/`,
which is the one change they exist to catch.
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

# `CREATE POLICY`, `CREATE OR REPLACE POLICY`, `ALTER POLICY`, `DROP POLICY`, and any
# `ALTER TABLE … {ENABLE|DISABLE|FORCE|NO FORCE} ROW LEVEL SECURITY`. Matching the DROP and
# DISABLE forms too is deliberate: a file under `infra/` that *removes* a shipped policy is at
# least as dangerous as one that adds a wide one, and nothing else in the tree would catch it.
_POLICY_DDL = re.compile(
    r"\b(?:CREATE\s+(?:OR\s+REPLACE\s+)?POLICY|ALTER\s+POLICY|DROP\s+POLICY"
    r"|ROW\s+LEVEL\s+SECURITY)\b",
    re.IGNORECASE,
)

_LINE_COMMENT = re.compile(r"--[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def _strip_comments(sql: str) -> str:
    """Remove `--` line comments and `/* */` block comments.

    Without this, a commented-out example would be read as real DDL. `infra/supabase/seed.sql`
    is entirely comments, so the guards would fail on it the moment anyone pasted a `CREATE
    TABLE` or a `CREATE POLICY` into the example block.
    """
    return _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("", sql))


def _creates_a_table(sql: str) -> bool:
    return _CREATE_TABLE.search(_strip_comments(sql)) is not None


def _declares_policy_ddl(sql: str) -> bool:
    return _POLICY_DDL.search(_strip_comments(sql)) is not None


def _sql_files_under_infra() -> list[Path]:
    return sorted(_INFRA_ROOT.rglob("*.sql"))


def test_no_sql_file_under_infra_creates_a_table() -> None:
    offenders = [p for p in _sql_files_under_infra() if _creates_a_table(p.read_text())]
    assert offenders == [], (
        "These files under infra/ declare table DDL: "
        + ", ".join(str(p.relative_to(_REPO_ROOT)) for p in offenders)
        + ". The Alembic chain in backend/migrations/ is the only source of truth for the "
        "schema (docs/ops/migrations.md). A second copy that nothing executes drifts silently; "
        "infra/supabase/migrations/ was deleted for exactly that reason. Put the "
        "DDL in a new Alembic revision instead."
    )


def test_no_sql_file_under_infra_declares_rls_or_policy_ddl() -> None:
    offenders = [p for p in _sql_files_under_infra() if _declares_policy_ddl(p.read_text())]
    assert offenders == [], (
        "These files under infra/ declare RLS or policy DDL: "
        + ", ".join(str(p.relative_to(_REPO_ROOT)) for p in offenders)
        + ". The Alembic chain in backend/migrations/ is the only source of truth for the "
        "policy set (ADR-008, ADR-043). A policy file is worse than a table file, because "
        "policies COMPOSE: permissive policies for the same command and role are OR'd, so a "
        "second set does not replace the shipped one, it widens it. infra/supabase/"
        "rls_policies.sql was deleted after a clan-A editor used one of its "
        "clan-blind WITH CHECK clauses to insert a clan-B row. Put the policy in a new Alembic "
        "revision, key it on current_setting('app.clan_id') per ADR-008 section 2, and prove "
        "it two-sided at the database layer in tests/integration/test_rls_activation.py."
    )


def test_the_infra_sweep_actually_reaches_files() -> None:
    """A glob that returns nothing would make the guards above vacuously green forever."""
    assert _INFRA_ROOT.is_dir(), f"{_INFRA_ROOT} is missing; the guards above cannot mean anything"
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


@pytest.mark.parametrize(
    "sql",
    [
        # The two shapes the deleted file actually used, verbatim in form.
        'CREATE POLICY "documents_select_own_clan" ON public.documents\n'
        "  FOR SELECT USING (auth.user_belongs_to_clan(clan_id));",
        "ALTER TABLE public.persons ENABLE ROW LEVEL SECURITY;",
        # Case and whitespace must not be an escape hatch.
        "alter   table  public.events   enable   row   level   security ;",
        "CREATE OR REPLACE POLICY p ON t FOR ALL USING (true);",
        # Removing or weakening a shipped policy is caught too.
        "DROP POLICY persons_ins ON public.persons;",
        "ALTER POLICY persons_sel ON public.persons USING (true);",
        "ALTER TABLE public.persons DISABLE ROW LEVEL SECURITY;",
        "ALTER TABLE public.persons FORCE ROW LEVEL SECURITY;",
        # Mixed with harmless statements.
        "GRANT SELECT ON public.persons TO familyroots_app;\n"
        "CREATE POLICY p ON public.persons FOR SELECT USING (true);",
    ],
)
def test_the_policy_detector_finds_policy_ddl_it_is_given(sql: str) -> None:
    assert _declares_policy_ddl(sql)


@pytest.mark.parametrize(
    "sql",
    [
        '-- CREATE POLICY "p" ON public.persons FOR SELECT USING (true);',
        "/* ALTER TABLE public.persons ENABLE ROW LEVEL SECURITY; */",
        "CREATE TABLE public.persons (id UUID PRIMARY KEY);",
        "INSERT INTO public.clans (id) VALUES ('...');",
        "GRANT SELECT ON public.persons TO familyroots_app;",
        # A column merely *named* like the thing must not trip it.
        "SELECT security_level, policy_name FROM public.settings;",
        "",
    ],
)
def test_the_policy_detector_refuses_sql_that_declares_no_policy(sql: str) -> None:
    assert not _declares_policy_ddl(sql)
