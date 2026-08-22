"""Fail when a shell script under `scripts/` runs SQL that no decision sanctions.

## The asymmetry this closes (seed S-077, 2026-08-22)

`test_scripts_sql_is_sanctioned.py` reads `.sql` files. **The dangerous statements are not
all in `.sql` files.** Verified at source 2026-08-22, and both line numbers seed S-077 cited
are still correct:

    scripts/restore_drill.sh:116, the argument of a `psql "$ADMIN_DSN" -v ON_ERROR_STOP=1 -c`:
        DROP DATABASE IF EXISTS ${SCRATCH_DB} WITH (FORCE)
    scripts/restore_drill.sh:122, the argument of the same call one echo later:
        CREATE DATABASE ${SCRATCH_DB}

Before this module, no check in the tree read either line. **Nothing is wrong with them** —
the drill is meant to drop and recreate its own throwaway database, and
`docs/ops/backup-restore.md:91-92` is the sentence that says so. The defect is the asymmetry:
`ALTER ROLE familyroots_app BYPASSRLS` written into `restore_bootstrap_role.sql` fails the
other guard's check 3, and the identical statement written into `psql -c` two files away was
invisible.

## The shape, and why this one

**Extract only the text that a `psql` invocation executes, then hand it to the classifier the
`.sql` guard already uses.** That is the whole design, and both halves are deliberate.

*Extract, do not grep.* A guard that swept shell scripts for the word `CREATE` would fire on
`echo "==> creating scratch DB"`, on every `--help` banner, and on the drill's own header
comment. S-060's rule is that a guard with a high false-positive rate gets suppressed, and a
suppressed guard is worse than none. So the scanner recognises four shapes and nothing else:

1. a `-c` / `-tAc` / `--command` argument on a logical line that invokes `psql`,
2. a heredoc opened on a logical line that invokes `psql` (`<<EOF`, `<<'EOF'`, `<<-EOF`),
3. a here-string on such a line (`psql "$DSN" <<< "..."`),
4. one level of literal variable indirection: `psql -c "$SQL"` resolves against a
   `SQL='...'` or `SQL="..."` assignment in the same file.

Everything else in the file is text, not SQL, and this module does not look at it. Measured
2026-08-22 on the tree as it stands: five shell scripts swept, 13 regions extracted and all
13 from `scripts/restore_drill.sh`, of which 10 raise no anchor at all because they are
`SELECT` statements. **Zero false positives on the shipped tree, and the read-only majority
is silent rather than allow-listed.**

*Reuse the classifier, do not write a second one.* `_classify`, `_strip_comments` and
`_ESCALATIONS` are imported from `test_scripts_sql_is_sanctioned`. Two guards with two
regexes would drift, and drift **is** the defect this seed was opened to fix: the point is
that a statement gets the same verdict wherever it is written. That classifier defaults to
deny — a statement it has no class for is `unknown`, and `unknown` is never sanctioned — so
this module inherits default-deny for free.

Two classes are added on top, in this module only, because they matter for inline SQL and do
not arise in a `.sql` file under `scripts/`:

- **`database`**, for `CREATE`/`ALTER`/`DROP DATABASE`. The `.sql` guard classifies
  `DROP DATABASE` as `unknown` and its parametrised table pins that, deliberately. Adding
  the class *there* would have weakened its default-deny evidence, so the refinement lives
  here and that file is untouched.
- **`session_role`**, for `SET [LOCAL|SESSION] ROLE` and `SET SESSION AUTHORIZATION`. The
  imported anchor set does not raise on `SET`, and this is how a script changes who it is
  without any DDL. `SET search_path` and `set_config(...)` raise nothing: the anchor is
  spelled out as `SET … ROLE`, not as the bare word `SET`, so benign `SET` statements do not
  become `unknown` and fail.

## The three checks, which are not the same question

1. **A script whose inline SQL raises any anchor must be named in `_SANCTIONED`.** A script
   that only runs `SELECT` needs no entry and gets none — that is the false-positive budget
   spent where it belongs.
2. **A named script may run only the classes its decisions cover.** `unknown` is in no set.
3. **No inline SQL anywhere under a scripts root may confer an escalating privilege**, in any
   file, sanctioned or not. Not overridable by `_SANCTIONED`, exactly as in the `.sql` guard,
   and it is the check both of S-077's planted controls fail.

## What this misses. Read this list before trusting the guard

- **It reads shell scripts only. A `.py` script under `scripts/` is invisible to it.** This
  is the largest hole and it is a choice, not an oversight. Scanning every Python string
  literal would fire on prose: a module docstring saying "this does not drop the database"
  is a string literal, and `_strip_comments` cannot tell it from a statement. Doing it with
  `ast` to skip docstrings is a second decision and belongs in its own seed. Measured
  2026-08-22, this costs nothing yet: `scripts/bootstrap_super_admin.py` calls PostgREST
  builders (`.execute()` at `:39` and `:73`, no SQL string) and `scripts/seed_dev_data.py`
  is a `NotImplementedError` stub.
- **Client CLIs that are not `psql` are invisible.** `createdb`, `dropdb`, and above all
  `createuser --superuser` do the damage without any SQL text for this scanner to read.
  `pg_restore` and `pg_dump` are not read either. Only the word `psql` opens a region.
- **Variable indirection beyond one literal level.** `SQL="$PREFIX bypassrls"`,
  `SQL=$(cat <<'EOF' …)`, and any value built at run time resolve to nothing. Only a direct
  `NAME='…'` or `NAME="…"` assignment in the same file is followed.
- **A heredoc that is not on a `psql` line.** `cat <<EOF > /tmp/x.sql` on one line and
  `psql -f /tmp/x.sql` on another is two regions this scanner joins into none. `cat <<EOF |
  psql "$DSN"` **is** caught, because both words are on the same logical line.
- **`psql -f` targets are not followed.** A `.sql` file under `scripts/` is the other guard's
  subject; a path outside the repository is nobody's.
- **It classifies by verb, not by meaning** — inherited from the classifier it reuses.
  Widening a sanctioned script's `GRANT SELECT` to `GRANT ALL` stays class `grant`. A
  `SET ROLE` to a different role inside a script already sanctioned for `session_role`
  passes. What catches those is the drill's own check 4, which drops to the request role and
  counts rows two-sided (ADR-052 § 3).
- **Only whole-line `#` comments are skipped.** Shell has no reliable comment rule this side
  of a parser, so a commented-out `psql -c` on the end of a live line would still be read.
  That direction is safe (it can only over-report), and no such line exists today.
- **Scope is `scripts/` and `backend/scripts/`.** A shell script anywhere else in the tree is
  seen by no guard. `docs/ops/backup-restore.md:330` holds a real `psql … -c "CREATE
  DATABASE familyroots_head_stage"` inside a runbook, and documentation is not swept.
- **`.github/workflows/*.yml` is not swept.** A `run:` step is a shell script by another
  name, and a workflow that ran `psql -c` would not be read. No workflow does today.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple

import pytest

from tests.unit.test_scripts_sql_is_sanctioned import (
    _CLASSES,
    _ESCALATIONS,
    _classify,
    _strip_comments,
)

pytestmark = pytest.mark.unit

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = _BACKEND_ROOT.parent

# The same two roots the `.sql` guard sweeps, for the same reason: `scripts/` is where SQL
# actually runs, and `backend/scripts/` is the next place it would appear.
_SCRIPT_ROOTS = (_REPO_ROOT / "scripts", _BACKEND_ROOT / "scripts")

_SHELL_SUFFIXES = frozenset({".sh", ".bash", ".zsh", ".ksh"})
# An executable with no suffix is still a shell script. Match the interpreter, so a script
# added under any name is swept.
_SHEBANG = re.compile(r"^#!.*\b(?:sh|bash|zsh|ksh|dash)\b")

# The only word that opens a SQL region. See "What this misses".
_CLIENT = re.compile(r"\bpsql\b")

# `-c "…"`, `-tAc "…"` (bundled short options, `c` last), `--command "…"`, `--command="…"`.
# The argument is a double-quoted, single-quoted, ANSI-C-quoted, or bare token.
_COMMAND = re.compile(
    r"(?:^|\s)(?:--command[=\s]+|-[A-Za-z]*c\s+)"
    r"(\"(?:[^\"\\]|\\.)*\"|'[^']*'|\$'(?:[^'\\]|\\.)*'|[^\s;|&]+)"
)

# `<<EOF`, `<<'EOF'`, `<<"EOF"`, `<<-EOF`, `<< EOF`. The negative lookahead keeps `<<<`
# (a here-string) and `<<(` out; here-strings are read by `_HERESTRING` instead.
_HEREDOC = re.compile(r"<<(-?)[ \t]*(?![<(])(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2")
_HERESTRING = re.compile(r"<<<\s*(\"(?:[^\"\\]|\\.)*\"|'[^']*'|[^\s;|&]+)")

# A `-c` argument that is exactly one parameter expansion, and nothing else.
_BARE_VAR = re.compile(r"^\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?$")


class _Region(NamedTuple):
    """One run of text that a `psql` invocation executes, and where it was read from."""

    line: int
    origin: str
    sql: str


class _Sanction(NamedTuple):
    """What one shell script under a scripts root may run inline, and who said so."""

    classes: frozenset[str]
    decisions: tuple[str, ...]
    why: str


# Keyed by path relative to the repository root. A script that runs only `SELECT` raises no
# anchor and needs no entry here; see check 1.
_SANCTIONED: dict[str, _Sanction] = {
    "scripts/restore_drill.sh": _Sanction(
        classes=frozenset({"database", "session_role"}),
        decisions=(
            "docs/ops/backup-restore.md",
            "docs/decisions/052-restore-bootstraps-the-request-role.md",
        ),
        why=(
            "database: the drill never restores over production. It drops and recreates one "
            "scratch database, familyroots_restore_drill, which is what makes it safe to "
            "re-run; docs/ops/backup-restore.md:91-92 states that as the rule and names the "
            "database. session_role: check 4 exists to drop out of the superuser that "
            "created the scratch database and prove clan isolation two-sided as the request "
            "role, which ADR-052 section 3 decided. Both classes are the point of the "
            "script. It is sanctioned for nothing else: a CREATE TABLE or a GRANT added "
            "inline fails check 2, because the Alembic chain owns the schema and "
            "scripts/restore_bootstrap_role.sql owns the grants."
        ),
    ),
}

# Refinements applied only where the imported classifier returns `unknown`. Matched against
# the snippet it returns, which starts at the anchor.
_REFINEMENTS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("database", re.compile(r"^(?:CREATE|ALTER|DROP)\s+DATABASE\b", re.IGNORECASE)),
)

# Anchors the imported classifier does not raise, added here because they only arise inline.
# Spelled out as `SET … ROLE` rather than a bare `SET`, so `SET search_path TO x` and
# `SELECT set_config(...)` stay silent instead of becoming `unknown` and failing.
_EXTRA_ANCHORS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "session_role",
        re.compile(
            r"\bSET\s+(?:LOCAL\s+|SESSION\s+)?ROLE\b|\bSET\s+SESSION\s+AUTHORIZATION\b",
            re.IGNORECASE,
        ),
    ),
)

_INLINE_CLASSES = frozenset(
    {name for name, _ in _CLASSES}
    | {name for name, _ in _REFINEMENTS}
    | {name for name, _ in _EXTRA_ANCHORS}
)


def _unquote(token: str) -> str:
    """Strip one layer of shell quoting from a `-c` argument or here-string."""
    if len(token) >= 2 and token[0] == token[-1] and token[0] in "\"'":
        body = token[1:-1]
        return body.replace('\\"', '"').replace("\\\\", "\\") if token[0] == '"' else body
    if token.startswith("$'") and token.endswith("'"):
        return token[2:-1]
    return token


def _literal_assignments(text: str, name: str) -> list[str]:
    """Every literal `name='…'` / `name="…"` value in `text`, one level, no composition."""
    pattern = re.compile(rf"(?:^|\s){re.escape(name)}=(\"(?:[^\"\\]|\\.)*\"|'[^']*')", re.DOTALL)
    return [_unquote(m.group(1)) for m in pattern.finditer(text)]


def _regions(text: str) -> list[_Region]:
    """Return every run of SQL text a `psql` invocation in `text` executes.

    Logical lines are assembled first, so a `-c` that sits on a backslash continuation of the
    `psql` line is still read — `scripts/restore_drill.sh:193-194` and `:201-202` are exactly
    that shape, and a scanner working line by line would miss both.
    """
    raw = text.splitlines()
    out: list[_Region] = []
    i = 0
    while i < len(raw):
        start = i
        buf = raw[i]
        while buf.rstrip().endswith("\\") and i + 1 < len(raw):
            i += 1
            buf = buf.rstrip()[:-1] + " " + raw[i]
        if not buf.lstrip().startswith("#") and _CLIENT.search(buf):
            for match in _COMMAND.finditer(buf):
                arg = _unquote(match.group(1))
                var = _BARE_VAR.match(arg)
                if var is None:
                    out.append(_Region(start + 1, "-c argument", arg))
                else:
                    out += [
                        _Region(start + 1, f"-c argument via ${var.group(1)}", value)
                        for value in _literal_assignments(text, var.group(1))
                    ]
            for match in _HERESTRING.finditer(buf):
                out.append(_Region(start + 1, "here-string", _unquote(match.group(1))))
            cursor = i
            for dash, _quote, tag in _HEREDOC.findall(buf):
                cursor += 1
                body_start = cursor
                body: list[str] = []
                while cursor < len(raw):
                    candidate = raw[cursor].strip() if dash else raw[cursor].rstrip()
                    if candidate == tag:
                        break
                    body.append(raw[cursor])
                    cursor += 1
                out.append(_Region(body_start + 1, f"heredoc <<{tag}", "\n".join(body)))
            i = cursor
        i += 1
    return out


def _classify_inline(sql: str) -> list[tuple[str, str]]:
    """Classify inline SQL: the imported classifier, plus this module's two extra classes."""
    found: list[tuple[str, str]] = []
    for name, snippet in _classify(sql):
        if name == "unknown":
            name = next((c for c, p in _REFINEMENTS if p.match(snippet)), "unknown")
        found.append((name, snippet))
    text = _strip_comments(sql)
    for name, pattern in _EXTRA_ANCHORS:
        found += [
            (name, " ".join(text[m.start() : m.start() + 70].split()))
            for m in pattern.finditer(text)
        ]
    return found


