"""RLS layer-2 Phase 9: audit_logs (per-command) + notification_log (template) — ADR-043.

**Two tables, two different policy shapes, and the difference is the point.** ADR-043 § 1
settled the membership question the same way for both — "the reader decides membership of
layer 2, not the writer", because ``familyroots_app`` holds table-blind CRUD on every table
in ``public`` (``002_rls_documents_pilot.py:45``, plus default privileges at ``:49``), so a
request-role handler that forgot its ``WHERE clan_id`` could read either table today and
nothing at the database would stop it. What the writer's privilege decides is the SHAPE.

``notification_log`` — the migration-027 template, unchanged (ADR-043 § 2)
------------------------------------------------------------------------
``clan_id`` is ``NOT NULL`` with ``ON DELETE RESTRICT``
(``app/models/notification_log.py:17-21``), so there is no row the predicate mishandles.
Its only accessors are the anniversary scheduler's dedup ``SELECT`` and its ``INSERT``
(``app/services/scheduler.py:173``, ``:201``), which run on an ``AsyncSession`` bound to a
bare ``engine.connect()`` — no RLS seam, so no ``SET LOCAL ROLE`` and no policy. There is no
query port, no repository, and no route: ``docs/contracts/push-notifications.md:135`` says
"``notification_log`` is not queryable by clients today."

**So this policy is inert on 2026-08-22, and that is accepted deliberately.** It guards a
reader that does not exist yet. The alternative ADR-043 rejected was a permanent exemption
row in the clan-owned table list, which is a second place to record the same fact and
therefore a second place to be wrong.

``audit_logs`` — per command, because the writer is the REQUEST role (ADR-043 § 3)
---------------------------------------------------------------------------------
Copying the template here would break registration. Three facts force the split:

1. **Most audit rows are written by ``familyroots_app``.** ``AuditLogHandler``
   (``app/infrastructure/event_dispatcher.py:77-90``) is wired by
   ``create_event_dispatcher(db)``, and thirteen of its sixteen sites in
   ``app/infrastructure/dependencies.py`` hang off ``Depends(get_db)`` — the request
   session. Only ``:145`` (identity claims), ``:169`` (platform admin) and ``:361``
   (invitation accept, ADR-048) are privileged. The audit writer is not a system path; it
   is the request path writing a side-effect row inside the caller's own transaction
   (ADR-014).
2. **Three request routes write an audit row with NO clan GUC at all.** The GUC is written
   only inside ``get_current_clan_id`` (``app/core/security.py:290``).
   ``POST /api/v1/auth/register`` is unauthenticated and ``POST /api/v1/auth/onboard`` takes
   ``get_current_user`` only (``app/api/v1/auth.py:44-49``, ``:63-68``); neither can have a
   clan GUC, because ``auth.py:17`` imports ``get_current_user`` and nothing else from
   ``app.core.security``. Both write a ``clan.create``/``clan.join_request`` row whose
   ``clan_id`` is a real clan. Under a template ``WITH CHECK`` that comparison is
   ``<real clan> = NULL`` → NULL → not true → **rejected**. ADR-043's third route,
   ``POST /invitations/{token}/accept``, has since moved to the privileged session
   (``dependencies.py:358-362``, ADR-048), so it is no longer one of these; the two that
   remain are enough to force the permissive ``WITH CHECK``.
3. **``clan_id`` is nullable on purpose** (``app/models/audit_log.py:18-21``): "platform-level
   actions have no clan, and deleting a clan must not erase its audit trail", with
   ``ondelete="SET NULL"``.

Hence ``audit_logs_sel`` (clan-keyed, the guard layer 2 exists for),
``audit_logs_ins WITH CHECK (true)`` (the writers above), and **no UPDATE and no DELETE
policy at all**. That absence is not an omission: with RLS enabled, a command with no
matching policy is denied outright for a non-bypass role, so the request role can append to
the audit trail and can never edit or erase it. ``audit_logs`` is documented as an
"immutable log of all write actions" at ``app/models/audit_log.py:1``; this makes the
database enforce it. ``grep -rn 'audit_logs' backend/app`` on 2026-08-22 finds no UPDATE and
no DELETE anywhere in the application, so nothing legitimate is being taken away.

What happens to NULL-``clan_id`` rows, in one line each (ADR-043 § 4)
--------------------------------------------------------------------
Retained; never filtered at write (``audit_logs_ins`` is permissive); invisible to **every**
clan under the request role, because ``NULL = <anything>`` is NULL in SQL and so
``audit_logs_sel`` hides them with no special case; and **fully visible to the platform-admin
surface**, because ``GET /api/v1/platform-admin/audit-log`` runs on ``get_system_db``
(``dependencies.py:174-177``), which never issues ``SET LOCAL ROLE``, so RLS does not apply
to it at all. ADR-030's newest-first cross-clan contract is therefore untouched.

ADR-043 explicitly rejected ``USING (clan_id = GUC OR clan_id IS NULL)`` — the predicate a
reader reaches for on seeing "nullable on purpose" — because it would make every
platform-level action and every orphaned row readable by **every** clan.

The ORM line that ships with this migration and is not optional (ADR-043 § 6)
----------------------------------------------------------------------------
``app/models/audit_log.py`` gains ``__mapper_args__ = {"eager_defaults": False}`` in the same
commit. ADR-038 found that Postgres matches a ``RETURNING`` row against the **SELECT**
policy, and SQLAlchemy's ``eager_defaults="auto"`` appends ``RETURNING`` whenever a server
default exists. Measured 2026-08-22 on SQLAlchemy 2.0.51 against the postgresql dialect:
``AuditLog`` resolved ``eager_defaults=auto`` → prefers eager ``True``, with ``created_at``
its one server default. So without that line every ORM insert appends
``RETURNING created_at``, ``audit_logs_ins`` accepts the write, and ``audit_logs_sel``
rejects the row on its way back — ADR-038's failure verbatim, and invisible to every unit
test. Fixed in the ORM rather than by widening the policy, on ADR-038's grounds: a policy
widened to admit a write stops describing the read rule it exists for.

``ENABLE``, not ``FORCE``: the system path connects as a bypassing role, so the scheduler,
the platform-admin surface and this migration itself are untouched. Grants are left alone.
Reversible (drop policies + disable).

Pinned by ``tests/integration/test_rls_phase9_audit_notification.py`` (two-sided isolation on
both tables at the DB layer, the NULL-clan pair, immutability, and the scheduler crossing
clans in one run) and by the three-way coverage guard in
``tests/integration/test_rls_activation.py``.

Revision ID: 034_rls_audit_notification
Revises: 033_rls_identity_claims
"""

