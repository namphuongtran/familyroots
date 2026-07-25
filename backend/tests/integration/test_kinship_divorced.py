"""M8 (RED-first): divorced marriages must not be traversed as live kinship edges.

`find_relationship_path` (migration 019's frontier-BFS body) expands a `spouse` edge
from EVERY non-deleted marriage with no status filter, so a long-divorced marriage
still yields a present-tense kinship path — a `("spouse",)` "Vợ/Chồng" for an ex-spouse
and a `("parent","spouse")` "Mẹ kế/Bố dượng" for a parent's ex-spouse.

Owner decision (design 2026-07-25): exclude only `status = 'divorced'`; widowed /
separated / married still traverse (matches the system-wide `has_active_marriage`
convention). These tests pin that contract against a real Postgres + the real
`find_relationship_path` SQL function.

Assertion strategy: the PRIMARY signal is the raw edge sequence returned by
`find_relationship_path` (SELECT step, person_id, edge_type ...) — that is exactly the
thing the one-line SQL fix changes, and it is locale/i18n-independent. Tests 2 and 3
additionally corroborate with `describe_relationship` (the emitted Vietnamese term) so
the observable descriptor behaviour is pinned too.

RED today: `test_divorced_spouse_has_no_kinship_path` and
`test_divorced_stepparent_not_described` FAIL (the divorced spouse edge is still
traversed). GREEN today: the widowed, separated, and co-parent-via-child controls pass.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.services.relationship_descriptor import describe_relationship
from app.services.translator import load_translations, t

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture()
async def async_session(migrated_db_url: str) -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine(migrated_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as session:
        yield session
    await engine.dispose()


# ── real-PG seeding helpers (mirrors test_path_tiebreak / test_phase0_blockers) ──


async def _clan(s: AsyncSession) -> uuid.UUID:
    clan_id = uuid.uuid4()
    await s.execute(
        sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :s)"),
        {"id": clan_id, "s": f"c{clan_id.hex[:8]}"},
    )
    return clan_id


async def _person(
    s: AsyncSession,
    clan_id: uuid.UUID,
    creator: uuid.UUID,
    *,
    gender: str = "unknown",
    name: str = "P",
) -> uuid.UUID:
    pid = uuid.uuid4()
    await s.execute(
        sa.text(
            "INSERT INTO persons (id, full_name, gender, created_by_clan_id, created_by) "
            "VALUES (:id, :n, :g, :c, :cb)"
        ),
        {"id": pid, "n": name, "g": gender, "c": clan_id, "cb": creator},
    )
    return pid


async def _marriage(
    s: AsyncSession,
    p1: uuid.UUID,
    p2: uuid.UUID,
    clan_id: uuid.UUID,
    creator: uuid.UUID,
    *,
    status: str,
    order: int = 1,
) -> None:
    await s.execute(
        sa.text(
            "INSERT INTO marriages (id, person1_id, person2_id, status, spouse_order, "
            " created_by_clan_id, created_by) "
            "VALUES (:id, :p1, :p2, :st, :o, :cl, :cb)"
        ),
        {
            "id": uuid.uuid4(),
            "p1": p1,
            "p2": p2,
            "st": status,
            "o": order,
            "cl": clan_id,
            "cb": creator,
        },
    )


async def _parent_child(
    s: AsyncSession, parent: uuid.UUID, child: uuid.UUID, clan_id: uuid.UUID, creator: uuid.UUID
) -> None:
    await s.execute(
        sa.text(
            "INSERT INTO parent_child "
            "(id, parent_id, child_id, created_by_clan_id, relationship_type, created_by) "
            "VALUES (:id, :p, :c, :cl, 'biological', :cb)"
        ),
        {"id": uuid.uuid4(), "p": parent, "c": child, "cl": clan_id, "cb": creator},
    )


async def _find_path(
    s: AsyncSession, frm: uuid.UUID, to: uuid.UUID, clan_id: uuid.UUID
) -> list[Any]:
    return list(
        (
            await s.execute(
                sa.text(
                    "SELECT step, person_id, edge_type "
                    "FROM public.find_relationship_path(:f, :t, :c) ORDER BY step"
                ),
                {"f": frm, "t": to, "c": clan_id},
            )
        ).all()
    )


def _edges(rows: list[Any]) -> list[str]:
    """Non-null edge types along the path (the source row's edge_type is NULL)."""
    return [r.edge_type for r in rows if r.edge_type]


def _describe(rows: list[Any], gender_by_id: dict[uuid.UUID, str]) -> str:
    """Feed the SQL path rows to describe_relationship as it is fed in production."""
    path = [
        {
            "person_id": str(r.person_id),
            "full_name": "X",
            "gender": gender_by_id.get(r.person_id, "unknown"),
            "edge_type": r.edge_type,
            "birth_date": None,
            "birth_date_precision": "exact",
        }
        for r in rows
    ]
    return describe_relationship(path)


# ── Test 1: divorced direct spouse → NO kinship path (RED today) ──────────────────


async def test_divorced_spouse_has_no_kinship_path(async_session: AsyncSession) -> None:
    """A & B married then divorced, no other link → find_relationship_path returns ZERO
    rows. RED today: the divorced marriage is still traversed as a live `spouse` edge."""
    creator = uuid.uuid4()
    clan_id = await _clan(async_session)
    a = await _person(async_session, clan_id, creator, gender="male", name="A")
    b = await _person(async_session, clan_id, creator, gender="female", name="B")
    await _marriage(async_session, a, b, clan_id, creator, status="divorced")
    await async_session.commit()

    rows = await _find_path(async_session, a, b, clan_id)

    # A dissolved marriage is the ONLY link → after the fix there is no path at all.
    assert rows == [], f"divorced spouse still traversed: edges={_edges(rows)}"


# ── Test 2: divorced step-parent gone (RED today) ─────────────────────────────────


async def test_divorced_stepparent_not_described(async_session: AsyncSession) -> None:
    """C is child of P; P married X then divorced. The C→X path must NOT be
    ("parent","spouse") and must NOT describe as a step-parent. RED today: X is reached
    across P's divorced spouse edge, yielding "Mẹ kế/Bố dượng"."""
    creator = uuid.uuid4()
    clan_id = await _clan(async_session)
    p = await _person(async_session, clan_id, creator, gender="male", name="P")
    c = await _person(async_session, clan_id, creator, gender="male", name="C")
    x = await _person(async_session, clan_id, creator, gender="female", name="X")
    await _parent_child(async_session, p, c, clan_id, creator)
    await _marriage(async_session, p, x, clan_id, creator, status="divorced")
    await async_session.commit()

    rows = await _find_path(async_session, c, x, clan_id)
    edges = _edges(rows)

    # PRIMARY: X must not be reachable via a divorced spouse edge.
    assert "spouse" not in edges, f"divorced ex-step-parent still traversed: edges={edges}"
    assert tuple(edges) != ("parent", "spouse"), edges
    # Corroborate the observable descriptor: no present-tense step-parent term.
    # X is female → the RED term today is "Mẹ kế" (kinship.step_mother).
    term = _describe(rows, {c: "male", p: "male", x: "female"})
    assert term != t("kinship.step_mother"), f"still described as step-parent: {term!r}"


# ── Test 3: widowed spouse STILL kinship (control, GREEN today) ───────────────────


async def test_widowed_spouse_still_kinship(async_session: AsyncSession) -> None:
    """A & B with status='widowed' → spouse path present, describes as spouse. Pins that
    the filter is divorced-only (bereavement does not end kinship)."""
    creator = uuid.uuid4()
    clan_id = await _clan(async_session)
    a = await _person(async_session, clan_id, creator, gender="male", name="A")
    b = await _person(async_session, clan_id, creator, gender="female", name="B")
    await _marriage(async_session, a, b, clan_id, creator, status="widowed")
    await async_session.commit()

    rows = await _find_path(async_session, a, b, clan_id)
    edges = _edges(rows)

    assert edges == ["spouse"], f"widowed spouse must still traverse: edges={edges}"
    # Target B is female → the specific spouse term is "Vợ" (kinship.wife).
    assert _describe(rows, {a: "male", b: "female"}) == t("kinship.wife")


# ── Test 4: separated spouse STILL kinship (control, GREEN today) ─────────────────


async def test_separated_spouse_still_kinship(async_session: AsyncSession) -> None:
    """status='separated' → spouse path present (separated counts as active, matching
    has_active_marriage)."""
    creator = uuid.uuid4()
    clan_id = await _clan(async_session)
    a = await _person(async_session, clan_id, creator, gender="male", name="A")
    b = await _person(async_session, clan_id, creator, gender="female", name="B")
    await _marriage(async_session, a, b, clan_id, creator, status="separated")
    await async_session.commit()

    rows = await _find_path(async_session, a, b, clan_id)
    assert _edges(rows) == ["spouse"], f"separated spouse must still traverse: {_edges(rows)}"


# ── Test 5: divorced co-parents STILL linked via child (control, GREEN today) ─────


async def test_divorced_coparents_still_linked_via_child(async_session: AsyncSession) -> None:
    """A & B divorced but share child C → A↔B remain connected (path exists). Proves the
    fix removes only the spouse EDGE, not the people: today they connect via the (shorter)
    spouse edge, after the fix via child/parent — either way a path exists."""
    creator = uuid.uuid4()
    clan_id = await _clan(async_session)
    a = await _person(async_session, clan_id, creator, gender="male", name="A")
    b = await _person(async_session, clan_id, creator, gender="female", name="B")
    c = await _person(async_session, clan_id, creator, gender="male", name="C")
    await _marriage(async_session, a, b, clan_id, creator, status="divorced")
    await _parent_child(async_session, a, c, clan_id, creator)
    await _parent_child(async_session, b, c, clan_id, creator)
    await async_session.commit()

    rows = await _find_path(async_session, a, b, clan_id)

    # People are not removed: A and B stay in one connected component.
    assert len(rows) >= 2, "co-parents must stay connected after divorce"
    assert rows[0].person_id == a and rows[-1].person_id == b, [r.person_id for r in rows]

    # ...and the A→B route must NOT use the divorced marriage: it runs through the shared
    # child (A→C→B = child then parent), with no spouse edge. This also WITNESSES the fix —
    # before migration 024 the divorced spouse edge gave the shorter A→B = ['spouse'].
    assert _edges(rows) == ["child", "parent"], (
        f"co-parents must link via child, not spouse: {_edges(rows)}"
    )

    # The shared child provides a live blood route independent of the marriage.
    via_child = await _find_path(async_session, a, c, clan_id)
    assert _edges(via_child) == ["child"], _edges(via_child)


@pytest.fixture(autouse=True, scope="module")
def _load_i18n() -> None:
    load_translations()
