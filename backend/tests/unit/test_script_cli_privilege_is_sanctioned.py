"""Fail when a shell script under `scripts/` invokes a Postgres client CLI no decision allows.

## The blind spot this closes (seed S-079, 2026-08-26)

**Every other guard in this tree reads SQL text.** `test_scripts_sql_is_sanctioned.py` (S-069)
reads `.sql` files. `test_inline_sql_in_scripts_is_sanctioned.py` (S-077) reads what a `psql`
invocation executes. A script that ran

    createuser --superuser familyroots_app

escalates exactly as `ALTER ROLE familyroots_app SUPERUSER` does, and **there is no SQL text for
either scanner to read.** S-077 named this itself, in its own "What this misses" list: "Client
CLIs that are not `psql` are invisible. `createdb`, `dropdb`, and above all `createuser
--superuser` do the damage without any SQL text for this scanner to read."

**Nothing is wrong today.** Measured 2026-08-26 with

    git grep -nwE '(createuser|dropuser|createdb|dropdb|pg_restore|pg_dump|pg_dumpall|pg_ctl|
    pg_isready|reindexdb|vacuumdb|clusterdb|pg_basebackup|pg_upgrade|pg_resetwal|initdb|
    pgbench|psql)' -- scripts backend/scripts

The tree invokes exactly two of them: `pg_dump` at `scripts/db_backup.sh:40` and `pg_restore` at
`scripts/restore_drill.sh:130`. There is no `createuser`, no `dropuser`, no `createdb` and no
`dropdb` anywhere. **The gap was never a live defect; it was that the guards' shape had a hole
their own error messages did not admit to.**

*(A note on that measurement, because it nearly went in wrong. `git grep -E` is POSIX ERE, where
`\b` is not a word boundary. The first run of the command above used `\b(...)\b` and returned
nothing at all, which reads exactly like "no CLI is used". Use `-w`.)*

## The decision: a third module, not a widening of either existing one

A rule over client CLIs matches **argv**. A rule over SQL matches **statements**. They are not
the same kind of rule and they cannot share a verdict:

- **Not S-069's module.** It reads `.sql` files. A shell script is not its subject at all.
- **Not S-077's module.** Every one of its three checks is phrased over `_Region.sql` and the
  imported `_classify`, and its `_SANCTIONED` vocabulary is SQL classes. Reporting a
  `createuser --superuser` through "runs role DDL — 'CREATE ROLE …'" would be a lie about where
  the text came from, and `psql -c "DROP DATABASE x"` and `dropdb x` need different sanction
  keys because they are different capabilities granted to different scripts.
- **So: a third module** that shares the pieces where sharing prevents drift and owns the pieces
  that are genuinely its own.

**What is shared, and why exactly these.** `_shell_files`, `_is_shell`, `_SCRIPT_ROOTS` and
`_key` are imported from S-077's module, so the two guards sweep the **identical** file set by
construction rather than by a test that hopes they agree. A script one guard reads and the other
does not would be a hole neither guard could report. `_ESCALATIONS` is imported from S-069's
module, not to match against text, but so that the argv flags this module forbids are checked
against the SQL attributes that module forbids — see
`test_the_argv_escalation_set_and_the_sql_escalation_set_account_for_each_other`.

**What is not shared.** The logical-line join below duplicates six lines of S-077's `_regions`.
Extracting it there would have to preserve `_regions`' heredoc cursor, which advances the outer
loop past a heredoc body; a pre-computed list of logical lines loses that. Six duplicated lines
with no shared verdict is the cheaper of the two risks.

## Two rules, because there are two questions (and a set is a setting too)

S-014's finding, recorded in `.claude/rules/seeds.md` § "A set is a setting too", is that one
guard asking one question of a mixed set pins the set rather than the coverage. This module asks
two questions with two different reaches, on purpose:

1. **Checks 1 and 2 read the command word.** A CLI counts as invoked when it is the command word
   of a segment: the first token that is not a `VAR=value` prefix and not a transparent wrapper
   (`if`, `!`, `env`, `sudo`, `xargs`, …). This is deliberately narrow. `scripts/restore_drill
   .sh:131` and `:133` both `echo` the words "pg_restore", and a rule that read any token would
   report two invocations that do not exist. S-060's rule is that a noisy guard gets suppressed,
   and these two checks are the noise-sensitive half.
2. **Check 3 reads every token in the segment.** The escalation check is the one this seed exists
   for and the one that must not be dodged by a wrapper, so it fires when a segment holds a
   `createuser` token **and** an escalating flag token, wherever they sit. That reaches
   `sudo -u postgres createuser -s app` and `bash -c "createuser --superuser app"`, both of which
   the command-word rule misses. The cost is that `echo "never run createuser -s"` would fire;
   that sentence is cheap to reword and no such line exists today.

## What a CLI is allowed to do, and default-deny at the level of the name

`_CLI_RULES` names every binary in the client image and gives each one a class. Read at source
2026-08-26: `docker exec familyroots-pgdb ls /usr/local/bin`, image `postgres:18-alpine`,
`postgres (PostgreSQL) 18.4` — the same image `docker-compose.yml:3` runs.

    class          raised by
    ------------   -------------------------------------------------------------------
    (silent)       pg_dump, pg_dumpall, pg_isready, pg_config, pg_controldata,
                   pg_waldump, pg_walsummary, pg_verifybackup, pg_amcheck,
                   pg_test_fsync, pg_test_timing, oid2name, psql without -f
    role           createuser, dropuser
    database       createdb, dropdb, pg_restore --clean, pg_restore --create
    restore        pg_restore
    sql_file       psql -f / psql --file
    unknown        every other recognised binary — never in any sanctioned set

`role` and `database` are the words S-069 and S-077 already use, so `dropdb x` and
`psql -c "DROP DATABASE x"` land in the same vocabulary in two different guards.

**A name nobody has decided about is `unknown`, and `unknown` is never sanctioned.** That is
S-069's default-deny moved up one level: from "a statement no class claims" to "a binary no
decision claims". `initdb`, `pg_ctl`, `pg_resetwal`, `pg_upgrade`, `reindexdb`, `vacuumdb` and
the rest are `unknown` not because they are known to be dangerous but because nobody has said
what a script may do with them. `test_every_binary_in_the_client_image_has_a_decision` pins the
image's own list against `_CLI_RULES`, so a Postgres upgrade that ships a new binary fails here
until someone classifies it.

**`pg_dump` is silent by decision, not by omission.** It reads; it neither escalates nor
destroys, and the seed's end state names those two. `scripts/db_backup.sh:40` is the invocation
that decision leaves silent, and `test_the_backup_script_is_silent_because_pg_dump_reads` pins
it, so anyone who later gives `pg_dump` a class is told immediately that `db_backup.sh` then
needs an entry. Exfiltration — `pg_dump` writing the whole database to a file, `pg_dumpall`
writing role password hashes — is **not** this guard's subject. Say so rather than implying a
silent CLI is a safe one.

## The escalating flags, read at source

`docker exec familyroots-pgdb createuser --help`, 2026-08-26, PostgreSQL 18.4. Five flags set a
role attribute that defeats the isolation model, and each has a negated form that must **not**
fire:

    -s, --superuser      / -S, --no-superuser
    -d, --createdb       / -D, --no-createdb
    -r, --createrole     / -R, --no-createrole
        --bypassrls      /     --no-bypassrls
        --replication    /     --no-replication

Short options are matched **case-sensitively**, which is the whole reason `-S` does not read as
`-s`. Long options are matched as whole tokens, which is why `--no-superuser` does not contain a
match for `--superuser`.

**Flag tables are per-CLI, and that is load-bearing in two places.** `pg_restore -c` is
`--clean`, while `psql -c` is `--command`; and `pg_restore -S NAME` is `--superuser=NAME`, which
*names an existing superuser to disable triggers as* rather than granting anything — both read
from `--help` at source on 2026-08-26. A single flag table shared across CLIs would mis-read
`gunzip -c "$DUMP" | pg_restore …` as a `--clean` restore, on the shipped tree, today.

`createuser -g/--member-of`, `-m/--with-member` and `-a/--with-admin` grant role **membership**,
not a role attribute. They are class `role` and therefore sanctionable, matching S-069, whose
check 3 does not forbid `GRANT some_role TO x` either.

## Indirection: one literal level, and where the boundary really is

S-077 resolves one literal level of variable indirection for a SQL payload. **This module
resolves one literal level for a command name, so the two depths are the same by decision.** Two
shapes are followed, and the first matters more than the second:

1. **A path prefix, with no assignment following at all.** The command word is matched on its
   basename, so `/usr/lib/postgresql/18/bin/createuser` and `"$PG_BIN/createuser"` are caught.
   This is the shape real operations scripts use, and it needs no resolution.
2. **One literal assignment in the same file**, when the token is exactly one parameter
   expansion: `CU=createuser` (or `CU="createuser"`, or `CU='createuser -h db'`) followed by
   `$CU --superuser app`.

**Where this module deliberately differs from S-077, with the reason.** S-077's
`_literal_assignments` requires the value to be quoted. A SQL statement always contains
whitespace, so requiring quotes costs it nothing. A command name is always a single bare word, so
requiring quotes would lose `CU=createuser`, which is how shell is actually written. `_assigned`
below therefore accepts a bare token as well as the two quoted forms.
`test_the_bare_unquoted_assignment_is_followed_here_and_not_by_the_sql_guard` pins the divergence
so it stays a decision and does not decay into drift.

**Is one level enough? No, and it cannot be.** Nothing resolves `CU="$1"`, `CU=$(command -v
createuser)`, `CU="create"; CU="${CU}user"`, or `eval`. A determined author defeats this in one
keystroke: `CU=cre` then `${CU}ateuser -s app` is a valid invocation this module cannot see,
because `${CU}ateuser` is not a bare parameter expansion and nothing resolves it.
`test_the_indirection_boundary_is_where_this_module_says_it_is` plants that exact case and
asserts it is **missed**, so the boundary is a pinned fact rather than a paragraph. It also
asserts one dodge that does **not** work — `"cre""ateuser"` is caught, because `_bare` removes
quote characters before the lookup — so the list of misses is not read as longer than it is.
One level is the right depth anyway, because **this is a drift guard, not a security
boundary**: it exists so that a script gaining a privileged CLI call has to be argued for in a
sanction table, not so that it stops someone who is trying. Both existing guards have the same
property; neither of them says so.

## What this misses. Read this before trusting it

- **`bash -c "…"`, `sh -c "…"`, and `eval` are not entered.** Checks 1 and 2 see `bash` as the
  command word and stop. Check 3 does reach inside, because it reads every token in the segment.
- **A wrapper with its own options hides the command word from checks 1 and 2.** `sudo -u
  postgres createuser app` yields the command word `-u`. Check 3 still fires if a flag escalates.
- **A shell function that wraps a CLI is invisible.** This is not theoretical and it is the
  largest hole here: `scripts/supabase_local.sh:30` defines `supa() { npx --yes
  "supabase@${SUPABASE_CLI_VERSION}" … }` and `:100` runs `supa stop --no-backup`, which the
  script's own comment at `:98` describes as "`--no-backup` DELETES the Supabase database". That
  is a destructive database call, it is deliberate, and **no guard in this tree sees it**, because
  `supabase` is not a Postgres client CLI and `supa` is a function. Scoping a rule over
  non-Postgres database tooling is a separate decision.
- **`psql -f` targets are not followed, only reported.** The invocation raises `sql_file`, so the
  `cat <<EOF > /tmp/x.sql` then `psql -f /tmp/x.sql` pair S-077 names now needs a decision — but
  nothing reads `/tmp/x.sql`. That **narrows** two of S-077's items; it does not close them.
- **`psql < file` is a redirection, not a flag**, and raises nothing here or in S-077.
- **Only whole-`#` comments after a word boundary are stripped**, quote-aware. A CLI name inside
  a `'…'` string on a live line is still tokenised.
- **A binary that is not in `_CLI_RULES` is invisible**, including `alembic`, `supabase`, and any
  wrapper script. `test_every_binary_in_the_client_image_has_a_decision` only pins the image.
- **Python scripts are not swept.** `scripts/bootstrap_super_admin.py` could call `createuser`
  through `subprocess` and nothing would read it. That is S-077's first named hole and it is
  still open, for the same reason: doing it properly means an `ast` pass, which is its own seed.
- **`.github/workflows/*.yml` is not swept.** A `run:` step is a shell script by another name.
  Still open, as S-077 left it.
- **Scope is `scripts/` and `backend/scripts/`**, the same two roots as both other guards.
  `docs/ops/backup-restore.md` holds real commands inside a runbook and documentation is not
  swept.

## Why this is not an ADR

`.claude/rules/seeds.md` § "Why this is a rule here and not ADR-049" establishes the boundary:
"Every ADR in this repository decides something about the system it builds", and how this
repository verifies is `.claude/rules/` and the folder `CLAUDE.md` files. This module decides how
a check reads argv. `backend/CLAUDE.md` § Testing carries the pointer.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple

import pytest

from tests.unit.test_inline_sql_in_scripts_is_sanctioned import (
    _BARE_VAR,
    _SCRIPT_ROOTS,
    _key,
    _shell_files,
)
from tests.unit.test_scripts_sql_is_sanctioned import _ESCALATIONS

pytestmark = pytest.mark.unit

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = _BACKEND_ROOT.parent


class _Flag(NamedTuple):
    """One command-line option, in every spelling that means the same thing.

    `shorts` is matched case-sensitively against the characters of a bundled short option, so
    `createuser -S` (NO superuser) does not read as `createuser -s` (superuser).
    """

    label: str
    longs: frozenset[str]
    shorts: frozenset[str]


class _CliRule(NamedTuple):
    """What one recognised binary does, and what raises the more severe reading.

    `base` is the class when no upgrading flag is present; `""` means the invocation is silent.
    `upgraded` is the class when any flag in `on` is present.
    """

    base: str
    on: tuple[_Flag, ...] = ()
    upgraded: str = ""


_SILENT = _CliRule(base="")
_UNDECIDED = _CliRule(base="unknown")

# Read at source 2026-08-26: `docker exec familyroots-pgdb createuser --help`, image
# postgres:18-alpine, `postgres (PostgreSQL) 18.4`, the image docker-compose.yml:3 runs.
_CREATEUSER_SUPERUSER = _Flag("SUPERUSER", frozenset({"--superuser"}), frozenset({"s"}))
_CREATEUSER_CREATEDB = _Flag("CREATEDB", frozenset({"--createdb"}), frozenset({"d"}))
_CREATEUSER_CREATEROLE = _Flag("CREATEROLE", frozenset({"--createrole"}), frozenset({"r"}))
_CREATEUSER_BYPASSRLS = _Flag("BYPASSRLS", frozenset({"--bypassrls"}), frozenset())
_CREATEUSER_REPLICATION = _Flag("REPLICATION", frozenset({"--replication"}), frozenset())

# `pg_restore --help`, same image, same date: `-c, --clean` drops objects before recreating and
# `-C, --create` creates the target database. `psql --help`: `-f, --file` executes a file.
_PG_RESTORE_CLEAN = _Flag("--clean", frozenset({"--clean"}), frozenset({"c"}))
_PG_RESTORE_CREATE = _Flag("--create", frozenset({"--create"}), frozenset({"C"}))
_PSQL_FILE = _Flag("--file", frozenset({"--file"}), frozenset({"f"}))

# Every binary the client image ships, each with a class. A name absent from this table is
# invisible to the guard; a name present with `_UNDECIDED` fails until someone decides.
_CLI_RULES: dict[str, _CliRule] = {
    # Silent by decision: these read. Neither escalates nor destroys, which is the seed's
    # subject. Exfiltration is deliberately not this guard's question.
    "oid2name": _SILENT,
    "pg_amcheck": _SILENT,
    "pg_config": _SILENT,
    "pg_controldata": _SILENT,
    "pg_dump": _SILENT,
    "pg_dumpall": _SILENT,
    "pg_isready": _SILENT,
    "pg_test_fsync": _SILENT,
    "pg_test_timing": _SILENT,
    "pg_verifybackup": _SILENT,
    "pg_waldump": _SILENT,
    "pg_walsummary": _SILENT,
    # Decided.
    "createdb": _CliRule(base="database"),
    "createuser": _CliRule(base="role"),
    "dropdb": _CliRule(base="database"),
    "dropuser": _CliRule(base="role"),
    "pg_restore": _CliRule(
        base="restore", on=(_PG_RESTORE_CLEAN, _PG_RESTORE_CREATE), upgraded="database"
    ),
    "psql": _CliRule(base="", on=(_PSQL_FILE,), upgraded="sql_file"),
    # Recognised, and nobody has decided what a script may do with them.
    "clusterdb": _UNDECIDED,
    "ecpg": _UNDECIDED,
    "initdb": _UNDECIDED,
    "pg_archivecleanup": _UNDECIDED,
    "pg_basebackup": _UNDECIDED,
    "pg_checksums": _UNDECIDED,
    "pg_combinebackup": _UNDECIDED,
    "pg_createsubscriber": _UNDECIDED,
    "pg_ctl": _UNDECIDED,
    "pg_receivewal": _UNDECIDED,
    "pg_recvlogical": _UNDECIDED,
    "pg_resetwal": _UNDECIDED,
    "pg_rewind": _UNDECIDED,
    "pg_upgrade": _UNDECIDED,
    "pgbench": _UNDECIDED,
    "reindexdb": _UNDECIDED,
    "vacuumdb": _UNDECIDED,
    "vacuumlo": _UNDECIDED,
}

# Check 3, never overridable by `_SANCTIONED`. Keyed by binary because a flag letter means
# different things to different binaries — see the module docstring on `pg_restore -c`/`-S`.
_ESCALATING_FLAGS: dict[str, tuple[_Flag, ...]] = {
    "createuser": (
        _CREATEUSER_SUPERUSER,
        _CREATEUSER_CREATEDB,
        _CREATEUSER_CREATEROLE,
        _CREATEUSER_BYPASSRLS,
        _CREATEUSER_REPLICATION,
    ),
}

# The two entries in the imported `_ESCALATIONS` that no `createuser` flag can spell. Named as
# their own set rather than left out, because S-014's finding is that a guard which asks "is
# this name in the covered list" pins the list. A new entry in `_ESCALATIONS` fails
# `test_the_argv_escalation_set_and_the_sql_escalation_set_account_for_each_other` until
# somebody puts it on one side or the other.
_NO_ARGV_SPELLING = frozenset({"a grantee of PUBLIC", "WITH GRANT OPTION"})

# Read at source 2026-08-26: `docker exec familyroots-pgdb ls /usr/local/bin`, minus the image's
# own `docker-*.sh` entrypoints, `gosu`, and the `postgres` server binary. `postgres` is left
# out on purpose and it is not a style choice: `scripts/restore_drill.sh:105` assigns
# `ADMIN_DSN="postgresql://…/postgres"`, whose basename is the word `postgres`, so including it
# would fire on a connection string. `test_a_dsn_ending_in_a_database_name_is_not_an_invocation`
# pins that.
_CLIENT_IMAGE_BINARIES = frozenset(
    {
        "clusterdb",
        "createdb",
        "createuser",
        "dropdb",
        "dropuser",
        "ecpg",
        "initdb",
        "oid2name",
        "pg_amcheck",
        "pg_archivecleanup",
        "pg_basebackup",
        "pg_checksums",
        "pg_combinebackup",
        "pg_config",
        "pg_controldata",
        "pg_createsubscriber",
        "pg_ctl",
        "pg_dump",
        "pg_dumpall",
        "pg_isready",
        "pg_receivewal",
        "pg_recvlogical",
        "pg_resetwal",
        "pg_restore",
        "pg_rewind",
        "pg_test_fsync",
        "pg_test_timing",
        "pg_upgrade",
        "pg_verifybackup",
        "pg_waldump",
        "pg_walsummary",
        "pgbench",
        "psql",
        "reindexdb",
        "vacuumdb",
        "vacuumlo",
    }
)

_CLASSES = frozenset(
    {rule.base for rule in _CLI_RULES.values() if rule.base}
    | {rule.upgraded for rule in _CLI_RULES.values() if rule.upgraded}
)


class _Sanction(NamedTuple):
    """What one shell script may invoke, and who said so."""

    classes: frozenset[str]
    decisions: tuple[str, ...]
    why: str


_SANCTIONED: dict[str, _Sanction] = {
    "scripts/restore_drill.sh": _Sanction(
        classes=frozenset({"restore", "sql_file"}),
        decisions=(
            "docs/ops/backup-restore.md",
            "docs/decisions/052-restore-bootstraps-the-request-role.md",
        ),
        why=(
            "restore: the drill exists to prove a backup restores, so pg_restore is the "
            "script. It runs at :130 against SCRATCH_DSN, never against production; "
            "docs/ops/backup-restore.md:91-92 names the one scratch database it targets. It "
            "carries neither --clean nor --create, so it is class restore and not database: "
            "the drop and the create are done at :116 and :122 through psql -c, which is "
            "S-077's guard's subject, not this one's. sql_file: :149 runs "
            "scripts/restore_bootstrap_role.sql, whose nine statements are S-069's guard's "
            "subject; ADR-052 section 1 is the decision that the role and its grants have to "
            "be replayed outside the Alembic chain after a restore. It is sanctioned for "
            "nothing else. A createuser, a dropdb, or a pg_restore --clean added here fails "
            "check 2, and any createuser attribute flag fails check 3, which no entry in "
            "this table can override."
        ),
    ),
}

_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

# Words that stand in front of a command without being one. `if`/`!`/`then` matter on the
# shipped tree: `scripts/restore_drill.sh:116` reads `if ! psql …`.
_TRANSPARENT = frozenset(
    {
        "!",
        "builtin",
        "command",
        "do",
        "doas",
        "elif",
        "else",
        "env",
        "eval",
        "exec",
        "if",
        "nice",
        "nohup",
        "then",
        "time",
        "until",
        "while",
        "xargs",
        "sudo",
    }
)


class _Invocation(NamedTuple):
    """One recognised CLI call: where it is, which binary, what class, and its whole segment."""

    line: int
    cli: str
    cls: str
    tokens: tuple[str, ...]


def _logical_lines(text: str) -> list[tuple[int, str]]:
    """Join backslash continuations, keeping the 1-based line the invocation starts on.

    `scripts/restore_drill.sh:193-194`, `:201-202` and `:220-223` all put the flags on a
    continuation of the line that names the binary, so a scanner working physical line by
    physical line would read the wrong flag set for three real invocations.
    """
    raw = text.splitlines()
    out: list[tuple[int, str]] = []
    i = 0
    while i < len(raw):
        start = i
        buf = raw[i]
        while buf.rstrip().endswith("\\") and i + 1 < len(raw):
            i += 1
            buf = buf.rstrip()[:-1] + " " + raw[i]
        out.append((start + 1, buf))
        i += 1
    return out


def _segments(line: str) -> list[str]:
    """Split one logical line where the shell would start a new command, quote-aware.

    Quote tracking is not decoration. `scripts/restore_drill.sh:193` passes `-F'|'`, and a
    naive split on `|` would cut that invocation in half and read the wrong flags. `$(` and a
    backtick open a command even inside double quotes, which is how `person_row="$(psql …"`
    gets read at all. An unquoted `#` at a word boundary ends the logical line, which is what
    keeps the trailing comments at `:219` and `:225` out.
    """
    out: list[str] = []
    buf: list[str] = []
    single = double = False
    at_word_start = True
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == "\\" and not single:
            buf.append(line[i : i + 2])
            i += 2
            at_word_start = False
            continue
        if ch == "'" and not double:
            single = not single
        elif ch == '"' and not single:
            double = not double
        elif not single and ch == "$" and line[i : i + 2] == "$(":
            out.append("".join(buf))
            buf = []
            i += 2
            at_word_start = True
            continue
        elif not single and ch == "`":
            out.append("".join(buf))
            buf = []
            i += 1
            at_word_start = True
            continue
        elif not single and not double:
            if ch == "#" and at_word_start:
                break
            if ch in "|&;()":
                out.append("".join(buf))
                buf = []
                i += 1
                at_word_start = True
                continue
        buf.append(ch)
        at_word_start = ch.isspace()
        i += 1
    out.append("".join(buf))
    return out


def _bare(token: str) -> str:
    """Remove every quote character from a token. `-F'|'` becomes `-F|`, `"$X"` becomes `$X`."""
    return token.replace('"', "").replace("'", "")


def _assigned(text: str, name: str) -> list[str]:
    """Every literal value assigned to `name` in `text`: quoted, or a bare single word.

    The bare form is where this module differs from S-077's `_literal_assignments`, and the
    reason is in the module docstring: a SQL payload always has whitespace, so requiring
    quotes costs that scanner nothing, while a command name never does, so requiring quotes
    here would lose `CU=createuser`.
    """
    pattern = re.compile(
        rf"(?:^|\s){re.escape(name)}=(\"(?:[^\"\\]|\\.)*\"|'[^']*'|[^\s;|&()]+)", re.DOTALL
    )
    return [_bare(m.group(1)) for m in pattern.finditer(text)]


def _resolve(token: str, text: str) -> list[str]:
    """Resolve one token to the words it stands for: itself, or one literal assignment level."""
    stripped = _bare(token)
    var = _BARE_VAR.match(stripped)
    if var is None:
        return [stripped]
    return [word for value in _assigned(text, var.group(1)) for word in value.split()]


def _basename(token: str) -> str:
    return token.rsplit("/", 1)[-1]


def _has_flag(tokens: tuple[str, ...], flag: _Flag) -> bool:
    """Whether `flag` appears among `tokens`, long as a whole token, short case-sensitively."""
    for token in tokens:
        if token in flag.longs or any(token.startswith(f"{long}=") for long in flag.longs):
            return True
        bundled = len(token) > 1 and token[0] == "-" and token[1] != "-"
        if flag.shorts and bundled and set(token[1:]) & flag.shorts:
            return True
    return False


def _command_word(tokens: tuple[str, ...]) -> str | None:
    """The first token that is a command rather than a prefix of one."""
    for token in tokens:
        if not token or _ASSIGNMENT.match(token) or token in _TRANSPARENT:
            continue
        return token
    return None


def _invocations(text: str) -> list[_Invocation]:
    """Every recognised CLI call in command position, with the class its flags earn it."""
    out: list[_Invocation] = []
    for line, logical in _logical_lines(text):
        for segment in _segments(logical):
            tokens = tuple(word for raw in segment.split() for word in _resolve(raw, text) if word)
            word = _command_word(tokens)
            if word is None:
                continue
            cli = _basename(word)
            rule = _CLI_RULES.get(cli)
            if rule is None:
                continue
            cls = rule.upgraded if any(_has_flag(tokens, f) for f in rule.on) else rule.base
            if cls:
                out.append(_Invocation(line, cli, cls, tokens))
    return out


def _escalations(text: str) -> list[tuple[int, str, str]]:
    """Check 3's wider reach: `(line, cli, label)` for every escalating flag in any segment.

    This reads every token rather than only the command word, so a wrapper does not hide the
    call. See the module docstring on why the two questions get two reaches.
    """
    out: list[tuple[int, str, str]] = []
    for line, logical in _logical_lines(text):
        for segment in _segments(logical):
            tokens = tuple(word for raw in segment.split() for word in _resolve(raw, text) if word)
            names = {_basename(t) for t in tokens} & set(_ESCALATING_FLAGS)
            out += [
                (line, cli, flag.label)
                for cli in sorted(names)
                for flag in _ESCALATING_FLAGS[cli]
                if _has_flag(tokens, flag)
            ]
    return out


def _scanned() -> list[tuple[str, _Invocation]]:
    return [(_key(p), inv) for p in _shell_files() for inv in _invocations(p.read_text())]


def test_every_script_that_invokes_a_privileged_cli_is_named_in_the_sanction_table() -> None:
    """Check 1: a script that runs `pg_restore` or `dropdb` must be named by a decision.

    A script whose only Postgres call reads — `pg_dump`, `pg_isready`, a `psql` without `-f` —
    raises nothing and needs no entry. That is where the false-positive budget goes, and it is
    why `scripts/db_backup.sh` is absent from the table.
    """
    offences = [
        f"{key}:{inv.line} invokes {inv.cli} ({inv.cls})"
        for key, inv in _scanned()
        if key not in _SANCTIONED
    ]
    assert offences == [], "\n".join(
        [
            "These shell scripts invoke a Postgres client CLI that no decision sanctions:",
            *offences,
            "A client CLI needs no SQL text to escalate privilege or destroy a database: "
            "`createuser --superuser familyroots_app` does what `ALTER ROLE … SUPERUSER` does "
            "and no SQL scanner can see it. The Alembic chain in backend/migrations/ owns the "
            "schema and the policy set (docs/ops/migrations.md, ADR-008, ADR-043), and "
            "scripts/restore_bootstrap_role.sql owns the request role and its grants "
            "(ADR-052). If this script genuinely must make this call, write the decision that "
            "says why, then add the script to _SANCTIONED with the narrowest set of classes "
            "that decision covers.",
        ]
    )


def test_no_sanctioned_script_invokes_a_class_its_decisions_did_not_cover() -> None:
    """Check 2: being on the allow-list is not a blank cheque.

    `unknown` is in no sanctioned set, so a binary nobody has decided about fails here rather
    than passing by omission.
    """
    offences: list[str] = []
    for key, inv in _scanned():
        sanction = _SANCTIONED.get(key)
        if sanction is None:
            continue  # Check 1 owns this script.
        if inv.cls not in sanction.classes:
            offences.append(
                f"{key}:{inv.line} invokes {inv.cli} as {inv.cls}, which "
                f"{' and '.join(sanction.decisions)} does not sanction "
                f"(allowed: {', '.join(sorted(sanction.classes))})"
            )
    assert offences == [], "\n".join(
        ["A sanctioned script invokes a CLI outside its decisions:", *offences]
    )


def test_no_script_invokes_a_cli_that_confers_an_escalating_role_attribute() -> None:
    """Check 3: never overridable by `_SANCTIONED`, in any script, ever.

    This is the check S-079's planted controls fail. `createuser --superuser familyroots_app`
    hands the application role every clan's rows and switches off row-level security for every
    request the application makes, on any database it is run against, with no SQL text anywhere
    for the other two guards to read.
    """
    offences = [
        f"{key}:{line} runs {cli} with a flag that confers {label}"
        for path in _shell_files()
        for key in [_key(path)]
        for line, cli, label in _escalations(path.read_text())
    ]
    assert offences == [], "\n".join(
        [
            "These scripts invoke a client CLI that defeats the isolation model:",
            *offences,
            "No decision sanctions any of these, and _SANCTIONED cannot override this check. "
            "The request role is NOBYPASSRLS by design (ADR-052; "
            "scripts/restore_bootstrap_role.sql:34) — RLS layer-2 (ADR-008) means nothing "
            "against a role that bypasses it. This is the same set of attributes "
            "test_scripts_sql_is_sanctioned.py forbids in SQL text; the only difference is "
            "that here they are spelled as command-line flags.",
        ]
    )


def test_the_sweep_reaches_files_and_finds_an_invocation() -> None:
    """A scanner that silently matched nothing would make all three checks vacuous."""
    assert any(root.is_dir() for root in _SCRIPT_ROOTS), (
        f"None of {[str(r) for r in _SCRIPT_ROOTS]} exists; the checks above mean nothing"
    )
    assert _shell_files(), (
        "No shell script found under any scripts/ root. If that is now correct, delete this "
        "module rather than leaving three sweeps that can never fail."
    )
    assert _scanned(), (
        "No Postgres client CLI invocation extracted from any shell script under a scripts/ "
        "root. Either scripts/restore_drill.sh:130 has gone, or the scanner has stopped "
        "seeing the shapes it reads. Check that line first."
    )


def test_the_scanner_reads_the_real_drill_as_one_restore_and_one_sql_file() -> None:
    """The measurement this module rests on, re-taken by the test on every run.

    Verified by hand 2026-08-26: `scripts/restore_drill.sh` invokes `pg_restore` at `:130`
    with neither `--clean` nor `--create`, and `psql -f` at `:149`. Every other `psql` call in
    the file carries `-c` or nothing and is silent here, because its SQL is
    `test_inline_sql_in_scripts_is_sanctioned.py`'s subject. Asserting the exact list rather
    than a subset is what stops an extractor regression from passing while reading half the
    file — and it is what keeps the `echo "==> pg_restore completed"` at `:131` from being
    counted as an invocation.
    """
    path = _REPO_ROOT / "scripts" / "restore_drill.sh"
    assert path.is_file(), f"{path} is missing; docs/ops/backup-restore.md:81 requires it"
    found = [(inv.line, inv.cli, inv.cls) for inv in _invocations(path.read_text())]
    assert found == [(130, "pg_restore", "restore"), (149, "psql", "sql_file")], found


def test_the_backup_script_is_silent_because_pg_dump_reads() -> None:
    """`pg_dump` is silent by decision, and this is the invocation that decision covers.

    `scripts/db_backup.sh:40` pipes a custom-format dump into gzip. It neither escalates nor
    destroys, which is this guard's subject, so the script needs no sanction entry. If anyone
    later gives `pg_dump` a class — for exfiltration, say, which this guard does not judge —
    this test fails and tells them `db_backup.sh` needs an entry in the same change.
    """
    path = _REPO_ROOT / "scripts" / "db_backup.sh"
    assert path.is_file(), f"{path} is missing; .github/workflows/db-backup.yml runs it"
    text = path.read_text()
    assert "pg_dump --format=custom" in text, (
        "db_backup.sh no longer runs pg_dump; this test is pinning a line that has moved"
    )
    assert _invocations(text) == [], _invocations(text)
    assert _key(path) not in _SANCTIONED, "a silent script must not carry a sanction entry"


def test_a_dsn_ending_in_a_database_name_is_not_an_invocation() -> None:
    """A measured near-miss on the shipped tree, pinned so it stays fixed.

    `scripts/restore_drill.sh:105` assigns
    `ADMIN_DSN="postgresql://…:…@…:…/postgres"`. The basename of that token is the word
    `postgres`, so a `_CLI_RULES` table that included the server binary would report a CLI
    invocation on a connection string. The `-d "$SCRATCH_DSN"` on the real `pg_restore` line
    resolves through `_assigned` to the same shape.
    """
    assert "postgres" not in _CLI_RULES, (
        "`postgres` is the server binary, not a client CLI, and its name is the tail of every "
        "DSN in scripts/restore_drill.sh"
    )
    script = 'ADMIN_DSN="postgresql://u:p@h:5432/postgres"\npg_restore -d "$ADMIN_DSN" f.dump'
    assert [(i.cli, i.cls) for i in _invocations(script)] == [("pg_restore", "restore")]


def test_every_binary_in_the_client_image_has_a_decision() -> None:
    """Default-deny at the level of the name, not only of the statement.

    Read at source 2026-08-26: `docker exec familyroots-pgdb ls /usr/local/bin` on
    `postgres:18-alpine`, `postgres (PostgreSQL) 18.4`. A Postgres upgrade that ships a new
    client binary fails here until somebody classifies it, rather than the new binary being
    silently invisible.
    """
    undecided = sorted(_CLIENT_IMAGE_BINARIES - set(_CLI_RULES))
    assert undecided == [], (
        f"These binaries ship in the client image and no rule classifies them: {undecided}. "
        "Add each to _CLI_RULES: `_SILENT` if it only reads, `_UNDECIDED` if nobody has "
        "decided, or a class if there is a decision."
    )
    stale = sorted(set(_CLI_RULES) - _CLIENT_IMAGE_BINARIES)
    assert stale == [], (
        f"_CLI_RULES names binaries the image does not ship: {stale}. Re-read "
        "`docker exec familyroots-pgdb ls /usr/local/bin` and re-date the comment."
    )


def test_the_argv_escalation_set_and_the_sql_escalation_set_account_for_each_other() -> None:
    """The symmetry this seed exists for, made machine-checked rather than claimed.

    S-069's `_ESCALATIONS` forbids seven things in SQL text. Five of them are role attributes
    `createuser` can set with a flag, and this module forbids those five flags. Two —
    a grantee of `PUBLIC` and `WITH GRANT OPTION` — have no `createuser` spelling at all and
    are named in `_NO_ARGV_SPELLING`.

    The assertion is an equality over the union, not a subset check. That is S-014's finding
    applied here: a subset check would pass silently when a new entry is added to
    `_ESCALATIONS`, pinning the list this module happens to cover instead of the coverage.
    """
    sql_labels = {label for label, _ in _ESCALATIONS}
    argv_labels = {flag.label for flags in _ESCALATING_FLAGS.values() for flag in flags}
    assert argv_labels <= sql_labels, (
        f"These argv labels name nothing in _ESCALATIONS: {sorted(argv_labels - sql_labels)}. "
        "Use the label the SQL guard already uses, so one attribute reads the same in both."
    )
    assert argv_labels | _NO_ARGV_SPELLING == sql_labels, (
        "A privilege the SQL guard forbids is on neither side here: "
        f"{sorted(sql_labels - (argv_labels | _NO_ARGV_SPELLING))}. Decide whether a client "
        "CLI can confer it. If a flag spells it, add the flag to _ESCALATING_FLAGS. If none "
        "does, add the label to _NO_ARGV_SPELLING and say why. Do not widen the subset check."
    )
    assert not argv_labels & _NO_ARGV_SPELLING, (
        "A label cannot both have an argv spelling and not have one: "
        f"{sorted(argv_labels & _NO_ARGV_SPELLING)}"
    )


def test_the_sanction_table_is_not_a_list_of_names_nobody_reads() -> None:
    """A stale entry is a blank cheque waiting for a future script to reuse the name."""
    missing = [k for k in _SANCTIONED if not (_REPO_ROOT / k).is_file()]
    assert missing == [], (
        f"_SANCTIONED names scripts that do not exist: {missing}. Delete the entry in the "
        "same change that deletes the script."
    )
    unused = [k for k in _SANCTIONED if not any(key == k for key, _ in _scanned())]
    assert unused == [], (
        f"_SANCTIONED names scripts that invoke nothing this guard reads: {unused}. An entry "
        "that covers no invocation permits nothing and hides the real hole."
    )


@pytest.mark.parametrize("key", sorted(_SANCTIONED))
def test_every_sanction_cites_decisions_that_exist_and_name_the_script(key: str) -> None:
    """The citation must be load-bearing, not a path that merely resolves.

    Requiring each cited document to contain the script's own path is as far as a mechanical
    check goes. It does not establish that the document sanctions these classes; only a reader
    does. A human read `docs/ops/backup-restore.md:91-92` and ADR-052 section 1 on 2026-08-26,
    and they cover the scratch database and the role replay respectively.
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
    assert sanction.classes <= _CLASSES, (
        f"{key} names a class the scanner cannot produce: "
        f"{sorted(sanction.classes - _CLASSES)}. A sanction for a class that never gets "
        "assigned silently permits nothing and hides the real hole."
    )


