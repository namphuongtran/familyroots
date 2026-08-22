"""Drop the ``clan_settings`` table (S-065, ADR-054).

ADR-044 § 5 handed the fate of this table to the coordinator after S-017 and S-018 took
two of its columns. ADR-054 decides it: the table is dropped whole. This docstring is the
durable record of what that costs and what the ``downgrade`` has to put back, because the
seed tracker is not what the next agent reads when it opens a migration.

Why the table goes, in one paragraph
------------------------------------
Three authorities point the same way and none of them was written to answer this question,
which is why they are worth naming. **The design spec refuses to draw it**: § 7.10d, under
the heading "What this screen must not contain"
(``docs/superpowers/specs/2026-08-02-design-system-and-screens.md:1783-1789``), names the
table and its knobs and rules them out of the clan-admin screen, and § 9-J21 (``:2397-2402``)
repeats the refusal as a numbered lesson. **The roadmap has no item for it**: the only row in
``docs/roadmap.md`` that named the table is its M1 privacy-toggle boundary at ``:41``, whose
two columns were dropped on 2026-08-22, and ``data-model.md``'s pointer to "Roadmap item D3"
resolved to nothing — measured 2026-08-22, ``grep -rn 'D3\\b' docs/`` returns five hits and not
one is a roadmap item. **ADR-044 § 3 already decided nothing creates a row and nothing
should.** So the table has no reader, no writer, no row, no screen, and no scheduled work.

The round trip is exact on everything that carries meaning, and NOT on ``attnum``
--------------------------------------------------------------------------------
Stated plainly because S-018 recorded the mirror-image fact and this one is its reverse.

At ``038`` the live table's ``attnum`` sequence is ``1,2,3,4,5,7,9,10,11``: the gaps at 6 and
8 are the tombstones ``037`` and ``038`` left when they dropped ``allow_public_tree`` and
``privacy_level``. Postgres never reuses a dropped ``attnum``. A ``CREATE TABLE`` cannot
reproduce a gap, so ``downgrade`` returns ``1..9`` contiguous.

**That is the only difference, and it is a difference in the tidier direction** — the
downgrade produces a catalogue with no tombstones rather than one with two. Column names,
types, ``NOT NULL``, defaults, ordering, the primary key, the unique constraint, the foreign
key and its ``RESTRICT``, the ``updated_at`` trigger, the RLS flags, the policy and its two
predicates, and the ``familyroots_app`` grants all come back identical. Verified by ``cmp``
on a catalogue dump, against a database that never carried this revision (S-018's pattern).

What ``DROP TABLE`` takes with it, and what ``downgrade`` therefore has to rebuild
---------------------------------------------------------------------------------
``DROP TABLE`` is not a column drop. Five things ride along silently, and every one is
restored explicitly below rather than left to a default:

1. **The RLS policy from ``035_rls_clan_settings``.** Postgres drops a table's policies with
   the table; there is no separate statement and no warning. ``035`` is left on disk and
   untouched — running it after this revision is not a supported path, and it is not in the
   chain ahead of this one. ``downgrade`` re-runs its two statements verbatim, so a database
   downgraded to ``038`` has the policy ``035`` gave it.

   **No test in the suite proves that, and the reason is worth knowing.** The obvious
   assumption is that ``tests/integration/test_rls_activation.py`` would catch a downgrade
   that forgot the policy. It would not, and it is in fact the other way round. That guard
   reads the RLS-enabled tables from the catalogue and asserts the set EQUALS the union of
   its four posture sets. Measured 2026-08-22 on two throwaway databases: at ``038`` with
   this downgrade applied the catalogue returns 14 RLS tables including ``clan_settings``,
   and at head it returns 13 without it. ``clan_settings`` is no longer named in any posture
   set, so a **correct** downgrade makes that assertion fail with "RLS scope drifted", while
   a downgrade that skipped the policy would leave RLS disabled, keep the table out of the
   catalogue set, and **pass**. The guard is pinned to head, which is where the suite runs.
   So what proves the policy came back is the ``cmp`` on the catalogue dump and the exercised
   two-sided isolation, not a test. Do not add ``clan_settings`` back to that guard to "fix"
   this: the table does not exist at head, and the guard is right about head.
2. **The ``trg_clan_settings_updated_at`` trigger** (``001_initial.py:930-937``). The
   ``update_updated_at_column()`` function itself belongs to ``001`` and survives.
3. **The ``fk_clan_settings_clan_id_clans`` foreign key**, which is ``ON DELETE RESTRICT`` —
   ADR-009's rule, applied by ``010_clan_fk_restrict.py:34``, converting ``001_initial.py:589``'s
   original ``CASCADE``. ``downgrade`` writes ``RESTRICT`` directly: it restores the table as
   ``038`` had it, not as ``001`` created it.
4. **The ``familyroots_app`` grants.** ``002`` grants table CRUD to the request role and also
   sets ``ALTER DEFAULT PRIVILEGES`` for the migration owner (``002:44-50``), so a table this
   migration recreates is granted automatically. That is a real dependency on ``002`` having
   run, so it is asserted rather than assumed — the ``cmp`` above covers the grant rows.
5. **The constraint names.** They follow the project convention in
   ``app/models/base.py:13-19``, not Postgres defaults, so each is named explicitly:
   ``pk_clan_settings``, ``uq_clan_settings_clan_id``, ``fk_clan_settings_clan_id_clans``.

No rows are lost, and that is measured rather than believed
-----------------------------------------------------------
The table is empty in every environment, because nothing can put a row in it. Nothing
constructs a ``ClanSettings`` (ADR-044 Measurement 3), ``001_initial.py`` installs no trigger
that would create one, and ADR-044 Measurement 5 case A shows the obvious creator — an insert
during clan creation, on the request session with no ``app.clan_id`` — is **rejected** by
``035``'s ``WITH CHECK``. So ``upgrade`` drops no data and ``downgrade`` has none to
reconstruct.

**A safety net rather than a belief:** ``upgrade`` raises if the table is not empty. This
costs one ``SELECT`` on a table that has never held a row, and it means an operator running
this against a database that somehow does hold settings gets a refusal instead of a silent
deletion.

Nothing else changes. No API shape moves: no endpoint ever read or wrote this table, and no
contract ever documented it — ``docs/contracts/rest-clans-api.md``'s one "clan settings"
sentence means the ``PATCH /clans/me`` clan-info body, which ADR-054 disambiguates in the
same change.

Revision ID: 039_drop_clan_settings
Revises: 038_drop_privacy_level
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "039_drop_clan_settings"
down_revision: str | None = "038_drop_privacy_level"
branch_labels = None
depends_on = None

# Migration 035's predicate, verbatim. An unset GUC → empty string → nullif → NULL → no row
# matches and no write is admitted (fail closed).
_PREDICATE = "clan_id = nullif(current_setting('app.clan_id', true), '')::uuid"


def upgrade() -> None:
    # The table has never held a row and cannot (see the docstring). Refuse rather than
    # delete silently if that is somehow false here.
    count = op.get_bind().execute(sa.text("SELECT count(*) FROM clan_settings")).scalar_one()
    if count:
        raise RuntimeError(
            f"clan_settings holds {count} row(s); ADR-054 drops the table on the measured "
            "precondition that it is empty. Investigate before running this migration."
        )
    # DROP TABLE takes the RLS policy, the trigger, the FK, the unique constraint and the
    # grants with it. All five are rebuilt explicitly in downgrade().
    op.drop_table("clan_settings")


def downgrade() -> None:
    # Restores the table as revision 038 had it: 001's columns MINUS allow_public_tree (037)
    # and privacy_level (038), the FK already converted to RESTRICT by 010.
    op.create_table(
        "clan_settings",
        sa.Column(
            "id", UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("clan_id", UUID(as_uuid=True), nullable=False),
        sa.Column("approval_config", JSONB, nullable=True),
        sa.Column(
            "default_language", sa.String(10), nullable=False, server_default=sa.text("'vi'")
        ),
        sa.Column(
            "tree_display_mode", sa.String(20), nullable=False, server_default=sa.text("'vertical'")
        ),
        sa.Column("notification_defaults", JSONB, nullable=True),
        sa.Column(
            "max_upload_size_mb", sa.SmallInteger, nullable=False, server_default=sa.text("10")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_clan_settings"),
        sa.UniqueConstraint("clan_id", name="uq_clan_settings_clan_id"),
        sa.ForeignKeyConstraint(
            ["clan_id"],
            ["clans.id"],
            name="fk_clan_settings_clan_id_clans",
            ondelete="RESTRICT",
        ),
    )
    # 001_initial.py:930-937 — the function belongs to 001 and survives the drop.
    op.execute(
        "CREATE TRIGGER trg_clan_settings_updated_at "
        "BEFORE UPDATE ON clan_settings "
        "FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()"
    )
    # 035_rls_clan_settings, verbatim. ENABLE, not FORCE: the system session connects as a
    # bypassing role.
    op.execute("ALTER TABLE clan_settings ENABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS clan_settings_clan_isolation ON clan_settings")
    op.execute(
        "CREATE POLICY clan_settings_clan_isolation ON clan_settings "
        f"USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
    )
