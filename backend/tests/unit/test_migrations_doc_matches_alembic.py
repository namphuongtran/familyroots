"""Fail when `docs/ops/migrations.md` and the Alembic chain on disk disagree.

Seed S-063. On `main` at `62a863d`, `docs/ops/migrations.md:119` read
"Head = `035_rls_clan_settings`" while `backend/migrations/versions/036_rls_user_clan_roles.py`
had already landed a batch earlier. Seed S-052 shipped that migration and did not update the
document, and nothing caught it — including the coordinator, who merged it. The shape is the one
this repository keeps meeting: two places record the same fact, only one of them is executable,
and the other is what an agent reads first.

**Which shape this check takes, and why.** The seed offered two: derive the doc's list from
Alembic and fail on any difference, or assert the head only. This is the first, the stronger one.
Asserting the head alone would have caught the `62a863d` drift, because the head moved too — but
it would pass a document that names the right head and drops a revision in the middle, and the
"Current chain" block is what an agent reads to learn what the schema went through.

**Nothing here is hardcoded, on purpose.** Both sides are derived at run time: the expected chain
comes from `alembic.script.ScriptDirectory`, and the claimed chain comes from parsing the
document. A revision added by anyone — including another agent in the same batch, which is
exactly what happens while this lands — needs no edit here. The check simply starts requiring the
document to name it.

**Alembic, not the filenames.** `ScriptDirectory` walks `down_revision` links, so a file that
exists in `versions/` but hangs off nothing is not in the chain, and the order is the real one
rather than lexical. `test_the_alembic_chain_has_exactly_one_head` pins the document's own
"Single linear chain (no branches)" claim.

**On parser fragility.** A parser that silently matches nothing would be worse than no gate: it
would go green forever. Three things stop that here. The extractor raises when the
`## Current chain` heading is absent, raises when the block yields no revision, and raises when
the `Head = ` line is missing or appears more than once. It also does no filtering — *every*
backticked token inside the chain block is taken as a claimed revision, so a stray backticked
word in that block fails the check rather than being skipped. Two further tests,
`test_the_extractor_reads_a_chain_it_is_given` and
`test_the_extractor_refuses_a_document_with_no_chain_section`, exercise the extractor against
synthetic documents, so its ability to both match and refuse is pinned independently of what the
real document currently says.

Out of scope: any migration's content. `infra/supabase/migrations/`, the hand-written parallel
set this docstring used to exclude, no longer exists — seed S-064 deleted it on 2026-08-22, and
`test_no_parallel_table_ddl_under_infra.py` keeps it from coming back.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

pytestmark = pytest.mark.unit

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = _BACKEND_ROOT.parent
_MIGRATIONS_DOC = _REPO_ROOT / "docs" / "ops" / "migrations.md"
_VERSIONS_DIR = _BACKEND_ROOT / "migrations"

_CHAIN_HEADING = "## Current chain"
_BACKTICKED = re.compile(r"`([^`]+)`")
_HEAD_LINE = re.compile(r"^Head = `([^`]+)`", re.MULTILINE)

_FIX_HINT = (
    "The migration files are the source of truth (docs/ops/migrations.md, 'Known risks'). "
    "Update docs/ops/migrations.md in the same commit as the migration."
)


def alembic_chain(migrations_dir: Path = _VERSIONS_DIR) -> list[str]:
    """Every revision id from base to head, read from the `down_revision` links."""
    config = Config()
    config.set_main_option("script_location", str(migrations_dir))
    script = ScriptDirectory.from_config(config)
    chain = [revision.revision for revision in script.walk_revisions()]
    chain.reverse()
    return chain


def alembic_heads(migrations_dir: Path = _VERSIONS_DIR) -> list[str]:
    config = Config()
    config.set_main_option("script_location", str(migrations_dir))
    return list(ScriptDirectory.from_config(config).get_heads())


def documented_chain(markdown: str) -> list[str]:
    """Every backticked token in the `## Current chain` block, in the order written.

    Raises rather than returning an empty list, so a renamed heading or a reformatted block
    fails the suite instead of passing it.
    """
    lines = markdown.splitlines()
    try:
        start = lines.index(_CHAIN_HEADING) + 1
    except ValueError:
        raise AssertionError(
            f"docs/ops/migrations.md has no {_CHAIN_HEADING!r} heading, so this check cannot "
            "read the chain it is meant to compare. Restore the heading, or update this test "
            "to the new structure — do not leave it matching nothing."
        ) from None
    block: list[str] = []
    for line in lines[start:]:
        if not line.strip():
            break
        block.append(line)
    chain = [match.group(1) for line in block for match in _BACKTICKED.finditer(line)]
    if not chain:
        raise AssertionError(
            f"The {_CHAIN_HEADING!r} block in docs/ops/migrations.md names no backticked "
            f"revision. Read block: {block!r}"
        )
    return chain


def documented_head(markdown: str) -> str:
    """The revision named by the single `Head = ...` line."""
    matches = _HEAD_LINE.findall(markdown)
    if len(matches) != 1:
        raise AssertionError(
            "docs/ops/migrations.md must carry exactly one line starting 'Head = `...`'; "
            f"found {len(matches)}: {matches!r}"
        )
    return str(matches[0])


def describe_difference(doc_chain: list[str], disk_chain: list[str]) -> str:
    missing = [revision for revision in disk_chain if revision not in doc_chain]
    invented = [revision for revision in doc_chain if revision not in disk_chain]
    duplicated = sorted({r for r in doc_chain if doc_chain.count(r) > 1})
    parts: list[str] = []
    if missing:
        parts.append(f"on disk but missing from the doc: {', '.join(missing)}")
    if invented:
        parts.append(f"in the doc but not on disk: {', '.join(invented)}")
    if duplicated:
        parts.append(f"listed more than once in the doc: {', '.join(duplicated)}")
    if not parts:
        for position, (in_doc, on_disk) in enumerate(zip(doc_chain, disk_chain, strict=True), 1):
            if in_doc != on_disk:
                parts.append(
                    f"same revisions, different order: position {position} is {in_doc} in the "
                    f"doc and {on_disk} on disk"
                )
                break
    return "; ".join(parts)


@pytest.fixture(scope="module")
def migrations_markdown() -> str:
    if not _MIGRATIONS_DOC.exists():
        raise AssertionError(f"{_MIGRATIONS_DOC} is missing; this check has nothing to compare.")
    return _MIGRATIONS_DOC.read_text(encoding="utf-8")


def test_the_alembic_chain_has_exactly_one_head() -> None:
    """docs/ops/migrations.md claims 'Single linear chain'. Pin the claim, not the sentence."""
    heads = alembic_heads()
    assert len(heads) == 1, (
        f"The Alembic chain has {len(heads)} heads: {heads}. docs/ops/migrations.md § "
        f"'Current chain' says 'Single linear chain', and backend/CLAUDE.md § Migrations says "
        f"'one linear chain (no branches)'. Merge the branch, or change both documents."
    )


def test_documented_chain_matches_the_alembic_chain(migrations_markdown: str) -> None:
    """The exact defect S-063 exists to catch: a revision on disk the document does not name."""
    doc_chain = documented_chain(migrations_markdown)
    disk_chain = alembic_chain()
    assert doc_chain == disk_chain, (
        "docs/ops/migrations.md § 'Current chain' disagrees with the Alembic chain on disk: "
        f"{describe_difference(doc_chain, disk_chain)}. {_FIX_HINT}"
    )


def test_documented_head_matches_the_alembic_head(migrations_markdown: str) -> None:
    doc_head = documented_head(migrations_markdown)
    disk_head = alembic_chain()[-1]
    assert doc_head == disk_head, (
        f"docs/ops/migrations.md says 'Head = `{doc_head}`' but the Alembic head on disk is "
        f"`{disk_head}`. {_FIX_HINT}"
    )


def test_the_extractor_reads_a_chain_it_is_given() -> None:
    """Prove the extractor matches, so a green run is never a run that read nothing."""
    document = "\n".join(
        [
            "## Current chain",
            "Single linear chain:",
            "`001_initial` → `002_second` →",
            "`003_third`.",
            "",
            "`001_initial` in prose after the block must not be picked up.",
            "",
            "Head = `003_third`; verify with `cd backend && uv run alembic heads`.",
        ]
    )
    assert documented_chain(document) == ["001_initial", "002_second", "003_third"]
    assert documented_head(document) == "003_third"


def test_the_extractor_refuses_a_document_with_no_chain_section() -> None:
    """A missing heading must raise, never return an empty list that compares equal to nothing."""
    with pytest.raises(AssertionError, match="has no '## Current chain' heading"):
        documented_chain("# Migrations\n\nNothing here.\n")
    with pytest.raises(AssertionError, match="names no backticked revision"):
        documented_chain("## Current chain\nSingle linear chain: none yet.\n")
    with pytest.raises(AssertionError, match="exactly one line starting"):
        documented_head("## Current chain\n`001_initial`.\n")