from __future__ import annotations

from alembic import op

revision: str = "034_rls_audit_notification"
down_revision: str | None = "033_rls_identity_claims"
branch_labels = None
depends_on = None

# The migration-027 predicate, verbatim. An unset GUC → empty string → nullif → NULL →
# no row matches and no write is admitted (fail closed).
_PREDICATE = "clan_id = nullif(current_setting('app.clan_id', true), '')::uuid"

_NOTIFICATION_POLICY = "notification_log_clan_isolation"
_AUDIT_SELECT_POLICY = "audit_logs_sel"
_AUDIT_INSERT_POLICY = "audit_logs_ins"


def upgrade() -> None:
    # ── notification_log: the template, both halves clan-keyed ──────────────
    op.execute("ALTER TABLE notification_log ENABLE ROW LEVEL SECURITY")
    op.execute(f"DROP POLICY IF EXISTS {_NOTIFICATION_POLICY} ON notification_log")
    op.execute(
        f"CREATE POLICY {_NOTIFICATION_POLICY} ON notification_log "
        f"USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
    )

    # ── audit_logs: per command ─────────────────────────────────────────────
    op.execute("ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY")
    op.execute(f"DROP POLICY IF EXISTS {_AUDIT_SELECT_POLICY} ON audit_logs")
    op.execute(f"DROP POLICY IF EXISTS {_AUDIT_INSERT_POLICY} ON audit_logs")
    op.execute(
        f"CREATE POLICY {_AUDIT_SELECT_POLICY} ON audit_logs FOR SELECT USING ({_PREDICATE})"
    )
    # Permissive by decision, not by oversight: see paragraph 2 above. The value is
    # derived from an AuditableEvent assembled server-side, never from client input, and
    # the leak direction layer 2 exists for is READ, not write.
    op.execute(f"CREATE POLICY {_AUDIT_INSERT_POLICY} ON audit_logs FOR INSERT WITH CHECK (true)")
    # No UPDATE policy and no DELETE policy — deliberately. Under RLS a command with no
    # matching policy is denied for a non-bypass role, which is what makes the trail
    # append-only for familyroots_app.


def downgrade() -> None:
    op.execute(f"DROP POLICY IF EXISTS {_AUDIT_INSERT_POLICY} ON audit_logs")
    op.execute(f"DROP POLICY IF EXISTS {_AUDIT_SELECT_POLICY} ON audit_logs")
    op.execute("ALTER TABLE audit_logs DISABLE ROW LEVEL SECURITY")
    op.execute(f"DROP POLICY IF EXISTS {_NOTIFICATION_POLICY} ON notification_log")
    op.execute("ALTER TABLE notification_log DISABLE ROW LEVEL SECURITY")
