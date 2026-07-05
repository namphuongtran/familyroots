"""L13: the audit actor records the caller's RESOLVED clan role, not a hardcoded string.

Routes previously passed a literal ("editor"/"admin") to ActorInfo.from_jwt regardless of
the caller. So an admin acting through an editor-gated route (e.g. document upload) was
audited as "editor". The routes now thread the resolved `role.value` from the permission
dependency, so the audit trail reflects who actually acted.
"""

import io
import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import UploadFile

import app.api.v1.documents as documents_route
from app.core.permissions import ClanRole

pytestmark = [pytest.mark.unit]


class _ActorCapturingHandler:
    def __init__(self) -> None:
        self.actor: Any = None

    async def upload(self, *, file_content: bytes, actor: Any, **_: Any) -> SimpleNamespace:
        self.actor = actor
        return SimpleNamespace(model_dump=lambda: {})


@pytest.mark.parametrize(
    ("caller_role", "expected"),
    [(ClanRole.ADMIN, "admin"), (ClanRole.EDITOR, "editor")],
)
@pytest.mark.asyncio
async def test_audit_actor_uses_resolved_role(caller_role: ClanRole, expected: str) -> None:
    handler = _ActorCapturingHandler()
    await documents_route.upload_document(
        file=UploadFile(io.BytesIO(b"x"), filename="f.jpg"),
        title="t",
        document_type="photo",
        person_id=None,
        description=None,
        taken_date=None,
        taken_place=None,
        current_user={"sub": str(uuid.uuid4())},
        clan_id=uuid.uuid4(),
        cmd_handler=handler,  # type: ignore[arg-type]
        role=caller_role,
    )
    # The document upload route is EDITOR-gated. Before the fix, an admin caller was still
    # recorded as "editor" (hardcoded); now the audit actor carries the resolved role.
    assert handler.actor is not None
    assert handler.actor.role == expected