def _is_shell(path: Path) -> bool:
    if path.suffix in _SHELL_SUFFIXES:
        return True
    try:
        with path.open(encoding="utf-8") as handle:
            return _SHEBANG.match(handle.readline()) is not None
    except OSError, UnicodeDecodeError:
        return False


def _shell_files() -> list[Path]:
    return sorted(
        p
        for root in _SCRIPT_ROOTS
        if root.is_dir()
        for p in root.rglob("*")
        if p.is_file() and _is_shell(p)
    )


def _key(path: Path) -> str:
    return path.relative_to(_REPO_ROOT).as_posix()


def _scanned() -> list[tuple[str, _Region]]:
    return [(_key(p), r) for p in _shell_files() for r in _regions(p.read_text())]


def test_every_script_that_runs_inline_ddl_is_named_in_the_sanction_table() -> None:
    """Check 1: a script whose inline SQL declares anything must be named by a decision.

    A script that only runs `SELECT` raises no anchor and is not required to appear here.
    That is where the false-positive budget goes: read-only psql calls stay silent rather
    than being allow-listed one by one, which is what keeps this guard worth running.
    """
    offences = [
        f"{key}:{region.line} ({region.origin}) runs {name} DDL — {snippet!r}"
        for key, region in _scanned()
        if key not in _SANCTIONED
        for name, snippet in _classify_inline(region.sql)
    ]
    assert offences == [], "\n".join(
        [
            "These shell scripts run DDL or privilege SQL inline that no decision sanctions:",
            *offences,
            "Inline SQL is not less real than a .sql file — scripts/restore_drill.sh:116 "
            "drops a database through psql -c. The Alembic chain in backend/migrations/ is "
            "the only source of truth for the schema and the policy set "
            "(docs/ops/migrations.md, ADR-008, ADR-043), so put the DDL in a new revision. "
            "If this script genuinely must run it outside the chain, write the decision that "
            "says why, then add the script to _SANCTIONED with the narrowest set of classes "
            "that decision covers.",
        ]
    )


