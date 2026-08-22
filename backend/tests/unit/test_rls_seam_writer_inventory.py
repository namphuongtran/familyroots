"""Pin every place in `app/` that writes a Postgres session setting.

Seed S-045, the third guard beside `tests/integration/test_rls_seam_settings_pinned.py`.

The runtime pin asserts the exact set of settings a request transaction carries. It can
only see writers on the paths it drives. This one reads the source instead, so a **third**
writer added on a path no test exercises still fails the suite — which matters here,
because the seam already turned out to have two writers when
[ADR-047](../../../docs/decisions/047-rls-seam-sets-clan-id-only.md) Measurement 3 looked,
and seed S-040's own text had named only one.

Confirmed at source on 2026-08-22, in this worktree:

* `app/core/rls.py:63` — `connection.exec_driver_sql(f"SET LOCAL ROLE {role}")`
* `app/core/rls.py:65` — `connection.exec_driver_sql(
  "SELECT set_config('app.clan_id', %s, true)", (clan,))`
* `app/core/security.py:290` — `await db.execute(
  select(func.set_config("app.clan_id", str(resolved_clan_id), True)))`

Scope: `app/**/*.py` only. Migrations are not scanned — every `current_setting('app.clan_id')`
in `migrations/versions/` is a policy *reading* the GUC, never a writer (ADR-047
Measurement 2). Docstrings are excluded on purpose: `app/core/rls.py` and
`app/core/database.py` both quote `SET LOCAL ROLE` in prose describing this very seam, and
a guard that counted prose would fire on a comment edit and teach the next agent to ignore it.
The two foreign-key referential actions, `SET NULL` and `SET DEFAULT`, are excluded for the
same reason: ten models declare one and none of them is a statement.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

APP_ROOT = Path(__file__).resolve().parents[2] / "app"

# What the seam is allowed to write, one entry per call site, sorted. Changing this list is
# a deliberate act: it means ADR-008 § 2 and ADR-047 no longer describe the shipped seam,
# so amend them in the same change.
EXPECTED_WRITERS = [
    "app/core/rls.py: SET LOCAL ROLE",
    "app/core/rls.py: set_config('app.clan_id')",
    "app/core/security.py: set_config('app.clan_id')",
]

# A string that IS a statement changing session state. Anchored at the start so prose that
# merely mentions "SET ROLE" mid-sentence is not a writer.
_SET_STATEMENT_RE = re.compile(r"(?i)^(set|reset)\s")
# `ondelete="SET NULL"` is a foreign-key referential action, not a statement. Ten models
# declare one. Only the two exact spellings are excluded, so `SET LOCAL app.x = NULL`
# — a real writer — is still caught.
_FK_ACTIONS = {"set null", "set default"}
# The GUC name is the first argument of set_config, whichever form the call takes.
_SET_CONFIG_IN_SQL_RE = re.compile(r"set_config\s*\(\s*'([^']*)'")


def _docstring_constants(tree: ast.AST) -> set[int]:
    """Ids of string constants that are bare expression statements, i.e. docstrings."""
    return {
        id(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    }


def _call_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _writers_in(path: Path, rel: str) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    skip = _docstring_constants(tree)
    found: list[str] = []

    for node in ast.walk(tree):
        # 1. A raw SQL string, including the leading chunk of an f-string.
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip:
            text = node.value.strip()
            if _SET_STATEMENT_RE.match(text) and text.lower() not in _FK_ACTIONS:
                found.append(f"{rel}: {' '.join(text.split())}")
            for guc in _SET_CONFIG_IN_SQL_RE.findall(node.value):
                found.append(f"{rel}: set_config('{guc}')")
        # 2. A set_config(...) call built through SQLAlchemy rather than as SQL text.
        elif isinstance(node, ast.Call) and _call_name(node) == "set_config":
            first = node.args[0] if node.args else None
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                found.append(f"{rel}: set_config('{first.value}')")
            else:
                found.append(f"{rel}: set_config(<not a literal>)")

    return found


def test_only_the_two_known_writers_set_a_postgres_setting() -> None:
    """A third writer, or a second GUC name, fails here even with no test driving it.

    ADR-047 § "What a later seed must establish before adding `app.user_id`" requires a
    seed to change **both** writers plus the teardown clear. This assertion is where that
    requirement becomes mechanical: the list below is the whole inventory.
    """
    actual = sorted(
        writer
        for path in sorted(APP_ROOT.rglob("*.py"))
        for writer in _writers_in(path, path.relative_to(APP_ROOT.parent).as_posix())
    )
    assert actual == EXPECTED_WRITERS, (
        "the inventory of Postgres-setting writers in app/ changed.\n"
        f"expected: {EXPECTED_WRITERS}\nfound:    {actual}\n"
        "If this is deliberate, ADR-008 § 2 and ADR-047 describe the seam and must be "
        "amended in the same change."
    )


def test_the_guard_would_notice_a_new_writer(tmp_path: Path) -> None:
    """The scanner itself, proven on a synthetic module rather than trusted.

    Without this, a scanner that silently matched nothing would keep the test above green
    forever — the same 'a green gate is not evidence' failure that S-045 exists to close.
    """
    module = (
        '"""Docstring mentioning SET LOCAL app.decoy = 1 and set_config(\'app.decoy\').\n'
        "\n"
        "Prose that says SET ROLE mid-sentence must not count either.\n"
        '"""\n'
        'fk = ForeignKey("clans.id", ondelete="SET NULL")\n'
        "conn.exec_driver_sql(\"SET LOCAL app.probe = 'x'\")\n"
        "conn.exec_driver_sql(\"SELECT set_config('app.other', %s, true)\", (v,))\n"
        'db.execute(select(func.set_config("app.third", "v", True)))\n'
        "db.execute(select(func.set_config(name, 'v', True)))\n"
    )
    probe = tmp_path / "synthetic.py"
    probe.write_text(module, encoding="utf-8")

    # The docstring's SET LOCAL and set_config, and the ondelete="SET NULL", are absent.
    assert sorted(_writers_in(probe, "synthetic.py")) == [
        "synthetic.py: SET LOCAL app.probe = 'x'",
        "synthetic.py: set_config('app.other')",
        "synthetic.py: set_config('app.third')",
        "synthetic.py: set_config(<not a literal>)",
    ]
