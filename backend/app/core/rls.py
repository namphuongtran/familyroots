"""RLS layer-2 runtime seam (SP-3 Phase 1, ADR-008).

The request path drops to the non-bypass ``familyroots_app`` role and sets the
transaction-local ``app.clan_id`` GUC that the RLS policies read, so a future missed
application-layer ``WHERE clan_id = …`` cannot leak cross-clan data. The application
layer remains the PRIMARY isolation mechanism; this is defense-in-depth.

Mechanism: a request ``ContextVar`` holds the active clan id (set by
``get_current_clan_id`` once resolved). An ``after_begin`` event on the request session
re-applies, at the start of EVERY transaction (including a fresh one after a commit,
where ``SET LOCAL`` state would otherwise be lost):

    SET LOCAL ROLE familyroots_app;
    SELECT set_config('app.clan_id', <clan_id or ''>, true);

An unset clan id → empty GUC → the policy's ``nullif(...)::uuid`` is NULL → zero rows
(**fail closed**). System sessions (scheduler, purge, migrations) use a different
session class without this event, so they keep the privileged connection and bypass RLS.
"""

from __future__ import annotations

import re
import uuid
from contextvars import ContextVar
from typing import Any

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.core.config import settings

# The active clan for the current request (a UUID string), or None outside a
# clan-scoped request. Per-asyncio-task via contextvars (same pattern as RequestMeta).
_request_clan_id: ContextVar[str | None] = ContextVar("rls_request_clan_id", default=None)

# Role names are identifiers (cannot be parameterized) — restrict to a safe pattern so a
# misconfigured RLS_APP_ROLE can never inject SQL. The value is app config, not user input.
_ROLE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def set_request_clan_id(clan_id: uuid.UUID | str | None) -> None:
    """Record the active clan for this request (drives the RLS GUC)."""
    _request_clan_id.set(str(clan_id) if clan_id is not None else None)


def get_request_clan_id() -> str | None:
    return _request_clan_id.get()


def apply_rls_context(connection: Any) -> None:
    """Issue ``SET LOCAL ROLE`` + the ``app.clan_id`` GUC on a just-begun transaction.

    Called from the request session's ``after_begin`` event. No-op when RLS is disabled
    (rollback switch). Uses ``exec_driver_sql`` because this runs inside the sync
    greenlet at transaction begin.
    """
    if not settings.RLS_ENABLED:
        return
    role = settings.RLS_APP_ROLE
    if not _ROLE_RE.match(role):
        raise RuntimeError(f"unsafe RLS_APP_ROLE identifier: {role!r}")
    connection.exec_driver_sql(f"SET LOCAL ROLE {role}")
    clan = _request_clan_id.get() or ""
    connection.exec_driver_sql("SELECT set_config('app.clan_id', %s, true)", (clan,))


def register_rls_session_events(session_class: type[Session]) -> None:
    """Attach the RLS ``after_begin`` seam to a (request-only) sync Session class."""

    @event.listens_for(session_class, "after_begin")
    def _after_begin(session: Session, transaction: Any, connection: Any) -> None:
        apply_rls_context(connection)