def test_no_sanctioned_script_runs_a_class_its_decisions_did_not_cover() -> None:
    """Check 2: being on the allow-list is not a blank cheque.

    `unknown` is in no sanctioned set, so a statement nobody enumerated fails here rather
    than passing by omission.
    """
    offences: list[str] = []
    for key, region in _scanned():
        sanction = _SANCTIONED.get(key)
        if sanction is None:
            continue  # Check 1 owns this script.
        for name, snippet in _classify_inline(region.sql):
            if name not in sanction.classes:
                offences.append(
                    f"{key}:{region.line} ({region.origin}) runs {name} DDL, which "
                    f"{' and '.join(sanction.decisions)} does not sanction "
                    f"(allowed: {', '.join(sorted(sanction.classes))}) — {snippet!r}"
                )
    assert offences == [], "\n".join(
        ["A sanctioned script runs inline SQL outside its decisions:", *offences]
    )


def test_no_script_runs_inline_sql_that_confers_an_escalating_privilege() -> None:
    """Check 3: never overridable by `_SANCTIONED`, in any script, ever.

    This is the check S-077's two planted controls fail. `ALTER ROLE familyroots_app
    BYPASSRLS` is class `role`; putting it in a script sanctioned for `role` would satisfy
    check 2 and it would still fail here. It would switch off row-level security for every
    request the application makes, on a database restored from a backup, silently.
    """
    offences = [
        f"{key}:{region.line} ({region.origin}) confers {label}"
        for key, region in _scanned()
        for label, pattern in _ESCALATIONS
        if pattern.search(_strip_comments(region.sql))
    ]
    assert offences == [], "\n".join(
        [
            "These scripts run inline SQL that defeats the isolation model:",
            *offences,
            "No decision sanctions any of these, and _SANCTIONED cannot override this check. "
            "The request role is NOBYPASSRLS by design (ADR-052; "
            "scripts/restore_bootstrap_role.sql:34) — RLS layer-2 (ADR-008) means nothing "
            "against a role that bypasses it, and a grantee of PUBLIC hands the privilege to "
            "every role in the cluster including that one.",
        ]
    )


