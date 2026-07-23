"""Real-DB tests PROVING review finding H4: when a child descends from thủy tổ via
BOTH parents (pedigree collapse), ``/tree``, ``/tree/focus``, and the export report
report DIFFERENT đời for the same person — and one parent's branch silently loses the
child.

Con theo đời cha (the desired single authority — implemented by Tasks 2-3, NOT by this
file): đời follows the FATHER line (an adoptive father counts) whenever a child is
reachable via two lineages, never the shorter ("min-depth") one. Today no consumer
implements this rule, so most tests here assert the DESIRED outcome and are EXPECTED
TO FAIL against current behavior — see each docstring for what "today" actually does.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.application.tree.handlers import TreeQueryHandler
from app.application.tree.queries import GetFocusView, GetFullTree
from app.infrastructure.persistence.export_query_port import SqlAlchemyExportQueryPort
from app.infrastructure.persistence.tree_repository import SqlAlchemyTreeRepository

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture()
async def async_session(migrated_db_url: str) -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine(migrated_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as session:
        yield session
    await engine.dispose()


async def _clan(s: AsyncSession) -> uuid.UUID:
    cid = uuid.uuid4()
    await s.execute(
        sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :s)"),
        {"id": cid, "s": f"c{cid.hex[:8]}"},
    )
    return cid


async def _person(
    s: AsyncSession,
    clan_id: uuid.UUID,
    creator: uuid.UUID,
    name: str = "P",
    *,
    gender: str = "male",
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


async def _member(
    s: AsyncSession,
    person_id: uuid.UUID,
    clan_id: uuid.UUID,
    *,
    is_founder: bool = False,
) -> None:
    await s.execute(
        sa.text(
            "INSERT INTO clan_memberships (person_id, clan_id, is_founder) VALUES (:p, :c, :f)"
        ),
        {"p": person_id, "c": clan_id, "f": is_founder},
    )


async def _pc(
    s: AsyncSession,
    parent: uuid.UUID,
    child: uuid.UUID,
    clan_id: uuid.UUID,
    creator: uuid.UUID,
    *,
    relationship_type: str = "biological",
) -> None:
    await s.execute(
        sa.text(
            "INSERT INTO parent_child "
            "(id, parent_id, child_id, created_by_clan_id, relationship_type, created_by) "
            "VALUES (:id, :p, :c, :cl, :rt, :cb)"
        ),
        {
            "id": uuid.uuid4(),
            "p": parent,
            "c": child,
            "cl": clan_id,
            "rt": relationship_type,
            "cb": creator,
        },
    )


async def _marriage(
    s: AsyncSession,
    p1: uuid.UUID,
    p2: uuid.UUID,
    clan_id: uuid.UUID,
    creator: uuid.UUID,
    *,
    spouse_order: int = 1,
) -> None:
    await s.execute(
        sa.text(
            "INSERT INTO marriages "
            "(id, person1_id, person2_id, created_by_clan_id, status, spouse_order, created_by) "
            "VALUES (:id, :p1, :p2, :c, 'married', :so, :cb)"
        ),
        {"id": uuid.uuid4(), "p1": p1, "p2": p2, "c": clan_id, "so": spouse_order, "cb": creator},
    )


async def _handler(session: AsyncSession) -> TreeQueryHandler:
    return TreeQueryHandler(SqlAlchemyTreeRepository(session))


def _find_node(tree: dict[str, Any], person_id: uuid.UUID) -> dict[str, Any] | None:
    """Recursively find a node by id ANYWHERE in a /tree response subtree
    (regardless of which parent it currently renders under)."""
    if tree.get("id") == str(person_id):
        return tree
    for child in tree.get("children", []):
        found = _find_node(child, person_id)
        if found is not None:
            return found
    return None


def _child_of(parent_node: dict[str, Any], person_id: uuid.UUID) -> dict[str, Any] | None:
    """Find ``person_id`` among ``parent_node``'s DIRECT children only (not
    recursive) — used to check which parent a pedigree-collapsed child renders
    under, and whether the OTHER parent also carries a stub for it."""
    return next((c for c in parent_node.get("children", []) if c["id"] == str(person_id)), None)


async def test_h4_family_all_consumers_agree_on_doi_4(async_session: AsyncSession) -> None:
    """THE H4 FAMILY (asymmetric collapse):
        F (male, founder, đời 1)
        ├─ S (male, F's son, đời 2)
        │   └─ GS (male, S's son, đời 3)          ← cha line
        └─ D (female, F's daughter, đời 2)         ← mẹ line
    GS + D → child C.
    Con theo đời cha: đời(C) = đời(GS) + 1 = 4.
    Min-depth (old focus/export) would say đời(D) + 1 = 3.
    ONE authority, THREE consumers, one answer — asserted here for all three.
    """
    creator = uuid.uuid4()
    clan_id = await _clan(async_session)
    f = await _person(async_session, clan_id, creator, "F")
    s = await _person(async_session, clan_id, creator, "S")
    gs = await _person(async_session, clan_id, creator, "GS")
    d = await _person(async_session, clan_id, creator, "D", gender="female")
    c = await _person(async_session, clan_id, creator, "C")
    await _member(async_session, f, clan_id, is_founder=True)
    for p in (s, gs, d, c):
        await _member(async_session, p, clan_id)
    await _pc(async_session, f, s, clan_id, creator)
    await _pc(async_session, s, gs, clan_id, creator)
    await _pc(async_session, f, d, clan_id, creator)
    await _marriage(async_session, gs, d, clan_id, creator)
    await _pc(async_session, gs, c, clan_id, creator)
    await _pc(async_session, d, c, clan_id, creator)
    await async_session.commit()

    handler = await _handler(async_session)

    full = await handler.get_full_tree(GetFullTree(clan_id=clan_id))
    c_node = _find_node(full["tree"], c)
    assert c_node is not None
    assert c_node["generation"] == 4  # /tree

    focus = await handler.get_focus_view(GetFocusView(person_id=c, clan_id=clan_id))
    assert focus["generation_of_focus"] == 4  # /tree/focus

    export_port = SqlAlchemyExportQueryPort(async_session)
    generations = await export_port.generation_map(clan_id)
    assert generations[c] == 4  # export report


async def test_h4_child_renders_under_both_parents(async_session: AsyncSession) -> None:
    """Same H4 family as above. /tree must show:
      - the FULL C node under GS (canonical, cha line): generation 4, a real
        (possibly empty) children list, no pedigree-collapse marker.
      - a STUB for C under D (mẹ line): id == C, generation == 4,
        pedigree_collapse_ref is True, no children.
    D's branch is NOT childless anymore — today it is (C is entirely missing
    from D's children, and no pedigree_collapse_ref field exists anywhere).
    """
    creator = uuid.uuid4()
    clan_id = await _clan(async_session)
    f = await _person(async_session, clan_id, creator, "F")
    s = await _person(async_session, clan_id, creator, "S")
    gs = await _person(async_session, clan_id, creator, "GS")
    d = await _person(async_session, clan_id, creator, "D", gender="female")
    c = await _person(async_session, clan_id, creator, "C")
    await _member(async_session, f, clan_id, is_founder=True)
    for p in (s, gs, d, c):
        await _member(async_session, p, clan_id)
    await _pc(async_session, f, s, clan_id, creator)
    await _pc(async_session, s, gs, clan_id, creator)
    await _pc(async_session, f, d, clan_id, creator)
    await _marriage(async_session, gs, d, clan_id, creator)
    await _pc(async_session, gs, c, clan_id, creator)
    await _pc(async_session, d, c, clan_id, creator)
    await async_session.commit()

    handler = await _handler(async_session)
    full = await handler.get_full_tree(GetFullTree(clan_id=clan_id))

    gs_node = _find_node(full["tree"], gs)
    assert gs_node is not None
    c_under_gs = _child_of(gs_node, c)
    assert c_under_gs is not None  # canonical, full node
    assert c_under_gs["generation"] == 4
    assert c_under_gs.get("pedigree_collapse_ref") is not True

    d_node = _find_node(full["tree"], d)
    assert d_node is not None
    c_under_d = _child_of(d_node, c)
    assert c_under_d is not None  # D's branch is NOT childless
    assert c_under_d["id"] == str(c)
    assert c_under_d["generation"] == 4
    assert c_under_d.get("pedigree_collapse_ref") is True
    assert c_under_d["children"] == []


async def test_symmetric_collapse_same_doi(async_session: AsyncSession) -> None:
    """SYMMETRIC collapse — both lineages the same length:
        F → S1 (m) → H (m, đời 3)
        F → S2 (m) → W (f, đời 3)
    H + W → C2.
    đời(C2) == 4 everywhere (both paths are equally long, so no min-depth vs
    theo-cha disagreement on the NUMBER is possible). The rendering side still
    has a canonical/stub distinction: canonical parent == H (father, per
    theo-cha), stub under W. Which parent "wins" today is NOT governed by any
    theo-cha rule (no such rule exists yet) — it depends on accidental SQL row
    order for the tied depth, so this half of the test may pass or fail today;
    see task-1-report.md for the observed outcome.
    """
    creator = uuid.uuid4()
    clan_id = await _clan(async_session)
    f = await _person(async_session, clan_id, creator, "F")
    s1 = await _person(async_session, clan_id, creator, "S1")
    h = await _person(async_session, clan_id, creator, "H")
    s2 = await _person(async_session, clan_id, creator, "S2")
    w = await _person(async_session, clan_id, creator, "W", gender="female")
    c2 = await _person(async_session, clan_id, creator, "C2")
    await _member(async_session, f, clan_id, is_founder=True)
    for p in (s1, h, s2, w, c2):
        await _member(async_session, p, clan_id)
    await _pc(async_session, f, s1, clan_id, creator)
    await _pc(async_session, s1, h, clan_id, creator)
    await _pc(async_session, f, s2, clan_id, creator)
    await _pc(async_session, s2, w, clan_id, creator)
    await _marriage(async_session, h, w, clan_id, creator)
    await _pc(async_session, h, c2, clan_id, creator)
    await _pc(async_session, w, c2, clan_id, creator)
    await async_session.commit()

    handler = await _handler(async_session)

    full = await handler.get_full_tree(GetFullTree(clan_id=clan_id))
    c2_node = _find_node(full["tree"], c2)
    assert c2_node is not None
    assert c2_node["generation"] == 4  # tied depths → the number always agrees

    focus = await handler.get_focus_view(GetFocusView(person_id=c2, clan_id=clan_id))
    assert focus["generation_of_focus"] == 4

    export_port = SqlAlchemyExportQueryPort(async_session)
    generations = await export_port.generation_map(clan_id)
    assert generations[c2] == 4

    h_node = _find_node(full["tree"], h)
    w_node = _find_node(full["tree"], w)
    assert h_node is not None and w_node is not None
    c2_under_h = _child_of(h_node, c2)
    c2_under_w = _child_of(w_node, c2)
    assert c2_under_h is not None  # canonical parent == H (father)
    assert c2_under_w is not None  # stub under W
    assert c2_under_w.get("pedigree_collapse_ref") is True


async def test_no_father_fallback_follows_mother(async_session: AsyncSession) -> None:
    """PIN of existing correct behavior: a child with ONLY an in-tree mother —
    the father is recorded as a parent but is NOT descended from the founder
    (married-in, no ancestry of his own) — takes đời from the mother:
    đời(child) = đời(mother) + 1. There is only one path to the founder here
    (through the mother), so no consumer can disagree; this should PASS today.
    """
    creator = uuid.uuid4()
    clan_id = await _clan(async_session)
    f2 = await _person(async_session, clan_id, creator, "F2")
    m = await _person(async_session, clan_id, creator, "M", gender="female")
    dad = await _person(async_session, clan_id, creator, "Dad")  # married-in, no ancestry
    child2 = await _person(async_session, clan_id, creator, "Child2")
    await _member(async_session, f2, clan_id, is_founder=True)
    for p in (m, dad, child2):
        await _member(async_session, p, clan_id)
    await _pc(async_session, f2, m, clan_id, creator)  # M is F2's daughter, đời 2
    await _marriage(async_session, dad, m, clan_id, creator)
    await _pc(async_session, m, child2, clan_id, creator)
    await _pc(async_session, dad, child2, clan_id, creator)
    await async_session.commit()

    handler = await _handler(async_session)

    full = await handler.get_full_tree(GetFullTree(clan_id=clan_id))
    child2_node = _find_node(full["tree"], child2)
    assert child2_node is not None
    assert child2_node["generation"] == 3  # đời(M)=2 + 1

    focus = await handler.get_focus_view(GetFocusView(person_id=child2, clan_id=clan_id))
    assert focus["generation_of_focus"] == 3

    export_port = SqlAlchemyExportQueryPort(async_session)
    generations = await export_port.generation_map(clan_id)
    assert generations[child2] == 3


async def test_adoptive_father_carries_the_line(async_session: AsyncSession) -> None:
    """Con nuôi lập tự: a child whose only in-tree FATHER edge is
    ``relationship_type='adopted'`` (the biological father is married-in / not
    descended from the founder and is not seeded here at all) — with an
    in-tree biological MOTHER who has a SHORTER line to the founder — must
    take đời from the ADOPTIVE FATHER, not the mother:
        F3 (founder, đời 1)
        ├─ X (đời 2) → AF (đời 3, adoptive father)   ← cha line, longer
        └─ BM (đời 2, biological mother)              ← mẹ line, shorter
    AF --[adopted]--> Child3 ; BM --[biological]--> Child3.
    đời(Child3) = đời(AF) + 1 = 4, NOT đời(BM) + 1 = 3.
    """
    creator = uuid.uuid4()
    clan_id = await _clan(async_session)
    f3 = await _person(async_session, clan_id, creator, "F3")
    x = await _person(async_session, clan_id, creator, "X")
    af = await _person(async_session, clan_id, creator, "AF")
    bm = await _person(async_session, clan_id, creator, "BM", gender="female")
    child3 = await _person(async_session, clan_id, creator, "Child3")
    await _member(async_session, f3, clan_id, is_founder=True)
    for p in (x, af, bm, child3):
        await _member(async_session, p, clan_id)
    await _pc(async_session, f3, x, clan_id, creator)
    await _pc(async_session, x, af, clan_id, creator)
    await _pc(async_session, f3, bm, clan_id, creator)
    await _pc(async_session, af, child3, clan_id, creator, relationship_type="adopted")
    await _pc(async_session, bm, child3, clan_id, creator)
    await async_session.commit()

    handler = await _handler(async_session)

    full = await handler.get_full_tree(GetFullTree(clan_id=clan_id))
    child3_node = _find_node(full["tree"], child3)
    assert child3_node is not None
    assert child3_node["generation"] == 4  # đời(AF)=3 + 1

    focus = await handler.get_focus_view(GetFocusView(person_id=child3, clan_id=clan_id))
    assert focus["generation_of_focus"] == 4

    export_port = SqlAlchemyExportQueryPort(async_session)
    generations = await export_port.generation_map(clan_id)
    assert generations[child3] == 4


async def test_mother_shorter_line_does_not_capture_doi(async_session: AsyncSession) -> None:
    """The divergence case isolated to its minimal shape: cha đời 3, mẹ đời 2 →
    child đời 4 (NOT 3, which is what the mother's shorter line would give).
        F4 (founder, đời 1)
        ├─ Y (đời 2) → Cha (đời 3)      ← cha line, longer
        └─ Me (đời 2)                    ← mẹ line, shorter
    Cha + Me → Child4. đời(Child4) = đời(Cha) + 1 = 4.
    """
    creator = uuid.uuid4()
    clan_id = await _clan(async_session)
    f4 = await _person(async_session, clan_id, creator, "F4")
    y = await _person(async_session, clan_id, creator, "Y")
    cha = await _person(async_session, clan_id, creator, "Cha")
    me = await _person(async_session, clan_id, creator, "Me", gender="female")
    child4 = await _person(async_session, clan_id, creator, "Child4")
    await _member(async_session, f4, clan_id, is_founder=True)
    for p in (y, cha, me, child4):
        await _member(async_session, p, clan_id)
    await _pc(async_session, f4, y, clan_id, creator)
    await _pc(async_session, y, cha, clan_id, creator)
    await _pc(async_session, f4, me, clan_id, creator)
    await _marriage(async_session, cha, me, clan_id, creator)
    await _pc(async_session, cha, child4, clan_id, creator)
    await _pc(async_session, me, child4, clan_id, creator)
    await async_session.commit()

    handler = await _handler(async_session)

    full = await handler.get_full_tree(GetFullTree(clan_id=clan_id))
    child4_node = _find_node(full["tree"], child4)
    assert child4_node is not None
    assert child4_node["generation"] == 4  # NOT 3

    focus = await handler.get_focus_view(GetFocusView(person_id=child4, clan_id=clan_id))
    assert focus["generation_of_focus"] == 4  # NOT 3

    export_port = SqlAlchemyExportQueryPort(async_session)
    generations = await export_port.generation_map(clan_id)
    assert generations[child4] == 4  # NOT 3
