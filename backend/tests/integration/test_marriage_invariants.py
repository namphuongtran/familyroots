"""RED: A7 marriage invariants — M1 (PATCH date-order bypass) + M7 (two-sided
spouse_order uniqueness).

Real Postgres (migrated_db_url), real RBAC. Mirrors
tests/integration/test_relationship_update_validation.py: only JWT
*verification* is stubbed (the Authorization header carries the user id
directly), so these tests focus on the marriage aggregate's create/PATCH
business rules, not auth.

M1 — ``MarriageCreateRequest.validate_marriage`` (a pydantic model validator)
blocks ``divorce_date < marriage_date`` at create time, but
``MarriageUpdateRequest`` has no equivalent check and
``MarriageCommandHandler.update`` never re-validates date order — a PATCH can
put a marriage into a state CREATE would have rejected.

M7 — ``RelationshipDomainValidator.check_spouse_order`` /
``has_spouse_order_conflict`` key the uniqueness check on ``person1_id``
only. Because ``(person1_id, person2_id)`` is an unordered pair (either
spouse may land in either column), creating the same logical marriage with
the operands flipped — ``(W2, H)`` instead of ``(H, W2)`` — searches a
different column and never finds the existing ``(H, W1)`` row at the same
spouse_order, so a second "vợ cả" (order=1) can be created undetected.

Task 2 fixes both; this file only proves the gap (RED) and pins today's
controls (GREEN).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi import Header
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.core.security import get_current_user
from app.main import create_app

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


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
    """A clan plus an approved editor membership."""
    clan_id = uuid.uuid4()
    editor_id = uuid.uuid4()
    async with session_factory() as s:
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'Marriage Inv Clan', :slug)"),
            {"id": clan_id, "slug": f"minv-{clan_id.hex[:8]}"},
        )
        await s.execute(
            sa.text(
                "INSERT INTO user_profiles (id, email, display_name) VALUES (:id, :email, :name)"
            ),
            {"id": editor_id, "email": f"{editor_id.hex[:8]}@example.com", "name": "editor"},
        )
        await s.execute(
            sa.text(
                "INSERT INTO user_clan_roles "
                "(user_id, clan_id, role, is_approved, approved_by, approved_at) "
                "VALUES (:uid, :cid, 'editor', true, :uid, now())"
            ),
            {"uid": editor_id, "cid": clan_id},
        )
        await s.commit()
    return {"clan_id": clan_id, "editor_id": editor_id}


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


@pytest.fixture()
def editor_headers(seeded: dict[str, Any]) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {seeded['editor_id']}",
        "X-Current-Clan-Id": str(seeded["clan_id"]),
    }


async def _make_person(
    client: AsyncClient,
    headers: dict[str, str],
    name: str,
    gender: str,
) -> str:
    resp = await client.post(
        "/api/v1/persons", headers=headers, json={"full_name": name, "gender": gender}
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["data"]["id"])


async def _create_marriage(
    client: AsyncClient,
    headers: dict[str, str],
    person1_id: str,
    person2_id: str,
    **kwargs: Any,
) -> Any:
    body: dict[str, Any] = {"person1_id": person1_id, "person2_id": person2_id, **kwargs}
    return await client.post("/api/v1/relationships/marriages", headers=headers, json=body)


# ── M1: divorce_date must not precede marriage_date ──────────────────────────


async def test_marriage_create_still_blocks_divorce_before_marriage(
    client: AsyncClient, editor_headers: dict[str, str]
) -> None:
    """Regression pin (GREEN today): CREATE already blocks this via
    ``MarriageCreateRequest.validate_marriage`` (a pydantic model validator),
    surfaced as the app's generic 422 request-validation envelope — not the
    domain ``relationship.divorce_before_marriage`` code, which only exists on
    the (currently missing) update-path check."""
    h = await _make_person(client, editor_headers, "Husband M1a", "male")
    w = await _make_person(client, editor_headers, "Wife M1a", "female")

    resp = await _create_marriage(
        client,
        editor_headers,
        h,
        w,
        status="divorced",
        marriage_date="1950-01-01",
        divorce_date="1940-01-01",
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "validation_error"


async def test_marriage_update_blocks_divorce_before_marriage(
    client: AsyncClient, editor_headers: dict[str, str]
) -> None:
    """RED today: PATCH has no date-order re-validation —
    ``MarriageUpdateRequest`` carries no ``validate_marriage``-equivalent check
    and ``MarriageCommandHandler.update`` never re-derives/validates effective
    dates. The data itself is NOT corrupted (a pre-existing DB CHECK
    ``marriages_divorce_after_marriage``, migration 001, refuses the write) —
    but that ``CheckViolation`` is unmapped by ``integrity_error_handler``, so
    today this PATCH surfaces a raw **500 internal_error** instead of the clean
    domain ``relationship.divorce_before_marriage`` 422. Task 2's pre-write
    domain check short-circuits before the DB call, turning the 500 into the
    422 CREATE would have raised for the same date pair."""
    h = await _make_person(client, editor_headers, "Husband M1b", "male")
    w = await _make_person(client, editor_headers, "Wife M1b", "female")

    created = await _create_marriage(
        client, editor_headers, h, w, status="married", marriage_date="1950-01-01"
    )
    assert created.status_code == 201, created.text
    data = created.json()["data"]

    resp = await client.patch(
        f"/api/v1/relationships/marriages/{data['id']}",
        headers=editor_headers,
        json={
            "divorce_date": "1940-01-01",
            "status": "divorced",
            "expected_version": data["version"],
        },
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "relationship.divorce_before_marriage"


async def test_marriage_update_blocks_marriage_after_divorce(
    client: AsyncClient, editor_headers: dict[str, str]
) -> None:
    """RED today: same gap from the other side — a marriage already divorced
    (marriage=1950, divorce=1960) gets its marriage_date PATCHed to 1970 (after
    its own divorce_date). Nothing re-derives/validates the effective date pair
    on update; the DB CHECK refuses it but the unmapped CheckViolation surfaces
    as a raw **500** today (not 200), which Task 2's pre-write domain check
    turns into a clean 422."""
    h = await _make_person(client, editor_headers, "Husband M1c", "male")
    w = await _make_person(client, editor_headers, "Wife M1c", "female")

    created = await _create_marriage(
        client,
        editor_headers,
        h,
        w,
        status="divorced",
        marriage_date="1950-01-01",
        divorce_date="1960-01-01",
    )
    assert created.status_code == 201, created.text
    data = created.json()["data"]

    resp = await client.patch(
        f"/api/v1/relationships/marriages/{data['id']}",
        headers=editor_headers,
        json={"marriage_date": "1970-01-01", "expected_version": data["version"]},
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "relationship.divorce_before_marriage"


async def test_marriage_update_allows_valid_dates(
    client: AsyncClient, editor_headers: dict[str, str]
) -> None:
    """Control (PASS today and after the fix): divorce_date after
    marriage_date is a legitimate PATCH and must keep succeeding."""
    h = await _make_person(client, editor_headers, "Husband M1d", "male")
    w = await _make_person(client, editor_headers, "Wife M1d", "female")

    created = await _create_marriage(
        client, editor_headers, h, w, status="married", marriage_date="1950-01-01"
    )
    assert created.status_code == 201, created.text
    data = created.json()["data"]

    resp = await client.patch(
        f"/api/v1/relationships/marriages/{data['id']}",
        headers=editor_headers,
        json={
            "divorce_date": "1990-01-01",
            "status": "divorced",
            "expected_version": data["version"],
        },
    )
    assert resp.status_code == 200, resp.text


# ── M7: spouse_order uniqueness must be orientation-independent ─────────────


async def test_spouse_order_flip_orientation_is_caught(
    client: AsyncClient, editor_headers: dict[str, str]
) -> None:
    """RED today: (H, W1, order=1) exists. Creating (W2, H, order=1) — the
    SAME father H, same order, but with H in the person2 column this time —
    must be caught as a second "vợ cả" for H. ``check_spouse_order`` /
    ``has_spouse_order_conflict`` only filter on ``person1_id``, so the
    flipped orientation searches a column H never occupies in the new row
    and misses the existing marriage entirely: this currently returns 201."""
    h = await _make_person(client, editor_headers, "Husband M7a", "male")
    w1 = await _make_person(client, editor_headers, "Wife M7a-1", "female")
    w2 = await _make_person(client, editor_headers, "Wife M7a-2", "female")

    first = await _create_marriage(client, editor_headers, h, w1, spouse_order=1)
    assert first.status_code == 201, first.text

    flipped = await _create_marriage(client, editor_headers, w2, h, spouse_order=1)
    assert flipped.status_code == 409, flipped.text
    assert flipped.json()["error"]["code"] == "relationship.duplicate_spouse_order"


async def test_da_the_distinct_orders_allowed(
    client: AsyncClient, editor_headers: dict[str, str]
) -> None:
    """Control (PASS today and after the fix): legitimate đa thê — the same
    father marrying two wives at DISTINCT spouse_order values — must keep
    succeeding for both."""
    h = await _make_person(client, editor_headers, "Husband M7b", "male")
    w1 = await _make_person(client, editor_headers, "Wife M7b-1", "female")
    w2 = await _make_person(client, editor_headers, "Wife M7b-2", "female")

    first = await _create_marriage(client, editor_headers, h, w1, spouse_order=1)
    assert first.status_code == 201, first.text

    second = await _create_marriage(client, editor_headers, h, w2, spouse_order=2)
    assert second.status_code == 201, second.text


async def test_spouse_order_update_flip_caught(
    client: AsyncClient, editor_headers: dict[str, str]
) -> None:
    """RED today: marriage A = (H, W1, order=1); marriage B = (W2, H,
    order=2) — B is stored with H in person2, so it's invisible to the
    person1-only spouse_order check for H. PATCHing B's spouse_order to 1
    must collide with A (H would have two order=1 marriages across
    orientations); this currently succeeds (200) instead.

    Also pins the exclude-self control: PATCHing A's OWN spouse_order back to
    its current value (1) must stay a no-op success, not a false collision
    with itself — this already passes today via ``exclude_marriage_id``."""
    h = await _make_person(client, editor_headers, "Husband M7c", "male")
    w1 = await _make_person(client, editor_headers, "Wife M7c-1", "female")
    w2 = await _make_person(client, editor_headers, "Wife M7c-2", "female")

    a = await _create_marriage(client, editor_headers, h, w1, spouse_order=1)
    assert a.status_code == 201, a.text
    a_data = a.json()["data"]

    b = await _create_marriage(client, editor_headers, w2, h, spouse_order=2)
    assert b.status_code == 201, b.text
    b_data = b.json()["data"]

    flip = await client.patch(
        f"/api/v1/relationships/marriages/{b_data['id']}",
        headers=editor_headers,
        json={"spouse_order": 1, "expected_version": b_data["version"]},
    )
    assert flip.status_code == 409, flip.text
    assert flip.json()["error"]["code"] == "relationship.duplicate_spouse_order"

    # Exclude-self control: A patched to its own existing order must be fine.
    self_patch = await client.patch(
        f"/api/v1/relationships/marriages/{a_data['id']}",
        headers=editor_headers,
        json={"spouse_order": 1, "expected_version": a_data["version"]},
    )
    assert self_patch.status_code == 200, self_patch.text


async def test_polyandry_same_rank_rejected_ADR029(
    client: AsyncClient, editor_headers: dict[str, str]
) -> None:
    """RED today (accepted consequence, per ADR-029 — NOT a bug once Task 2
    lands): the two-sided per-person spouse_order invariant treats
    spouse_order as "this person's Nth live spouse" for EITHER side of the
    pair, not just the person1 (traditionally husband) side. So two DIFFERENT
    husbands (H1, H2) each marrying the SAME wife W1 at order=1 collide on
    W1's side of the check, even though neither husband individually has a
    duplicate order — a deliberate over-reject of the rare polyandry /
    dual-live-household case, accepted under the polygyny model per ADR-029.
    Today (pre-fix, person1-only check) both creates succeed at 201; this
    test pins the DESIRED post-fix behavior and is expected to fail until
    Task 2 lands."""
    h1 = await _make_person(client, editor_headers, "Husband M7d-1", "male")
    h2 = await _make_person(client, editor_headers, "Husband M7d-2", "male")
    w1 = await _make_person(client, editor_headers, "Wife M7d", "female")

    first = await _create_marriage(client, editor_headers, h1, w1, spouse_order=1)
    assert first.status_code == 201, first.text

    second = await _create_marriage(client, editor_headers, h2, w1, spouse_order=1)
    assert second.status_code == 409, second.text
    assert second.json()["error"]["code"] == "relationship.duplicate_spouse_order"


async def test_divorced_marriage_excluded_from_spouse_order(
    client: AsyncClient, editor_headers: dict[str, str]
) -> None:
    """Control (PASS today and after the fix): a DIVORCED marriage at the same
    spouse_order is exempt from the uniqueness check on both sides — it has
    left the "live spouse" set, so (H, W1, order=1, married) plus
    (H, W2, order=1, divorced) must both be allowed to exist."""
    h = await _make_person(client, editor_headers, "Husband M7e", "male")
    w1 = await _make_person(client, editor_headers, "Wife M7e-1", "female")
    w2 = await _make_person(client, editor_headers, "Wife M7e-2", "female")

    married = await _create_marriage(
        client, editor_headers, h, w1, status="married", spouse_order=1
    )
    assert married.status_code == 201, married.text

    divorced = await _create_marriage(
        client, editor_headers, h, w2, status="divorced", spouse_order=1
    )
    assert divorced.status_code == 201, divorced.text


async def test_widowed_marriage_still_blocks_same_spouse_order(
    client: AsyncClient, editor_headers: dict[str, str]
) -> None:
    """ADR-029 residual 3 (intended, not an over-reject): the spouse_order check
    filters status <> 'divorced' ONLY, so a WIDOWED marriage still holds its rank.
    A husband widowed from his vợ cả (order=1, status='widowed' — the truthful
    record of a deceased first wife) cannot record a NEW wife at order=1: vợ cả is
    historically singular, so the remarriage is vợ kế (a distinct order), not a
    second 'first wife'. Contrast test_divorced_marriage_excluded (divorced DOES
    free the slot)."""
    h = await _make_person(client, editor_headers, "Husband M7f", "male")
    w1 = await _make_person(client, editor_headers, "Wife M7f-1", "female")
    w2 = await _make_person(client, editor_headers, "Wife M7f-2", "female")

    widowed = await _create_marriage(
        client, editor_headers, h, w1, status="widowed", spouse_order=1
    )
    assert widowed.status_code == 201, widowed.text

    remarriage = await _create_marriage(
        client, editor_headers, h, w2, status="married", spouse_order=1
    )
    assert remarriage.status_code == 409, remarriage.text
    assert remarriage.json()["error"]["code"] == "relationship.duplicate_spouse_order"