def test_the_shell_sweep_actually_reaches_files_and_extracts_sql() -> None:
    """A scanner that silently matched nothing would make all three checks vacuous.

    This is the anti-vacuity test the `.sql` guard learned to carry. It pins that the sweep
    finds shell scripts *and* that the extractor gets SQL out of one.
    """
    assert any(root.is_dir() for root in _SCRIPT_ROOTS), (
        f"None of {[str(r) for r in _SCRIPT_ROOTS]} exists; the checks above cannot mean anything"
    )
    assert _shell_files(), (
        "No shell script found under any scripts/ root. If that is now correct, delete this "
        "module rather than leaving three sweeps that can never fail."
    )
    assert _scanned(), (
        "No inline SQL extracted from any shell script under a scripts/ root. Either every "
        "psql call has gone, or the extractor has stopped seeing the shapes it reads. "
        "scripts/restore_drill.sh:116 was the reason this module exists; check it first."
    )


def test_the_scanner_reads_the_real_drill_as_two_database_statements_and_nothing_else() -> None:
    """The measurement S-077 rests on, re-taken by the test itself on every run.

    Verified by hand 2026-08-22: `scripts/restore_drill.sh` runs `DROP DATABASE IF EXISTS
    … WITH (FORCE)` at `:116` and `CREATE DATABASE` at `:122`, and every other inline
    statement is a `SELECT` or a `SET LOCAL ROLE`. Both line numbers are as seed S-077 cited
    them. Asserting the count as well as the set is what stops a future extractor regression
    from passing here while quietly reading half the file.
    """
    path = _REPO_ROOT / "scripts" / "restore_drill.sh"
    assert path.is_file(), f"{path} is missing; docs/ops/backup-restore.md:81 requires it"
    regions = _regions(path.read_text())
    classes = [name for r in regions for name, _ in _classify_inline(r.sql)]
    assert sorted(classes) == ["database", "database", "session_role"], classes
    silent = [r for r in regions if not _classify_inline(r.sql)]
    assert len(silent) >= 8, (
        "The drill runs many read-only psql calls and they must stay silent; only "
        f"{len(silent)} of {len(regions)} regions raised no anchor"
    )
    lines = sorted(
        r.line for r in regions if any(n == "database" for n, _ in _classify_inline(r.sql))
    )
    assert lines == [116, 122], lines