@pytest.mark.parametrize(
    ("expected", "script"),
    [
        # The plain forms, with no SQL text anywhere for the other guards to read.
        ([("createuser", "role")], "createuser familyroots_app"),
        ([("dropuser", "role")], "dropuser familyroots_app"),
        ([("createdb", "database")], "createdb family_roots"),
        ([("dropdb", "database")], "dropdb --force family_roots"),
        # An absolute path, and a path through a variable. Neither needs assignment following.
        ([("createuser", "role")], "/usr/lib/postgresql/18/bin/createuser app"),
        ([("createuser", "role")], 'PG_BIN=/usr/bin\n"$PG_BIN/createuser" app'),
        # A leading assignment is a prefix, not a command.
        ([("dropdb", "database")], 'PGPASSWORD="x" dropdb scratch'),
        # `if ! …` is the shape scripts/restore_drill.sh:116 uses.
        ([("dropdb", "database")], "if ! dropdb scratch; then exit 1; fi"),
        # After a pipe, which is how pg_restore is reached at :130.
        ([("pg_restore", "restore")], 'gunzip -c "$D" | pg_restore -d "$DSN"'),
        # Inside a command substitution, which is how every psql read at :157+ is reached.
        ([("psql", "sql_file")], 'out="$(psql "$DSN" -f setup.sql)"'),
        # pg_restore's own flags, whose short letters mean something else to psql.
        ([("pg_restore", "database")], 'pg_restore --clean -d "$DSN" f.dump'),
        ([("pg_restore", "database")], 'pg_restore -c -d "$DSN" f.dump'),
        ([("pg_restore", "database")], 'pg_restore -C -d "$DSN" f.dump'),
        ([("pg_restore", "database")], 'pg_restore --create -d "$DSN" f.dump'),
        # psql's file flag, long, short, bundled and with an `=`.
        ([("psql", "sql_file")], 'psql "$DSN" -f x.sql'),
        ([("psql", "sql_file")], 'psql "$DSN" --file x.sql'),
        ([("psql", "sql_file")], 'psql "$DSN" --file=x.sql'),
        ([("psql", "sql_file")], 'psql "$DSN" -qf x.sql'),
        # A recognised binary nobody has decided about is `unknown`, never sanctionable.
        ([("initdb", "unknown")], "initdb -D /var/lib/postgresql/data"),
        ([("vacuumdb", "unknown")], "vacuumdb --all"),
        ([("pg_ctl", "unknown")], "pg_ctl restart"),
        # One literal assignment level, in all three spellings this module accepts.
        ([("createuser", "role")], "CU=createuser\n$CU app"),
        ([("createuser", "role")], 'CU="createuser"\n$CU app'),
        ([("dropdb", "database")], "DD='dropdb'\n${DD} scratch"),
    ],
)
def test_the_scanner_finds_the_invocation_shapes_it_is_given(
    expected: list[tuple[str, str]], script: str
) -> None:
    assert [(i.cli, i.cls) for i in _invocations(script)] == expected


