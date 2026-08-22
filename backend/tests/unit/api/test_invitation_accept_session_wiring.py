"""ADR-048: the accept HANDLER resolves the privileged session, the other three do not.

This is the tripwire for the one defect ADR-048 can produce. ``POST
/invitations/{token}/accept`` has no clan context (the invitee is not a member yet), so its
handler runs on ``get_system_db``. Re-pointing it at ``get_db`` puts the invitation reads and
writes back under the RLS seam with an empty ``app.clan_id``, where the ``clan_invitations``
policy from migration 032 turns every accept into ``invitation.not_found``.

The mirror assertion matters just as much: create, list and revoke must STAY on ``get_db``.
The cheap way to unblock accept was to move the shared ``get_invitation_command_handler``,
which create and revoke also use (``app/api/v1/invitations.py:42`` and ``:76``), and that
would have taken RLS off two clan-scoped write paths in order to fix one. This test fails if
anyone does that later.

**Scoped to the handler subtree on purpose.** ``get_current_user``
(``app/core/security.py:108-111``) takes ``get_db``, so an RLS request session is opened on
the accept route no matter what. It reads ``user_profiles``, which carries no policy, and it
is never the session the invitation repository uses. Asserting over the whole route graph
would therefore assert something untrue; asserting over the handler's own subtree is the
claim that matters.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute

from app.api.v1.invitations import admin_invitations_router, user_invitations_router
from app.core.database import get_db, get_system_db
from app.infrastructure.dependencies import (
    get_invitation_accept_handler,
    get_invitation_command_handler,
    get_invitation_query_handler,
)


def _subtree(dep: Dependant, target: Callable[..., Any]) -> Dependant | None:
    if dep.call is target:
        return dep
    for sub in dep.dependencies:
        found = _subtree(sub, target)
        if found is not None:
            return found
    return None


def _callables(dep: Dependant) -> set[object]:
    found: set[object] = {dep.call} if dep.call is not None else set()
    for sub in dep.dependencies:
        found |= _callables(sub)
    return found


def _handler_session_deps(
    router: APIRouter, path: str, method: str, provider: Callable[..., Any]
) -> set[object]:
    """Every callable under *provider* in the resolved dependency graph of one route.

    Read off the router itself rather than a mounted app: ``include_router`` wraps the
    router in this FastAPI version, so ``app.routes`` does not expose the ``APIRoute``.
    """
    for route in router.routes:
        if not isinstance(route, APIRoute):
            continue
        if route.path != path or method not in (route.methods or set()):
            continue
        node = _subtree(route.dependant, provider)
        assert node is not None, f"{method} {path} does not depend on {provider.__name__}"
        return _callables(node)
    raise AssertionError(f"no {method} {path} on {router}")


def test_accept_handler_runs_on_the_system_session_not_the_rls_request_session() -> None:
    deps = _handler_session_deps(
        user_invitations_router, "/{token}/accept", "POST", get_invitation_accept_handler
    )
    assert get_system_db in deps, "accept must run privileged — see ADR-048"
    assert get_db not in deps, (
        "the accept handler resolved get_db. Under the clan_invitations policy "
        "(migration 032) the token lookup returns zero rows and every accept answers "
        "invitation.not_found."
    )


def test_create_list_and_revoke_handlers_stay_on_the_rls_request_session() -> None:
    for path, method, provider, name in (
        ("", "POST", get_invitation_command_handler, "create"),
        ("", "GET", get_invitation_query_handler, "list"),
        ("/{invitation_id}", "DELETE", get_invitation_command_handler, "revoke"),
    ):
        deps = _handler_session_deps(admin_invitations_router, path, method, provider)
        assert get_db in deps, f"{name} must keep the RLS request session — see ADR-048"
        assert get_system_db not in deps, (
            f"{name} resolved get_system_db, which strips DB-level clan isolation from a "
            "clan-scoped invitation path. ADR-048 moved ONLY accept."
        )