def test_the_sanction_table_is_not_a_list_of_names_nobody_reads() -> None:
    """A stale entry is a blank cheque waiting for a future script to reuse the name."""
    missing = [k for k in _SANCTIONED if not (_REPO_ROOT / k).is_file()]
    assert missing == [], (
        f"_SANCTIONED names scripts that do not exist: {missing}. Delete the entry in the "
        "same change that deletes the script."
    )


@pytest.mark.parametrize("key", sorted(_SANCTIONED))
def test_every_sanction_cites_decisions_that_exist_and_name_the_script(key: str) -> None:
    """The citation must be load-bearing, not a path that merely resolves.

    Requiring each cited document to contain the script's own path is as far as a mechanical
    check goes. It does not establish that the document sanctions these classes; only a
    reader does. A human read `docs/ops/backup-restore.md:91-92` and ADR-052 section 3 on
    2026-08-22, and they do.
    """
    sanction = _SANCTIONED[key]
    assert sanction.decisions, f"{key} cites no decision at all; remove the entry"
    for citation in sanction.decisions:
        document = _REPO_ROOT / citation
        assert document.is_file(), f"{key} cites {citation}, which does not exist"
        assert key in document.read_text(), (
            f"{citation} never mentions {key}, so it cannot be a decision that sanctions it."
        )
    assert sanction.classes, f"{key} is sanctioned for no class at all; remove the entry"
    assert sanction.classes <= _INLINE_CLASSES, (
        f"{key} names a class the classifier cannot produce: "
        f"{sorted(sanction.classes - _INLINE_CLASSES)}. A sanction for a class that never "
        "gets assigned silently permits nothing and hides the real hole."
    )