@pytest.mark.parametrize(
    "script",
    [
        # Silent by decision: these read.
        'pg_dump --format=custom --no-owner "$URL" | gzip > out.gz',
        "pg_dumpall --roles-only",
        'pg_isready -h "$PGHOST"',
        # A psql with no `-f` is S-077's subject, not this module's.
        'psql "$DSN" -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS x WITH (FORCE)"',
        'psql "$DSN" -tAc "SELECT 1"',
        # `-F` is not `-f`: psql's field separator, on the real line at :193.
        'psql "$DSN" -tA -F\'|\' -c "SELECT id FROM persons LIMIT 1"',
        # A whole-line comment is prose, including one that quotes a real command.
        "# createuser --superuser familyroots_app",
        '  # dropdb "$SCRATCH_DB" would destroy it',
        # A trailing comment on a live line, which is the shape at :219 and :225.
        "app_role_persons() {  # $1 = uuid. Prints psql output; last line = count.",
        "first_error() {  # $1 = psql output. Prints the first ERROR line.",
        # Words that merely look like flags or binaries.
        "gunzip -c dump.gz > dump",
        "echo hello | grep -c .",
        'echo "==> pg_dump (custom format) -> ${DUMP_PATH}"',
        # A connection string whose last path element is a database name.
        'ADMIN_DSN="postgresql://u:p@localhost:5432/postgres"',
        "",
    ],
)
def test_the_scanner_reports_nothing_for_lines_that_invoke_nothing_privileged(
    script: str,
) -> None:
    assert _invocations(script) == []


