"""The global IntegrityError handler maps a DB constraint violation to a 409 envelope.

Backstop for any write that loses a uniqueness race (or otherwise violates a
constraint) without an explicit application guard — it must surface as the stable
conflict envelope, never a raw 500.
"""

import json
from typing import Any

import pytest
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.requests import Request

from app.core.exceptions import integrity_error_handler

pytestmark = [pytest.mark.unit]

_REQ = Request({"type": "http", "method": "POST", "path": "/x", "headers": []})


class _Diag:
    def __init__(self, constraint_name: str | None) -> None:
        self.constraint_name = constraint_name


class _PgError(Exception):
    """Stand-in for the psycopg error under IntegrityError.orig — carries a SQLSTATE and
    (like psycopg3) a ``.diag.constraint_name``, plus an optional message."""

    def __init__(
        self, sqlstate: str, constraint_name: str | None = None, message: str | None = None
    ) -> None:
        self.sqlstate = sqlstate
        self.diag = _Diag(constraint_name)
        super().__init__(
            message or f"db error {sqlstate}: duplicate key value violates unique constraint"
        )


def _body(response: JSONResponse) -> dict[str, Any]:
    parsed: dict[str, Any] = json.loads(bytes(response.body))
    return parsed


@pytest.mark.asyncio
async def test_unique_violation_becomes_409_conflict() -> None:
    # 23505 = unique_violation — a lost race / duplicate.
    exc = IntegrityError("INSERT INTO user_profiles ...", {}, _PgError("23505"))
    resp = await integrity_error_handler(_REQ, exc)

    assert resp.status_code == 409
    body = _body(resp)
    assert set(body["error"]) == {"code", "message", "detail"}
    assert body["error"]["code"] == "conflict"
    # The raw DB message must not leak to the client.
    assert "duplicate key" not in json.dumps(body)


@pytest.mark.asyncio
async def test_non_unique_integrity_error_stays_a_500() -> None:
    # 23503 = foreign_key_violation — a server-side logic bug, must not be masked as 409.
    exc = IntegrityError("INSERT ...", {}, _PgError("23503"))
    resp = await integrity_error_handler(_REQ, exc)

    assert resp.status_code == 500
    assert _body(resp)["error"]["code"] == "internal_error"


# ── Named-constraint mapping (A7 unmapped-CHECK→500 + M11 invite-409 follow-ups) ──


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("constraint", "status", "code"),
    [
        (
            "ck_marriages_marriages_divorce_after_marriage",
            422,
            "relationship.divorce_before_marriage",
        ),
        ("ck_marriages_marriages_no_self", 422, "self_marriage_not_allowed"),
        ("ck_parent_child_parent_child_no_self", 422, "self_parent_not_allowed"),
    ],
)
async def test_known_check_constraint_maps_to_clean_4xx(
    constraint: str, status: int, code: str
) -> None:
    """A real named CHECK constraint (23514) that the app pre-check normally shadows must,
    if it slips through, surface as its specific client-facing code — not a raw 500."""
    exc = IntegrityError(
        "INSERT ...",
        {},
        _PgError("23514", constraint_name=constraint, message=f'violates check "{constraint}"'),
    )
    resp = await integrity_error_handler(_REQ, exc)
    assert resp.status_code == status
    body = _body(resp)
    assert body["error"]["code"] == code
    assert constraint not in json.dumps(body)  # raw DB detail must not leak


@pytest.mark.asyncio
async def test_unknown_check_constraint_stays_500() -> None:
    """A CHECK we do NOT recognize is still a server-side bug → loud 500 (the follow-up
    maps the KNOWN client-facing ones, it does not blanket-downgrade every CHECK)."""
    exc = IntegrityError(
        "INSERT ...", {}, _PgError("23514", constraint_name="ck_persons_birth_precision")
    )
    resp = await integrity_error_handler(_REQ, exc)
    assert resp.status_code == 500
    assert _body(resp)["error"]["code"] == "internal_error"


@pytest.mark.asyncio
async def test_trigger_slug_check_still_maps_by_message() -> None:
    """The ADR-023 triggers RAISE check_violation with NO constraint name — the slug in
    the message must still map to the app's code (regression pin)."""
    exc = IntegrityError(
        "INSERT ...",
        {},
        _PgError("23514", constraint_name=None, message="too_many_biological_parents for child"),
    )
    resp = await integrity_error_handler(_REQ, exc)
    assert resp.status_code == 409
    assert _body(resp)["error"]["code"] == "relationship.too_many_biological_parents"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("constraint", "code"),
    [
        ("uq_clan_invitations_pending", "invitation.pending_exists"),
        ("uq_marriages_spouse_order", "relationship.duplicate_spouse_order"),
    ],
)
async def test_known_unique_constraint_maps_to_specific_409(constraint: str, code: str) -> None:
    """A named unique-index race (23505) surfaces its SPECIFIC code, not the generic
    conflict — e.g. two fresh concurrent invites both insert → the loser sees
    invitation.pending_exists (M11), not the bare 'conflict'."""
    exc = IntegrityError("INSERT ...", {}, _PgError("23505", constraint_name=constraint))
    resp = await integrity_error_handler(_REQ, exc)
    assert resp.status_code == 409
    assert _body(resp)["error"]["code"] == code


@pytest.mark.asyncio
async def test_unknown_unique_constraint_stays_generic_conflict() -> None:
    """An unrecognized unique violation still maps to the stable generic 409 conflict."""
    exc = IntegrityError("INSERT ...", {}, _PgError("23505", constraint_name="some_other_uq"))
    resp = await integrity_error_handler(_REQ, exc)
    assert resp.status_code == 409
    assert _body(resp)["error"]["code"] == "conflict"
