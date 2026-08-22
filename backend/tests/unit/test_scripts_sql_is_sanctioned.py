"""Fail when a `.sql` file under a `scripts/` directory declares DDL no decision sanctions.

## Why this guard exists, and why it is not the `infra/` one widened (seed S-069, 2026-08-22)

`test_no_parallel_table_ddl_under_infra.py` carries two sweeps, and **both watch a directory
where SQL never ran.** Everything under `infra/` is inert: nothing in the tree reads it, no
workflow applies it, and S-064 and S-067 deleted the two files that lived there precisely
because nothing executed them.

**The one place SQL genuinely executes is `scripts/.`** Verified 2026-08-22 by reading the
tree: `git ls-files '*.sql'` returns exactly two paths, `infra/supabase/seed.sql` and
`scripts/restore_bootstrap_role.sql`, and the only line anywhere that feeds a `.sql` file to a
database client is `scripts/restore_drill.sh:111`, which sets
`BOOTSTRAP_SQL="${SCRIPT_DIR}/restore_bootstrap_role.sql"` and runs it at `:149`:

    psql "$SCRATCH_DSN" -q -v ON_ERROR_STOP=1 -f "$BOOTSTRAP_SQL"

**Nothing is wrong in `scripts/` today.** Measured 2026-08-22, `restore_bootstrap_role.sql`
declares nine statements: one `CREATE ROLE` at `:38` and eight grant statements at
`:44,45,46-47,50,51,52,53`. It declares no table and no policy. That is exactly what ADR-052
decided it should declare. **The gap this guard closes is that nothing would notice if it
changed.**

## The rule, and why it is shaped this way

A guard over `scripts/` **cannot simply forbid DDL**, because `restore_bootstrap_role.sql`
*is* DDL and must stay. Three checks, and they are deliberately not the same question:

1. **Every `.sql` file under a scripts root must be named in `_SANCTIONED`.** An unlisted file
   fails whatever it contains. This is a sweep over the directory tree, not a check on a known
   path, so a file added at any depth under any name is caught.

2. **A named file may declare only the DDL classes its decision sanctioned.**
   `restore_bootstrap_role.sql` is sanctioned for `role` and `grant`, and for nothing else, so
   a `CREATE TABLE` or a `CREATE POLICY` added inside it fails. **Being on the allow-list is
   not a blank cheque.**

3. **No file under a scripts root may confer a privilege that defeats the isolation model**,
   sanctioned or not: the role attributes `SUPERUSER`, `BYPASSRLS`, `CREATEROLE`, `CREATEDB`,
   `REPLICATION`, a grantee of `PUBLIC`, or `WITH GRANT OPTION`. This one is **not
   overridable** by `_SANCTIONED`, and it is the check that makes the allow-list safe at all.
   `ALTER ROLE familyroots_app BYPASSRLS` is class `role`, which check 2 sanctions in that
   file, and it would switch off row-level security for every request the application makes.
   The file's own comment at `:34` states the decision this check enforces: "NOBYPASSRLS is
   the default, which is the point of it."

## The classifier defaults to deny, which is the whole design

`_classify` does **not** hunt for a list of forbidden statements. It finds every DDL or
privilege anchor in the file and asks what class each one is. A statement it has no class for
is class **`unknown`**, and `unknown` is never in any sanctioned set. So `CREATE INDEX`,
`CREATE EXTENSION`, `CREATE FUNCTION`, `DROP DATABASE`, `DROP OWNED`, `COMMENT ON`, and
anything else nobody thought of fail by default rather than pass by omission. A guard written
the other way round — detect table DDL, detect policy DDL, allow the rest — is the rule that
makes today's tree pass with the least thought, and it would admit every statement in that
list.

## What this guard does not catch, stated so nobody reads it as wider than it is

- **Inline SQL in a shell script is invisible to it.** It reads `.sql` files only.
  `scripts/restore_drill.sh` itself runs `DROP DATABASE ... WITH (FORCE)` at `:116` and
  `CREATE DATABASE` at `:122` through `psql -c`, and this guard sees neither. That is the
  largest hole. Closing it means deciding how to scan shell heredocs and `-c` arguments
  without drowning in false positives, which is a second decision and therefore a second seed.
  **That seed is S-077 and it landed on 2026-08-22**: `test_inline_sql_in_scripts_is_sanctioned
  .py` extracts what a `psql` invocation executes and reuses `_classify`, `_strip_comments`
  and `_ESCALATIONS` from this module, so a statement gets the same verdict inline as it does
  in a `.sql` file. This paragraph still describes **this** guard correctly: it reads `.sql`
  files, and it is still blind to inline SQL on its own.
- **It classifies by verb, not by meaning.** Widening `GRANT SELECT` to `GRANT ALL` stays
  class `grant` and passes. What catches that is the drill's own check 4, which drops to the
  request role and counts rows two-sided (ADR-052 § 3), plus the instruction at
  `restore_bootstrap_role.sql:22-23` that a migration changing the role's privileges must
  change that file in the same pull request.
- **`_decision` is checked to exist and to name the file, not to sanction the classes.** The
  test below requires the cited ADR to contain the file's path, so the citation is
  load-bearing rather than a path that merely resolves. It does **not** and cannot check that
  the ADR's prose agrees the file may declare `role` and `grant`. A human read ADR-052 § 1 on
  2026-08-22 and it does.
- **It does not know whether a file is executed.** A new sanctioned `.sql` that nothing runs
  would pass every check here. `infra/` is the directory that failure mode belongs to, and the
  other guard owns it.
- **Scope is `scripts/` and `backend/scripts/`.** `backend/scripts/` holds no `.sql` today
  (only `check.sh`) and is swept anyway, because it is the scripts directory most likely to
  gain one. A `.sql` file dropped anywhere else in the tree is seen by neither guard.

Note: `.github/workflows/backend-ci.yml` was given a `scripts/**` path filter in the same
commit as this file. Without it, a pull request that only touched `scripts/` would run no
backend gate at all, which is the one change this guard exists to catch — the same omission
the `infra/**` filter fixed for the other guard.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple

import pytest

pytestmark = pytest.mark.unit

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = _BACKEND_ROOT.parent

# Repo-root `scripts/` is where SQL actually runs. `backend/scripts/` holds only `check.sh`
# today and is swept because it is the next most likely place for a `.sql` file to appear.
_SCRIPT_ROOTS = (_REPO_ROOT / "scripts", _BACKEND_ROOT / "scripts")


class _Sanction(NamedTuple):
    """What one `.sql` file under a scripts root is permitted to declare, and who said so."""

    classes: frozenset[str]
    decision: str
    why: str


# Keyed by path relative to the repository root. Moving a sanctioned file changes its key and
# fails check 1, which is intended: where the file sits decides what runs it.
_SANCTIONED: dict[str, _Sanction] = {
    "scripts/restore_bootstrap_role.sql": _Sanction(
        classes=frozenset({"role", "grant"}),
        decision="docs/decisions/052-restore-bootstraps-the-request-role.md",
        why=(
            "A Postgres role is a cluster object and a GRANT is a database object, so a "
            "single-database dump taken with --no-owner --no-privileges carries neither. "
            "ADR-052 section 1 puts the role and its seven grants in this one file, run by "
            "scripts/restore_drill.sh:149 after pg_restore. Role and grant DDL are the only "
            "classes the Alembic chain cannot carry across a restore, which is the whole "
            "reason this file is allowed to exist; every other class belongs in a migration."
        ),
    ),
}

_LINE_COMMENT = re.compile(r"--[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)

# Every place a statement creates, changes, removes, or hands out a privilege. Each hit is
# classified below; a hit no class claims is `unknown`, and `unknown` is never sanctioned.
# `COMMENT ON`, `SECURITY LABEL`, and `REFRESH MATERIALIZED` are spelled out rather than
# anchored on their first word, so the bare word SECURITY in `ROW LEVEL SECURITY` does not
# raise a second, spurious anchor inside a statement already classified as `policy`.
_DDL_ANCHOR = re.compile(
    r"\b(?:CREATE|ALTER|DROP|TRUNCATE|GRANT|REVOKE|REASSIGN"
    r"|COMMENT\s+ON|SECURITY\s+LABEL|REFRESH\s+MATERIALIZED)\b",
    re.IGNORECASE,
)

# How much text after an anchor is handed to the class patterns. Only the `policy` pattern
# reads more than a few words, and its gap is `[^;]` so it can never run into the next
# statement and mis-classify it.
_LOOKAHEAD = 240

_CLASSES: tuple[tuple[str, re.Pattern[str]], ...] = (
    # `policy` is tried before `table`, because ALTER TABLE ... ROW LEVEL SECURITY is a policy
    # statement wearing a table verb.
    (
        "policy",
        re.compile(
            r"CREATE\s+(?:OR\s+REPLACE\s+)?POLICY\b"
            r"|ALTER\s+POLICY\b"
            r"|DROP\s+POLICY\b"
            r"|ALTER\s+TABLE\b[^;]{0,200}?\b(?:ENABLE|DISABLE|FORCE|NO\s+FORCE)"
            r"\s+ROW\s+LEVEL\s+SECURITY\b",
            re.IGNORECASE,
        ),
    ),
    # The persistence qualifiers are spelled out rather than matched as `(?:\w+\s+)*TABLE`,
    # the looser form the infra guard uses. That form lets arbitrary words sit between CREATE
    # and TABLE, so what it classifies depends on wording rather than on an enumerated
    # keyword. **This is a robustness choice here, not a defect reported against that guard.**
    # Measured 2026-08-22: the loose pattern does match `CREATE OR REPLACE FUNCTION f RETURNS
    # TABLE`, but Postgres requires the argument parentheses, and every valid form tried --
    # `FUNCTION f() RETURNS TABLE`, `FUNCTION f (p uuid) RETURNS TABLE`, `FUNCTION
    # public.f (p uuid) RETURNS TABLE` -- fails to match, because `(?:\w+\s+)*` stops at `(`
    # and at `.`. Do not go and "fix" the infra guard on the strength of this comment.
    (
        "table",
        re.compile(
            r"CREATE\s+(?:(?:GLOBAL|LOCAL|TEMP|TEMPORARY|UNLOGGED|FOREIGN)\s+)*TABLE\b"
            r"|ALTER\s+(?:FOREIGN\s+)?TABLE\b"
            r"|DROP\s+(?:FOREIGN\s+)?TABLE\b"
            r"|TRUNCATE\b",
            re.IGNORECASE,
        ),
    ),
    ("role", re.compile(r"(?:CREATE|ALTER|DROP)\s+(?:ROLE|USER|GROUP)\b", re.IGNORECASE)),
    ("grant", re.compile(r"GRANT\b|REVOKE\b|ALTER\s+DEFAULT\s+PRIVILEGES\b", re.IGNORECASE)),
)

# Check 3. Not overridable by `_SANCTIONED`, in any file, ever. The `\b` before each attribute
# is load-bearing: it makes NOBYPASSRLS and NOSUPERUSER — the forms the shipped file relies on
# by default — not match, while BYPASSRLS and SUPERUSER do.
_ESCALATIONS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("SUPERUSER", re.compile(r"\bSUPERUSER\b", re.IGNORECASE)),
    ("BYPASSRLS", re.compile(r"\bBYPASSRLS\b", re.IGNORECASE)),
    ("CREATEROLE", re.compile(r"\bCREATEROLE\b", re.IGNORECASE)),
    ("CREATEDB", re.compile(r"\bCREATEDB\b", re.IGNORECASE)),
    ("REPLICATION", re.compile(r"\bREPLICATION\b", re.IGNORECASE)),
    ("a grantee of PUBLIC", re.compile(r"\bTO\s+PUBLIC\b", re.IGNORECASE)),
    ("WITH GRANT OPTION", re.compile(r"\bWITH\s+GRANT\s+OPTION\b", re.IGNORECASE)),
)


def _strip_comments(sql: str) -> str:
    """Remove `--` line comments and `/* */` block comments.

    Without this, the header of `restore_bootstrap_role.sql` would trip every check: it
    explains the grants it replays in prose and names `NOBYPASSRLS` at `:34`.
    """
    return _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("", sql))


def _classify(sql: str) -> list[tuple[str, str]]:
    """Return `(class, snippet)` for every DDL or privilege anchor in `sql`.

    The scan is over the whole comment-stripped text rather than over split statements, so a
    `CREATE ROLE` nested inside a `DO $$ ... $$` block — which is the exact shape
    `restore_bootstrap_role.sql:35-41` uses — is classified rather than skipped.
    """
    text = _strip_comments(sql)
    found: list[tuple[str, str]] = []
    for anchor in _DDL_ANCHOR.finditer(text):
        tail = text[anchor.start() : anchor.start() + _LOOKAHEAD]
        name = "unknown"
        for candidate, pattern in _CLASSES:
            if pattern.match(tail):
                name = candidate
                break
        found.append((name, " ".join(tail.split())[:70]))
    return found


def _sql_files() -> list[Path]:
    return sorted(p for root in _SCRIPT_ROOTS if root.is_dir() for p in root.rglob("*.sql"))


def _key(path: Path) -> str:
    return path.relative_to(_REPO_ROOT).as_posix()


def test_every_sql_file_under_a_scripts_root_is_named_in_the_sanction_table() -> None:
    """Check 1: an unlisted `.sql` file fails whatever it contains, at any depth."""
    unlisted = [_key(p) for p in _sql_files() if _key(p) not in _SANCTIONED]
    assert unlisted == [], (
        "These .sql files under a scripts/ root are named by no decision: "
        + ", ".join(unlisted)
        + ". A .sql file under scripts/ is not inert — scripts/restore_drill.sh:149 feeds one "
        "to psql against a live database. The Alembic chain in backend/migrations/ is the "
        "only source of truth for the schema and the policy set (docs/ops/migrations.md, "
        "ADR-008, ADR-043), so put the DDL in a new revision. If this file genuinely must run "
        "outside the chain, write the ADR that says why, then add it to _SANCTIONED with the "
        "narrowest set of classes that decision covers."
    )


def test_no_sanctioned_sql_file_declares_a_class_its_decision_did_not_cover() -> None:
    """Check 2: being on the allow-list is not a blank cheque."""
    offences: list[str] = []
    for path in _sql_files():
        sanction = _SANCTIONED.get(_key(path))
        if sanction is None:
            continue  # Check 1 owns this file.
        for name, snippet in _classify(path.read_text()):
            if name not in sanction.classes:
                offences.append(
                    f"{_key(path)} declares {name} DDL, which {sanction.decision} does not "
                    f"sanction (allowed: {', '.join(sorted(sanction.classes))}) — {snippet!r}"
                )
    assert offences == [], "\n".join(
        ["A sanctioned scripts/ SQL file declares DDL outside its decision:", *offences]
    )


def test_no_sql_file_under_a_scripts_root_confers_an_escalating_privilege() -> None:
    """Check 3: never overridable by `_SANCTIONED`, because that is what makes it worth having.

    `ALTER ROLE familyroots_app BYPASSRLS` is class `role`, which check 2 permits inside
    `restore_bootstrap_role.sql`. It would switch off row-level security for every request the
    application makes, on a database restored from a backup, silently.
    """
    offences: list[str] = []
    for path in _sql_files():
        text = _strip_comments(path.read_text())
        offences += [f"{_key(path)} confers {label}" for label, p in _ESCALATIONS if p.search(text)]
    assert offences == [], "\n".join(
        [
            "These scripts/ SQL files confer a privilege that defeats the isolation model:",
            *offences,
            "No decision sanctions any of these, and _SANCTIONED cannot override this check. "
            "The request role is NOBYPASSRLS by design (ADR-052; "
            "scripts/restore_bootstrap_role.sql:34) — RLS layer-2 (ADR-008) means nothing "
            "against a role that bypasses it, and a grantee of PUBLIC hands the privilege to "
            "every role in the cluster including that one.",
        ]
    )


def test_the_scripts_sweep_actually_reaches_files() -> None:
    """A glob that returns nothing would make the three checks above vacuously green."""
    assert any(root.is_dir() for root in _SCRIPT_ROOTS), (
        f"None of {[str(r) for r in _SCRIPT_ROOTS]} exists; the checks above cannot mean anything"
    )
    assert _sql_files(), (
        "No .sql file found under any scripts/ root. If that is now correct, delete this "
        "module rather than leaving three sweeps that can never fail."
    )


def test_the_classifier_reads_the_real_bootstrap_file_as_exactly_role_and_grant() -> None:
    """Anti-vacuity for the classifier itself, and the measurement S-069 rests on.

    A scanner that matched nothing would satisfy checks 2 and 3 forever. Measured 2026-08-22:
    nine statements, one `CREATE ROLE` at `:38` and eight grant statements.
    """
    path = _REPO_ROOT / "scripts" / "restore_bootstrap_role.sql"
    assert path.is_file(), f"{path} is missing; ADR-052 requires the restore path to run it"
    found = _classify(path.read_text())
    assert {name for name, _ in found} == {"role", "grant"}, found
    assert sum(1 for name, _ in found if name == "role") == 1, found


def test_the_sanction_table_is_not_a_list_of_names_nobody_reads() -> None:
    """A stale entry is a blank cheque waiting for a future file to reuse the name."""
    missing = [k for k in _SANCTIONED if not (_REPO_ROOT / k).is_file()]
    assert missing == [], (
        f"_SANCTIONED names files that do not exist: {missing}. Delete the entry in the same "
        "change that deletes the file."
    )


@pytest.mark.parametrize("key", sorted(_SANCTIONED))
def test_every_sanction_cites_a_decision_that_exists_and_names_the_file(key: str) -> None:
    """The citation must be load-bearing, not a path that merely resolves.

    Requiring the ADR to contain the file's own path is as far as a mechanical check goes. It
    does not establish that the ADR sanctions these classes; only a reader does that.
    """
    sanction = _SANCTIONED[key]
    decision = _REPO_ROOT / sanction.decision
    assert decision.is_file(), f"{key} cites {sanction.decision}, which does not exist"
    assert key in decision.read_text(), (
        f"{sanction.decision} never mentions {key}, so it cannot be the decision that "
        "sanctions it. Cite the ADR that actually names this file."
    )
    assert sanction.classes, f"{key} is sanctioned for no class at all; remove the entry"
    assert sanction.classes <= {name for name, _ in _CLASSES}, (
        f"{key} names a class the classifier cannot produce: "
        f"{sorted(sanction.classes - {name for name, _ in _CLASSES})}. A sanction for a class "
        "that never gets assigned silently permits nothing and hides the real hole."
    )


@pytest.mark.parametrize(
    ("expected", "sql"),
    [
        # role
        ("role", "CREATE ROLE familyroots_app NOLOGIN;"),
        ("role", "ALTER ROLE familyroots_app NOSUPERUSER;"),
        ("role", "DROP ROLE familyroots_app;"),
        ("role", "create   user  app_reader;"),
        # grant
        ("grant", "GRANT USAGE ON SCHEMA public TO familyroots_app;"),
        ("grant", "REVOKE ALL ON ALL TABLES IN SCHEMA public FROM familyroots_app;"),
        ("grant", "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO a;"),
        # table
        ("table", "CREATE TABLE public.persons (id UUID PRIMARY KEY);"),
        ("table", "create table if not exists public.x (id int);"),
        ("table", "CREATE UNLOGGED TABLE scratch (id int);"),
        ("table", "ALTER TABLE public.persons ADD COLUMN nickname text;"),
        ("table", "TRUNCATE public.audit_logs;"),
        # policy, including the form that wears a table verb
        ("policy", 'CREATE POLICY "persons_sel" ON public.persons FOR SELECT USING (true);'),
        ("policy", "CREATE OR REPLACE POLICY p ON t FOR ALL USING (true);"),
        ("policy", "DROP POLICY persons_ins ON public.persons;"),
        ("policy", "ALTER POLICY persons_sel ON public.persons USING (true);"),
        ("policy", "ALTER TABLE public.persons ENABLE ROW LEVEL SECURITY;"),
        ("policy", "alter   table  public.events   disable   row   level   security ;"),
        ("policy", "ALTER TABLE public.persons FORCE ROW LEVEL SECURITY;"),
        # Default deny. Every one of these is a statement nobody enumerated, and every one of
        # them must fail a file sanctioned only for role and grant.
        ("unknown", "CREATE INDEX ix_persons_clan ON public.persons (created_by_clan_id);"),
        ("unknown", "CREATE EXTENSION IF NOT EXISTS pgcrypto;"),
        ("unknown", "CREATE OR REPLACE FUNCTION f() RETURNS TABLE (x int) AS $$ $$ LANGUAGE sql;"),
        ("unknown", "DROP DATABASE family_roots;"),
        ("unknown", "DROP OWNED BY familyroots_app;"),
        ("unknown", "REASSIGN OWNED BY familyroots_app TO postgres;"),
        ("unknown", "COMMENT ON TABLE public.persons IS 'x';"),
        ("unknown", "CREATE SCHEMA auth;"),
        ("unknown", "ALTER SYSTEM SET row_security = off;"),
    ],
)
def test_the_classifier_gives_each_statement_the_class_it_should(expected: str, sql: str) -> None:
    """Assert the class *set*, because one statement can raise more than one anchor.

    `ALTER DEFAULT PRIVILEGES ... GRANT ... TO a` raises two, at `ALTER` and at `GRANT`, and
    both are `grant`. What checks 2 and 3 read is the set, so the set is what to pin. Ordering
    is pinned separately by the two-statement test below.
    """
    found = _classify(sql)
    assert found, f"no anchor raised for {sql!r}; the classifier would pass it silently"
    assert {name for name, _ in found} == {expected}, found


@pytest.mark.parametrize(
    "sql",
    [
        "-- CREATE POLICY p ON public.persons FOR SELECT USING (true);",
        "/* ALTER TABLE public.persons ENABLE ROW LEVEL SECURITY; */",
        "SELECT 1 FROM pg_roles WHERE rolname = 'familyroots_app';",
        "SELECT security_level, policy_name FROM public.settings;",
        "",
    ],
)
def test_the_classifier_raises_no_anchor_for_sql_that_declares_nothing(sql: str) -> None:
    assert _classify(sql) == []


def test_a_policy_statement_after_a_table_statement_is_not_swallowed_by_it() -> None:
    """The `policy` pattern's gap is `[^;]`, so it cannot reach across a statement boundary.

    With a `[\\s\\S]` gap, the first ALTER here would lazily match through the semicolon to the
    second statement's ROW LEVEL SECURITY, report `policy` twice, and lose the `table` class
    entirely — hiding table DDL inside a file sanctioned for neither.
    """
    sql = "ALTER TABLE x ADD COLUMN y int;\nALTER TABLE z ENABLE ROW LEVEL SECURITY;"
    assert [name for name, _ in _classify(sql)] == ["table", "policy"]


def test_the_do_block_is_looked_inside_rather_than_treated_as_one_opaque_statement() -> None:
    """`restore_bootstrap_role.sql:35-41` wraps its `CREATE ROLE` in PL/pgSQL.

    A classifier that split on `;` and read the leading keyword would see `DO`, then `BEGIN`,
    and never reach the `CREATE`. A `CREATE POLICY` hidden the same way would pass check 2.
    """
    sql = (
        "DO $$\nBEGIN\n  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'x') THEN\n"
        "    CREATE POLICY p ON public.persons FOR SELECT USING (true);\n  END IF;\nEND\n$$;"
    )
    assert [name for name, _ in _classify(sql)] == ["policy"]


@pytest.mark.parametrize(
    "sql",
    [
        "ALTER ROLE familyroots_app BYPASSRLS;",
        "ALTER ROLE familyroots_app SUPERUSER;",
        "CREATE ROLE r LOGIN CREATEROLE;",
        "CREATE ROLE r CREATEDB;",
        "ALTER ROLE r REPLICATION;",
        "GRANT SELECT ON ALL TABLES IN SCHEMA public TO PUBLIC;",
        "GRANT SELECT ON public.persons TO familyroots_app WITH GRANT OPTION;",
    ],
)
def test_the_escalation_detector_finds_what_it_is_given(sql: str) -> None:
    assert [label for label, p in _ESCALATIONS if p.search(_strip_comments(sql))]


@pytest.mark.parametrize(
    "sql",
    [
        # The negated attribute forms the shipped file depends on must not trip it.
        "CREATE ROLE familyroots_app NOLOGIN NOBYPASSRLS NOSUPERUSER NOCREATEDB;",
        "ALTER ROLE familyroots_app NOREPLICATION NOCREATEROLE;",
        # `public` as a schema name is not `PUBLIC` as a grantee.
        "GRANT USAGE ON SCHEMA public TO familyroots_app;",
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO app;",
        # A comment naming the attribute is prose, not a statement.
        "-- NOBYPASSRLS is the default, which is the point of it. BYPASSRLS would undo it.",
    ],
)
def test_the_escalation_detector_refuses_sql_that_confers_nothing(sql: str) -> None:
    assert [label for label, p in _ESCALATIONS if p.search(_strip_comments(sql))] == []