@pytest.mark.parametrize(
    ("label", "script"),
    [
        # The five attributes, long form.
        ("SUPERUSER", "createuser --superuser familyroots_app"),
        ("CREATEDB", "createuser --createdb familyroots_app"),
        ("CREATEROLE", "createuser --createrole familyroots_app"),
        ("BYPASSRLS", "createuser --bypassrls familyroots_app"),
        ("REPLICATION", "createuser --replication familyroots_app"),
        # Short forms, alone and bundled with unrelated letters.
        ("SUPERUSER", "createuser -s familyroots_app"),
        ("SUPERUSER", "createuser -sPl familyroots_app"),
        ("CREATEDB", "createuser -d familyroots_app"),
        ("CREATEROLE", "createuser -r familyroots_app"),
        # Reached through the wrappers checks 1 and 2 cannot see past.
        ("SUPERUSER", "sudo -u postgres createuser -s familyroots_app"),
        ("SUPERUSER", 'bash -c "createuser --superuser familyroots_app"'),
        # Reached through one literal assignment level, bare and quoted.
        ("SUPERUSER", "CU=createuser\n$CU --superuser familyroots_app"),
        ("SUPERUSER", 'CU="createuser"\n$CU -s familyroots_app'),
        # Reached through a path.
        ("SUPERUSER", "/usr/lib/postgresql/18/bin/createuser -s familyroots_app"),
        # On a backslash continuation of the line that names the binary.
        ("SUPERUSER", 'createuser -h "$PGHOST" \\\n  --superuser familyroots_app'),
    ],
)
def test_check_three_fires_on_every_spelling_of_an_escalating_flag(label: str, script: str) -> None:
    assert [found for _, _, found in _escalations(script)] == [label]


