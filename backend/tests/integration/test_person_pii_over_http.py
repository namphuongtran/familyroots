"""The four redacting person routes, proved by reading the response body.

**The PII-over-HTTP test.** ADR-049 § "Measurement 5" measured the gap this file closes: the
redaction rule had eight tests and **none of them issued an HTTP request**. Every
existing case calls ``handler.redact_pii(...)`` itself
(``tests/integration/test_person_pii_visibility.py:74,79,84``;
``tests/unit/application/test_person_pii_visibility.py:51,59,66,73,80``), and the two
route-level suites replace the call with a no-op that returns ``None``
(``tests/test_persons.py:60``; ``tests/unit/api/test_persons_batch_endpoint.py:85-86``).
So the four call sites were the load-bearing part of the rule and nothing watched them.
Measured twice on 2026-08-22, deleting ``app/api/v1/persons.py:337-339`` left the whole
suite at ``1351 passed`` and ``ruff check .`` at "All checks passed!".

**This file asserts the outcome, not the setting**, per ``.claude/rules/testing.md``
§ "A test pins an outcome, not a setting". It never asks whether the redaction ran, and
never counts a call. It sends a request over the real ASGI app and reads
``response.json()["data"]``, because "the response body a route sends contains no
stranger's phone number" is the only fact anyone cares about.

**One test per route, and that is deliberate.** A single case covering one route would
leave the other three exactly as unwatched as they were. The negative control for this
file deletes one ``await`` at a time — ``persons.py:126``, ``:267``, ``:337`` and
``application/person/handlers.py:148`` — and exactly one test below fails per deletion.

**Every case takes both readings in one run.** A viewer (or, for ``PATCH``, an editor)
reads ``null``, and an admin reads the number, against the same person in the same clan.
A test that only asserted the ``null`` half would pass over a route that nulled
``phone`` for everybody, which is a different bug wearing the same green.

**``test_the_stored_row_still_holds_the_number`` is the premise**, in raw SQL. Without
it the rest of the file is a claim about the seed data rather than about the read.

**``PATCH`` is covered with an ``editor``, not a viewer, and the reason is in the code.**
``PersonCommandHandler.update`` grants a viewer edit access to their own linked person
only (``handlers.py:118-140``), so a viewer patching a stranger never reaches the
redaction at ``:148`` — they get ``403 insufficient_permissions`` first. The caller that
line exists for is an editor, and its own comment says so. That matches the contract
table at ``docs/contracts/rest-persons-api.md:113-118``, where an ``editor`` sees the
contact details of their own linked person only.

Real Postgres (``migrated_db_url``), real handlers, real RBAC. Only JWT *verification* is
stubbed, the same seam and the same way ``test_relationship_by_id_soft_deleted_endpoint.py``
does it.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
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

STRANGER_PHONE = "0900000058"
STRANGER_EMAIL = "nguoi-la-s058@example.com"
OWN_PHONE = "0911111058"
OWN_EMAIL = "chinh-chu-s058@example.com"


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
    """One clan, three callers, two persons, and contact details on both persons.

    ``viewer`` is linked to ``own_person`` via ``user_profiles.person_id`` and is NOT
    linked to ``stranger`` — that link is what the redaction reads to decide. ``editor``
    and ``admin`` are linked to nobody, which is the last row of the contract table at
    ``docs/contracts/rest-persons-api.md:118``: a caller with no linked person sees
    nobody's contact details, unless they are an admin.
    """
    clan_id = uuid.uuid4()
    admin_id, editor_id, viewer_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    stranger_id, own_person_id = uuid.uuid4(), uuid.uuid4()

    async with session_factory() as s:
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'Họ S058', :slug)"),
            {"id": clan_id, "slug": f"s058-{clan_id.hex[:10]}"},
        )
        for key, name, gender, phone, email in (
            ("stranger", "Người Lạ", "male", STRANGER_PHONE, STRANGER_EMAIL),
            ("own", "Chính Chủ", "female", OWN_PHONE, OWN_EMAIL),
        ):
            pid = stranger_id if key == "stranger" else own_person_id
            await s.execute(
                sa.text(
                    "INSERT INTO persons "
                    "(id, full_name, gender, created_by_clan_id, created_by, phone, email) "
                    "VALUES (:id, :n, :g, :cid, :uid, :ph, :em)"
                ),
                {
                    "id": pid,
                    "n": name,
                    "g": gender,
                    "cid": clan_id,
                    "uid": admin_id,
                    "ph": phone,
                    "em": email,
                },
            )
            await s.execute(
                sa.text(
                    "INSERT INTO clan_memberships (person_id, clan_id, joined_at) "
                    "VALUES (:pid, :cid, now())"
                ),
                {"pid": pid, "cid": clan_id},
            )

        for uid, role, linked in (
            (admin_id, "admin", None),
            (editor_id, "editor", None),
            (viewer_id, "viewer", own_person_id),
        ):
            await s.execute(
                sa.text(
                    "INSERT INTO user_profiles (id, email, display_name, person_id) "
                    "VALUES (:id, :email, :dn, :linked)"
                ),
                {
                    "id": uid,
                    "email": f"{uid.hex[:10]}@example.com",
                    "dn": role,
                    "linked": linked,
                },
            )
            await s.execute(
                sa.text(
                    "INSERT INTO user_clan_roles "
                    "(user_id, clan_id, role, is_approved, approved_by, approved_at) "
                    "VALUES (:uid, :cid, :role, true, :uid, now())"
                ),
                {"uid": uid, "cid": clan_id, "role": role},
            )
        await s.commit()

    return {
        "clan_id": clan_id,
        "admin_id": admin_id,
        "editor_id": editor_id,
        "viewer_id": viewer_id,
        "stranger": stranger_id,
        "own_person": own_person_id,
    }


@pytest.fixture()
async def client(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncClient]:
    app = create_app()

    async def _override_db() -> AsyncGenerator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_current_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


def _headers(seeded: dict[str, Any], caller: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {seeded[caller]}",
        "X-Current-Clan-Id": str(seeded["clan_id"]),
    }


def _contact(person: dict[str, Any]) -> tuple[Any, Any]:
    """Read the two fields out of a response body, failing loudly if a key is absent.

    Key *presence* matters as much as the value: the contract says both keys are always
    on the full projection (``docs/contracts/rest-persons-api.md:152-156``), so a route
    that dropped them instead of nulling them would be a different response shape, not a
    redaction. ``person["phone"]`` raises ``KeyError`` here rather than passing.
    """
    return person["phone"], person["email"]


async def test_the_stored_row_still_holds_the_number(
    session_factory: async_sessionmaker[AsyncSession], seeded: dict[str, Any]
) -> None:
    """The premise, in raw SQL: redaction happens on the way out, not in the table.

    Without this reading, every assertion below would also pass against a seed that
    never wrote a phone number in the first place.
    """
    async with session_factory() as s:
        row = (
            await s.execute(
                sa.text("SELECT phone, email FROM persons WHERE id = :id"),
                {"id": seeded["stranger"]},
            )
        ).one()
    assert row.phone == STRANGER_PHONE
    assert row.email == STRANGER_EMAIL


async def test_get_person_by_id_sends_a_viewer_null_and_an_admin_the_number(
    client: AsyncClient, seeded: dict[str, Any]
) -> None:
    """``GET /persons/{id}`` — the call site at ``app/api/v1/persons.py:337``."""
    url = f"/api/v1/persons/{seeded['stranger']}"

    as_viewer = await client.get(url, headers=_headers(seeded, "viewer_id"))
    assert as_viewer.status_code == 200, as_viewer.text
    assert _contact(as_viewer.json()["data"]) == (None, None)

    as_admin = await client.get(url, headers=_headers(seeded, "admin_id"))
    assert as_admin.status_code == 200, as_admin.text
    assert _contact(as_admin.json()["data"]) == (STRANGER_PHONE, STRANGER_EMAIL)


async def test_the_person_list_sends_a_viewer_null_and_an_admin_the_number(
    client: AsyncClient, seeded: dict[str, Any]
) -> None:
    """``GET /persons`` — the call site at ``app/api/v1/persons.py:126``."""

    def _stranger_of(body: dict[str, Any]) -> dict[str, Any]:
        stranger = str(seeded["stranger"])
        rows: list[dict[str, Any]] = [p for p in body["data"] if p["id"] == stranger]
        assert len(rows) == 1, f"expected the stranger exactly once, got {len(rows)}"
        return rows[0]

    as_viewer = await client.get("/api/v1/persons", headers=_headers(seeded, "viewer_id"))
    assert as_viewer.status_code == 200, as_viewer.text
    assert _contact(_stranger_of(as_viewer.json())) == (None, None)

    as_admin = await client.get("/api/v1/persons", headers=_headers(seeded, "admin_id"))
    assert as_admin.status_code == 200, as_admin.text
    assert _contact(_stranger_of(as_admin.json())) == (STRANGER_PHONE, STRANGER_EMAIL)


async def test_the_batch_read_sends_a_viewer_null_and_an_admin_the_number(
    client: AsyncClient, seeded: dict[str, Any]
) -> None:
    """``POST /persons/batch`` — the call site at ``app/api/v1/persons.py:267``.

    Both persons are requested in one body, so the admin reading carries the viewer's
    own person too. That is what makes this a batch reading rather than a second
    by-id reading wearing a list.
    """
    body = {"ids": [str(seeded["stranger"]), str(seeded["own_person"])]}

    as_viewer = await client.post(
        "/api/v1/persons/batch", json=body, headers=_headers(seeded, "viewer_id")
    )
    assert as_viewer.status_code == 200, as_viewer.text
    viewer_rows = {p["id"]: p for p in as_viewer.json()["data"]}
    assert _contact(viewer_rows[str(seeded["stranger"])]) == (None, None)
    # The viewer's OWN person is untouched in the same response, so the redaction is
    # per-person and not a blanket null over the batch.
    assert _contact(viewer_rows[str(seeded["own_person"])]) == (OWN_PHONE, OWN_EMAIL)

    as_admin = await client.post(
        "/api/v1/persons/batch", json=body, headers=_headers(seeded, "admin_id")
    )
    assert as_admin.status_code == 200, as_admin.text
    admin_rows = {p["id"]: p for p in as_admin.json()["data"]}
    assert _contact(admin_rows[str(seeded["stranger"])]) == (STRANGER_PHONE, STRANGER_EMAIL)


async def test_the_patch_echo_sends_an_editor_null_and_an_admin_the_number(
    client: AsyncClient, seeded: dict[str, Any]
) -> None:
    """``PATCH /persons/{id}`` — the call site at ``app/application/person/handlers.py:148``.

    Both callers edit ``notes``, never ``phone`` or ``email``, so the two values in the
    echoed body come from storage rather than from the request that just set them. The
    editor patches first and the admin second, with the version the first edit produced,
    because ``expected_version`` is required (ADR-017).
    """
    url = f"/api/v1/persons/{seeded['stranger']}"
    current = await client.get(url, headers=_headers(seeded, "admin_id"))
    assert current.status_code == 200, current.text
    version = current.json()["data"]["version"]

    as_editor = await client.patch(
        url,
        json={"notes": "biên tập viên sửa", "expected_version": version},
        headers=_headers(seeded, "editor_id"),
    )
    assert as_editor.status_code == 200, as_editor.text
    edited = as_editor.json()["data"]
    assert edited["notes"] == "biên tập viên sửa"  # the edit really landed
    assert _contact(edited) == (None, None)

    as_admin = await client.patch(
        url,
        json={"notes": "quản trị sửa", "expected_version": edited["version"]},
        headers=_headers(seeded, "admin_id"),
    )
    assert as_admin.status_code == 200, as_admin.text
    assert _contact(as_admin.json()["data"]) == (STRANGER_PHONE, STRANGER_EMAIL)


async def test_a_viewer_reads_their_own_contact_details_over_http(
    client: AsyncClient, seeded: dict[str, Any]
) -> None:
    """The control on the whole file: the rule is about *whose* record, not about the
    two field names.

    A route that nulled ``phone`` and ``email`` unconditionally would satisfy every
    ``(None, None)`` assertion above. It fails here.
    """
    mine = await client.get(
        f"/api/v1/persons/{seeded['own_person']}", headers=_headers(seeded, "viewer_id")
    )
    assert mine.status_code == 200, mine.text
    assert _contact(mine.json()["data"]) == (OWN_PHONE, OWN_EMAIL)