@pytest.mark.parametrize(
    ("expected", "script"),
    [
        # The four shapes the extractor recognises.
        (
            ["DROP DATABASE x"],
            'psql "$DSN" -v ON_ERROR_STOP=1 -c "DROP DATABASE x"',
        ),
        (["DROP DATABASE x"], "psql \"$DSN\" -c 'DROP DATABASE x'"),
        (["DROP DATABASE x"], 'psql "$DSN" --command="DROP DATABASE x"'),
        (["DROP DATABASE x"], 'psql "$DSN" --command "DROP DATABASE x"'),
        # Bundled short options with `c` last, which is how psql is usually typed.
        (["SELECT 1"], 'psql "$DSN" -tAc "SELECT 1"'),
        # A `-c` on a backslash continuation: restore_drill.sh:193-194 is this shape.
        (["SELECT 1"], 'psql "$DSN" -tA -F\'|\' \\\n  -c "SELECT 1" \\\n  2>&1'),
        # More than one `-c` in one invocation: restore_drill.sh:220-223 is this shape.
        (
            ["SET LOCAL ROLE app", "SELECT count(*) FROM persons"],
            'psql "$DSN" -c "SET LOCAL ROLE app" -c "SELECT count(*) FROM persons"',
        ),
        # Heredocs, all three openings.
        (["ALTER ROLE app BYPASSRLS;"], "psql \"$DSN\" <<'EOF'\nALTER ROLE app BYPASSRLS;\nEOF"),
        (["ALTER ROLE app BYPASSRLS;"], 'psql "$DSN" <<EOF\nALTER ROLE app BYPASSRLS;\nEOF'),
        (["ALTER ROLE app BYPASSRLS;"], 'psql "$DSN" <<-SQL\n\tALTER ROLE app BYPASSRLS;\n\tSQL'),
        # A heredoc piped into psql rather than opened by it.
        (["CREATE TABLE t (id int);"], 'cat <<EOF | psql "$DSN"\nCREATE TABLE t (id int);\nEOF'),
        # Here-string.
        (["DROP DATABASE x"], 'psql "$DSN" <<< "DROP DATABASE x"'),
        # One level of literal variable indirection.
        (["CREATE TABLE t (id int);"], 'SQL="CREATE TABLE t (id int);"\npsql "$DSN" -c "$SQL"'),
        (
            ["CREATE TABLE t (id int);"],
            'SQL=\'CREATE TABLE t (id int);\'\npsql "$DSN" -c "${SQL}"',
        ),
    ],
)
def test_the_extractor_finds_the_sql_shapes_it_is_given(expected: list[str], script: str) -> None:
    assert [r.sql.strip() for r in _regions(script)] == expected