@pytest.mark.parametrize(
    "script",
    [
        # The negated forms. Short options are case-sensitive, which is the whole point:
        # `-S` is --no-superuser, `-D` is --no-createdb, `-R` is --no-createrole.
        "createuser --no-superuser --no-createdb --no-createrole familyroots_app",
        "createuser --no-bypassrls --no-replication familyroots_app",
        "createuser -SDR familyroots_app",
        # Role membership is class `role` and sanctionable, not an attribute. S-069's check 3
        # does not forbid `GRANT some_role TO x` either.
        "createuser --member-of app_readers reporter",
        "createuser -g app_readers -m reporter -a admin newrole",
        # A plain createuser escalates nothing by itself; check 1 owns it.
        "createuser familyroots_app",
        # pg_restore's `-S`/`--superuser` names an existing superuser and grants nothing.
        'pg_restore -S postgres -d "$DSN" f.dump',
        'pg_restore --superuser=postgres --clean -d "$DSN" f.dump',
        # A whole-line comment naming the flag is prose.
        "# never run createuser --superuser familyroots_app",
        # Another binary's `-s` means something else entirely.
        'pg_restore -s -d "$DSN" f.dump',
        "psql \"$DSN\" -c 'SELECT 1' -s",
        "",
    ],
)
def test_check_three_refuses_lines_that_confer_no_attribute(script: str) -> None:
    assert _escalations(script) == []


