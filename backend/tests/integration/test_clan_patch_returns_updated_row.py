"""``PATCH /clans/me`` answers 200 with the row it just wrote.

**Seed S-078.** The route answered **500 on every edit that changed something**, and the
row was written anyway — a server error and a successful write, which is the worst pair
to hand a client: retrying is unsafe and not retrying loses the response.

**The mechanism, read at source.** ``app/api/v1/clans.py:84`` validates the ORM instance
that ``ClanCommandHandler.update_clan`` returns, and that handler commits first
(``app/application/clan/handlers.py:54``). ``clans.updated_at`` carries
``onupdate=func.now()`` (``app/models/base.py:34-39``), a **SQL** expression, so
SQLAlchemy cannot know the new value client-side. SQLAlchemy 2.0's default
``eager_defaults="auto"`` uses ``RETURNING`` for **INSERT only**, never for UPDATE, so
after the UPDATE flush that attribute is left unloaded. Reading it after the commit
starts a lazy load with no greenlet to run the IO in — ``sqlalchemy.exc.MissingGreenlet``,
an unhandled exception, a 500.

**That is why it hid for so long, and why the no-op case below exists.** A PATCH that
changes nothing emits no UPDATE, expires nothing, and answers 200. S-073 measured the
sequence on 2026-08-22: change -> 500, no-op -> 200, no-op -> 200, change -> 500. **Any
smoke test that PATCHes the same value twice passes forever**, and the whole backend suite
was green with this route broken.

**Every test here sends a request and reads the response**, per ``.claude/rules/seeds.md``
§ "A test pins an outcome, not a setting". None of them asks whether a refresh ran, and
none asserts that a schema field exists. Two readings are taken of the same edit:

* ``test_a_real_edit_answers_200_and_the_body_is_the_row_it_wrote`` uses the default
  ``ASGITransport``, which re-raises what the app raised (Starlette's
  ``ServerErrorMiddleware`` always re-raises after its handler builds the 500). Against
  the unfixed route this test **names the exception**.
* ``test_the_client_reads_a_status_code_and_the_write_is_not_orphaned`` uses
  ``raise_app_exceptions=False``, so it reads the literal status code a real client gets,
  next to the row the request wrote. Against the unfixed route it reads ``(500, written)``.

**The body is checked against the stored row, not against the request.** A route that
answered 200 with a stale body would otherwise pass: the assertion covers all eight
profile fields plus ``created_at`` and ``updated_at``, and requires ``updated_at`` to have
moved past its pre-edit value.

Real Postgres (``migrated_db_url``, ADR-016), real handlers, real RBAC and real clan
resolution. Only JWT *verification* is stubbed, the same seam and the same way
``tests/integration/test_person_pii_over_http.py`` does it.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi import Header
from httpx2 import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.core.security import get_current_user
from app.main import create_app

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

# The eight fields `ClanUpdateRequest` accepts, plus the three the response adds. Read
# from `app/schemas/clan.py:29-46` (ClanResponse) and `:58-68` (ClanUpdateRequest).
_PROFILE_COLUMNS = (
    "name",
    "description",
    "origin_place",
    "founded_year",
    "avatar_url",
    "motto",
    "ancestral_hall_location",
    "clan_rules",
)

_SEEDED = {
    "name": "Họ Nguyễn S078",
    "description": "mô tả ban đầu",
    "origin_place": "Bắc Ninh",
    "founded_year": 1750,
    "avatar_url": "https://example.com/s078.png",
    "motto": "khẩu hiệu ban đầu",
    "ancestral_hall_location": "Nhà thờ tổ ban đầu",
    "clan_rules": "gia huấn ban đầu",
}


async def _override_current_user(
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    assert authorization is not None, "test client must send an Authorization header"
    return {"sub": authorization.removeprefix("Bearer ")}


@pytest.fixture()
async def session_factory(
    migrated_db_url: str,
) -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(migrated_db_url)
    yield async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    await engine.dispose()


@pytest.fixture()
async def seeded(session_factory: async_sessionmaker[AsyncSession]) -> dict[str, Any]:
    """One clan with every editable field already set, and one approved admin.

    The fields start non-null so that each PATCH below is a real change with a real
    "before" value to compare against — a PATCH that writes into a null column would
    still be a change, but it could not tell a stale body from a fresh one.
    """
    clan_id, admin_id = uuid.uuid4(), uuid.uuid4()

    async with session_factory() as s:
        await s.execute(
            sa.text(
                "INSERT INTO clans (id, slug, name, description, origin_place, "
                "founded_year, avatar_url, motto, ancestral_hall_location, clan_rules) "
                "VALUES (:id, :slug, :name, :description, :origin_place, :founded_year, "
                ":avatar_url, :motto, :ancestral_hall_location, :clan_rules)"
            ),
            {"id": clan_id, "slug": f"s078-{clan_id.hex[:10]}", **_SEEDED},
        )
        await s.execute(
            sa.text(
                "INSERT INTO user_profiles (id, email, display_name) "
                "VALUES (:id, :email, 'quản trị S078')"
            ),
            {"id": admin_id, "email": f"{admin_id.hex[:10]}@example.com"},
        )
        await s.execute(
            sa.text(
                "INSERT INTO user_clan_roles "
                "(user_id, clan_id, role, is_approved, approved_by, approved_at) "
                "VALUES (:uid, :cid, 'admin', true, :uid, now())"
            ),
            {"uid": admin_id, "cid": clan_id},
        )
        await s.commit()

    return {"clan_id": clan_id, "admin_id": admin_id}


def _app(session_factory: async_sessionmaker[AsyncSession]) -> Any:
    app = create_app()

    async def _override_db() -> AsyncGenerator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_current_user
    return app


@pytest.fixture()
async def client(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncClient]:
    """Re-raises whatever the route raised, so a failure names the exception."""
    transport = ASGITransport(app=_app(session_factory))
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest.fixture()
async def lenient_client(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncClient]:
    """Swallows the exception and hands back the response a real client would get.

    Starlette's ``ServerErrorMiddleware`` re-raises after building the 500, so the only
    way to *read the status code* rather than the traceback is to stop the re-raise here.
    """
    transport = ASGITransport(app=_app(session_factory), raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


def _headers(seeded: dict[str, Any]) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {seeded['admin_id']}",
        "X-Current-Clan-Id": str(seeded["clan_id"]),
    }


async def _row(
    session_factory: async_sessionmaker[AsyncSession], clan_id: uuid.UUID
) -> sa.Row[Any]:
    columns = ", ".join((*_PROFILE_COLUMNS, "created_at", "updated_at"))
    async with session_factory() as s:
        return (
            await s.execute(sa.text(f"SELECT {columns} FROM clans WHERE id = :id"), {"id": clan_id})
        ).one()


async def test_a_real_edit_answers_200_and_the_body_is_the_row_it_wrote(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    seeded: dict[str, Any],
) -> None:
    """The end state of S-078, in one reading.

    Against the unfixed route this raises ``sqlalchemy.exc.MissingGreenlet`` out of
    ``ClanResponse.model_validate`` — the negative control for this file.
    """
    before = await _row(session_factory, seeded["clan_id"])
    change = {"motto": "Uống nước nhớ nguồn", "founded_year": 1802}
    assert change["motto"] != _SEEDED["motto"], "the PATCH must change something"

    response = await client.patch("/api/v1/clans/me", json=change, headers=_headers(seeded))

    assert response.status_code == 200, response.text
    body = response.json()["data"]

    # The edit is in the body...
    assert body["motto"] == change["motto"]
    assert body["founded_year"] == change["founded_year"]
    # ...and the fields the request did not name are untouched, not blanked.
    assert body["name"] == _SEEDED["name"]
    assert body["description"] == _SEEDED["description"]
    assert body["clan_rules"] == _SEEDED["clan_rules"]

    # ...and the body is the STORED row, not an echo of the request. Without this a
    # route answering 200 with a pre-edit snapshot would pass every line above.
    after = await _row(session_factory, seeded["clan_id"])
    for column in _PROFILE_COLUMNS:
        assert body[column] == getattr(after, column), f"{column} differs from the row"
    assert datetime.fromisoformat(body["created_at"]) == after.created_at
    assert datetime.fromisoformat(body["updated_at"]) == after.updated_at

    # `updated_at` is the attribute the UPDATE expires, so it is the one a stale
    # instance would serve. It must have moved.
    assert after.updated_at > before.updated_at
    assert body["id"] == str(seeded["clan_id"])
    assert body["is_active"] is True


async def test_the_client_reads_a_status_code_and_the_write_is_not_orphaned(
    lenient_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    seeded: dict[str, Any],
) -> None:
    """The pair S-078 calls the worst one to hand anyone: status code beside the row.

    Against the unfixed route this reads ``(500, 'Ăn quả nhớ kẻ trồng cây')`` — the
    error and the successful write together. It must read ``(200, ...)``.
    """
    new_motto = "Ăn quả nhớ kẻ trồng cây"

    response = await lenient_client.patch(
        "/api/v1/clans/me", json={"motto": new_motto}, headers=_headers(seeded)
    )
    stored = (await _row(session_factory, seeded["clan_id"])).motto

    assert (response.status_code, stored) == (200, new_motto), response.text


async def test_a_second_consecutive_change_also_answers_200(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    seeded: dict[str, Any],
) -> None:
    """Two different edits in a row, so this is not a first-request-only reading."""
    first = await client.patch(
        "/api/v1/clans/me", json={"description": "sửa lần một"}, headers=_headers(seeded)
    )
    assert first.status_code == 200, first.text
    assert first.json()["data"]["description"] == "sửa lần một"

    second = await client.patch(
        "/api/v1/clans/me", json={"description": "sửa lần hai"}, headers=_headers(seeded)
    )
    assert second.status_code == 200, second.text
    assert second.json()["data"]["description"] == "sửa lần hai"

    row = await _row(session_factory, seeded["clan_id"])
    assert row.description == "sửa lần hai"
    assert datetime.fromisoformat(second.json()["data"]["updated_at"]) == row.updated_at


async def test_a_no_op_patch_answers_200_and_does_not_move_updated_at(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    seeded: dict[str, Any],
) -> None:
    """Documents the half of S-073's sequence that always passed. **Not the control.**

    The 200 half is green against the broken route as well, because a PATCH that writes
    the value already stored emits no UPDATE and expires nothing. It is here so the next
    reader does not mistake a passing no-op PATCH for evidence about this route, and
    because the fix must not break the path that already worked.

    The ``updated_at`` half is a reading in its own right, and it is the one the contract
    rests on (``docs/contracts/rest-clans-api.md``, "Clan info"): a no-op PATCH leaves the
    timestamp alone, which is also the proof that no UPDATE was emitted.
    """
    before = await _row(session_factory, seeded["clan_id"])
    same = {"motto": _SEEDED["motto"]}

    for _ in range(2):
        response = await client.patch("/api/v1/clans/me", json=same, headers=_headers(seeded))
        assert response.status_code == 200, response.text
        body = response.json()["data"]
        assert body["motto"] == _SEEDED["motto"]
        assert datetime.fromisoformat(body["updated_at"]) == before.updated_at

    after = await _row(session_factory, seeded["clan_id"])
    assert after.updated_at == before.updated_at
