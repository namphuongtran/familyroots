"""L13: the audit actor records the caller's RESOLVED clan role, not a hardcoded string.

Routes previously passed a literal ("editor"/"admin") to ActorInfo.from_jwt regardless of
the caller. So an admin acting through an editor-gated route (e.g. document upload) was
audited as "editor". The routes now thread the resolved `role.value` from the permission
dependency, so the audit trail reflects who actually acted.
"""

import uuid
from types import SimpleNamespace
from typing import Any

import pytest

import app.api.v1.documents as documents_route
from app.core.permissions import ClanRole
from app.schemas.document import DocumentCreateRequest

pytestmark = [pytest.mark.unit]


class _ActorCapturingHandler:
    def __init__(self) -> None:
        self.actor: Any = None

    async def confirm(self, *, actor: Any, **_: Any) -> SimpleNamespace:
        self.actor = actor
        return SimpleNamespace(model_dump=lambda: {})


@pytest.mark.parametrize(
    ("caller_role", "expected"),
    [(ClanRole.ADMIN, "admin"), (ClanRole.EDITOR, "editor")],
)
@pytest.mark.asyncio
async def test_audit_actor_uses_resolved_role(caller_role: ClanRole, expected: str) -> None:
    handler = _ActorCapturingHandler()
    clan_id = uuid.uuid4()
    await documents_route.create_document(
        body=DocumentCreateRequest(
            storage_path=f"clans/{clan_id}/uploads/{uuid.uuid4()}.jpg",
            title="t",
            document_type="photo",
        ),
        current_user={"sub": str(uuid.uuid4())},
        clan_id=clan_id,
        upload_handler=handler,  # type: ignore[arg-type]
        role=caller_role,
    )
    # The document create (upload confirm) route is EDITOR-gated. Before the fix, an admin
    # caller was still recorded as "editor" (hardcoded); now the audit actor carries the
    # resolved role.
    assert handler.actor is not None
    assert handler.actor.role == expected