def test_the_indirection_boundary_is_where_this_module_says_it_is() -> None:
    """One literal level, and the shapes past it are missed. Pinned, not described.

    A limitation stated only in prose drifts. Asserting the miss means that anyone who deepens
    the resolver has to come here and change the claim in the same edit, and anyone reading
    the guard can see exactly how far it reaches.
    """
    caught = "CU=createuser\n$CU --superuser app"
    assert [label for _, _, label in _escalations(caught)] == ["SUPERUSER"]

    # Composed at run time: the assignment value is not a literal command name.
    composed = 'CU="create"\nCU="${CU}user"\n$CU --superuser app'
    assert _escalations(composed) == [], "the resolver now goes deeper than one level"

    # From an argument, from the environment, and from a subshell.
    assert _escalations('CU="$1"\n$CU --superuser app') == []
    assert _escalations('CU="${CREATEUSER_BIN}"\n$CU --superuser app') == []
    assert _escalations('CU="$(command -v createuser)"\n$CU --superuser app') == []

    # Concatenation with a suffix: `${CU}ateuser` is not a bare parameter expansion, so
    # nothing resolves it. One keystroke, and nothing in this tree can see it. This module is
    # a drift guard, not a security boundary.
    assert _escalations("CU=cre\n${CU}ateuser --superuser app") == []

    # Splitting the name across string literals does NOT work as a dodge, because `_bare`
    # removes quote characters before the lookup. Asserted as a positive, so nobody reads the
    # misses above as a longer list than they are.
    assert [label for _, _, label in _escalations('"cre""ateuser" --superuser app')] == [
        "SUPERUSER"
    ]


def test_the_bare_unquoted_assignment_is_followed_here_and_not_by_the_sql_guard() -> None:
    """The one deliberate divergence from S-077's resolver, pinned so it stays deliberate.

    S-077 requires an assignment value to be quoted, which costs a SQL scanner nothing because
    a statement always contains whitespace. A command name never does, so this module accepts
    a bare token too. If someone unifies the two resolvers, this test says which behaviour was
    chosen on purpose and why.
    """
    from tests.unit.test_inline_sql_in_scripts_is_sanctioned import _literal_assignments

    script = "CU=createuser\n$CU --superuser app"
    assert _literal_assignments(script, "CU") == []
    assert _assigned(script, "CU") == ["createuser"]
    assert _assigned('CU="createuser"', "CU") == ["createuser"]
    assert _assigned("CU='createuser'", "CU") == ["createuser"]