@pytest.mark.parametrize(
    "script",
    [
        # A whole-line comment is prose, including the one that quotes a real command.
        '# psql "$DSN" -c "DROP DATABASE x"',
        '  # psql "$DSN" <<< "ALTER ROLE app BYPASSRLS"',
        # No psql on the line: `-c` belongs to some other program. This is the check that
        # keeps `bash -c` and `grep -c` out, and it is why the client word gates everything.
        'bash -c "DROP DATABASE x"',
        'sh -c "psql_is_not_a_word_here"',
        "echo hello | grep -c .",
        # A here-string that feeds a shell loop, which supabase_local.sh:72 really does.
        'done <<< "$roster"',
        # A heredoc that no database client reads.
        "cat <<EOF > /tmp/notes\nCREATE TABLE t (id int);\nEOF",
        # Prose that merely contains the words.
        'echo "==> dropping scratch DB if it exists: ${SCRATCH_DB}"',
        "",
    ],
)
def test_the_extractor_opens_no_region_for_text_that_is_not_executed_sql(script: str) -> None:
    assert _regions(script) == []


def test_a_heredoc_body_does_not_swallow_the_rest_of_the_file() -> None:
    """The terminator ends the region, so statements after it are read as themselves."""
    script = 'psql "$DSN" <<EOF\nSELECT 1;\nEOF\npsql "$DSN" -c "DROP DATABASE x"'
    assert [(r.origin, r.sql.strip()) for r in _regions(script)] == [
        ("heredoc <<EOF", "SELECT 1;"),
        ("-c argument", "DROP DATABASE x"),
    ]


def test_a_quoted_heredoc_tag_is_matched_against_the_bare_terminator() -> None:
    """`<<'EOF'` is quoted at the opening and bare at the close; both must line up.

    Getting this wrong runs the body to end of file, which would silently merge every later
    statement into one region and report the wrong line number for all of them.
    """
    script = "psql \"$DSN\" <<'EOF'\nSELECT 1;\nEOF\necho done"
    assert [r.sql.strip() for r in _regions(script)] == ["SELECT 1;"]


@pytest.mark.parametrize(
    ("expected", "sql"),
    [
        # The two classes this module adds.
        ("database", "DROP DATABASE IF EXISTS familyroots_restore_drill WITH (FORCE)"),
        ("database", "CREATE DATABASE familyroots_restore_drill"),
        ("database", "ALTER DATABASE family_roots SET row_security = off"),
        ("session_role", "SET LOCAL ROLE familyroots_app"),
        ("session_role", "SET ROLE postgres"),
        ("session_role", "SET SESSION AUTHORIZATION postgres"),
        # Inherited unchanged from the .sql guard's classifier.
        ("role", "ALTER ROLE familyroots_app BYPASSRLS"),
        ("grant", "GRANT SELECT ON public.persons TO familyroots_app"),
        ("table", "CREATE TABLE public.persons (id UUID PRIMARY KEY)"),
        ("policy", "ALTER TABLE public.persons ENABLE ROW LEVEL SECURITY"),
        # Still default-deny: a statement nobody enumerated is not quietly allowed.
        ("unknown", "CREATE EXTENSION IF NOT EXISTS pgcrypto"),
        ("unknown", "DROP OWNED BY familyroots_app"),
        ("unknown", "CREATE SCHEMA auth"),
    ],
)
def test_the_inline_classifier_gives_each_statement_the_class_it_should(
    expected: str, sql: str
) -> None:
    found = _classify_inline(sql)
    assert found, f"no anchor raised for {sql!r}; the guard would pass it silently"
    assert {name for name, _ in found} == {expected}, found


@pytest.mark.parametrize(
    "sql",
    [
        # Every read-only statement the drill actually runs, verbatim in form. If any of
        # these raised an anchor, restore_drill.sh would need a sanction for it and the
        # guard would start costing more than it catches.
        "SELECT version_num FROM alembic_version",
        "SELECT count(*) FROM persons",
        "SELECT id, created_by_clan_id FROM persons WHERE is_deleted = false LIMIT 1",
        "SELECT count(*) FROM get_family_tree_flat('a', 'b', 5)",
        "SELECT set_config('app.clan_id', 'a', true)",
        "SELECT count(*) FROM pg_roles WHERE rolname = 'familyroots_app'",
        "SELECT clan_id FROM clan_memberships GROUP BY clan_id ORDER BY count(*) DESC LIMIT 1",
        "SELECT gen_random_uuid()",
        # `SET` on its own is not `SET ROLE`, and `set_config` is not `SET` at all.
        "SET search_path TO public",
        "RESET ROLE",
        # Prose that survives extraction unchanged must still declare nothing.
        "$SCRATCH_DSN",
        "",
    ],
)
def test_the_inline_classifier_raises_no_anchor_for_statements_that_declare_nothing(
    sql: str,
) -> None:
    assert _classify_inline(sql) == []


@pytest.mark.parametrize(
    "sql",
    [
        "ALTER ROLE familyroots_app BYPASSRLS",
        "ALTER ROLE familyroots_app SUPERUSER",
        "CREATE ROLE r LOGIN CREATEROLE",
        "GRANT SELECT ON ALL TABLES IN SCHEMA public TO PUBLIC",
        "GRANT SELECT ON public.persons TO familyroots_app WITH GRANT OPTION",
    ],
)
def test_check_three_would_fire_on_the_statements_it_exists_to_catch(sql: str) -> None:
    """Check 3 reads regions, so pin that the imported detector fires on the region text.

    Both of S-077's planted controls are the first line of this list, put into a script
    rather than into a `.sql` file.
    """
    assert [label for label, p in _ESCALATIONS if p.search(_strip_comments(sql))]
