"""Real-DB tests for the tree focus data API (get_ancestors dedup, enrichment, handler)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.application.tree.handlers import TreeQueryHandler
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
    branch_id: uuid.UUID | None = None,
) -> None:
    await s.execute(
        sa.text(
            "INSERT INTO clan_memberships (person_id, clan_id, is_founder, branch_id) "
            "VALUES (:p, :c, :f, :b)"
        ),
        {"p": person_id, "c": clan_id, "f": is_founder, "b": branch_id},
    )


async def _pc(
    s: AsyncSession,
    parent: uuid.UUID,
    child: uuid.UUID,
    clan_id: uuid.UUID,
    creator: uuid.UUID,
    *,
    birth_order: int | None = None,
) -> None:
    await s.execute(
        sa.text(
            "INSERT INTO parent_child "
            "(id, parent_id, child_id, created_by_clan_id, relationship_type, birth_order, "
            " created_by) "
            "VALUES (:id, :p, :c, :cl, 'biological', :bo, :cb)"
        ),
        {
            "id": uuid.uuid4(),
            "p": parent,
            "c": child,
            "cl": clan_id,
            "bo": birth_order,
            "cb": creator,
        },
    )


async def test_get_ancestors_no_duplicates_on_fan_out(async_session: AsyncSession) -> None:
    """A child with TWO parents must not duplicate shared grandparents in the ancestor list."""
    creator = uuid.uuid4()
    clan_id = await _clan(async_session)
    gp = await _person(async_session, clan_id, creator, "GP")  # shared grandparent
    dad = await _person(async_session, clan_id, creator, "Dad")
    mom = await _person(async_session, clan_id, creator, "Mom")
    child = await _person(async_session, clan_id, creator, "Child")
    for p in (gp, dad, mom, child):
        await _member(async_session, p, clan_id)
    # gp is the parent of BOTH dad and mom → fan-out at the grandparent level.
    await _pc(async_session, gp, dad, clan_id, creator)
    await _pc(async_session, gp, mom, clan_id, creator)
    await _pc(async_session, dad, child, clan_id, creator)
    await _pc(async_session, mom, child, clan_id, creator)
    await async_session.commit()

    ancestors = await SqlAlchemyTreeRepository(async_session).get_ancestors(child, clan_id)

    ids = [a["id"] for a in ancestors]
    assert len(ids) == len(set(ids)), ids  # the old inline SQL fanned gp out twice
    assert str(gp) in ids and str(child) in ids
    # shape preserved: no child_id key leaked into the public /tree/ancestors output
    assert "child_id" not in ancestors[0]


async def _marriage(
    s: AsyncSession,
    p1: uuid.UUID,
    p2: uuid.UUID,
    clan_id: uuid.UUID,
    creator: uuid.UUID,
    *,
    spouse_order: int,
) -> None:
    await s.execute(
        sa.text(
            "INSERT INTO marriages "
            "(id, person1_id, person2_id, created_by_clan_id, status, spouse_order, created_by) "
            "VALUES (:id, :p1, :p2, :c, 'married', :so, :cb)"
        ),
        {"id": uuid.uuid4(), "p1": p1, "p2": p2, "c": clan_id, "so": spouse_order, "cb": creator},
    )


async def _branch(s: AsyncSession, clan_id: uuid.UUID, name: str, order: int) -> uuid.UUID:
    bid = uuid.uuid4()
    await s.execute(
        sa.text("INSERT INTO branches (id, clan_id, name, branch_order) VALUES (:id,:c,:n,:o)"),
        {"id": bid, "c": clan_id, "n": name, "o": order},
    )
    return bid


async def test_build_focus_view_enriches_generation_branch_sort_hasmore(
    async_session: AsyncSession,
) -> None:
    from app.services.tree_builder import DoiEntry, build_focus_view

    creator = uuid.uuid4()
    clan_id = await _clan(async_session)
    chi1 = await _branch(async_session, clan_id, "Chi Nhất", 1)
    chi2 = await _branch(async_session, clan_id, "Chi Hai", 2)

    root = await _person(async_session, clan_id, creator, "Root")  # focus, đời anchor = 3
    son_b = await _person(async_session, clan_id, creator, "Bình")  # birth_order 2
    son_a = await _person(async_session, clan_id, creator, "An")  # birth_order 1
    grand = await _person(async_session, clan_id, creator, "Cháu")  # under An
    ggrand = await _person(async_session, clan_id, creator, "Chắt")  # under Cháu (cut off)
    for p in (root, grand, ggrand):
        await _member(async_session, p, clan_id)
    await _member(async_session, son_a, clan_id, branch_id=chi1)
    await _member(async_session, son_b, clan_id, branch_id=chi2)
    await _pc(async_session, root, son_b, clan_id, creator, birth_order=2)
    await _pc(async_session, root, son_a, clan_id, creator, birth_order=1)
    await _pc(async_session, son_a, grand, clan_id, creator)
    await _pc(async_session, grand, ggrand, clan_id, creator)  # depth 2 → cut when descendants=2
    await async_session.commit()

    # This test exercises build_focus_view's enrichment logic (branch/birth_order
    # sort/has_more) in isolation from compute_generation_map, so the đời authority's
    # map is hand-built here with the same absolute-per-person shape the real map
    # would produce (root=3, its children=4, grandchild=5) — replacing the old
    # base_generation int + depth arithmetic this function no longer does.
    doi_map = {
        root: DoiEntry(3, None),
        son_a: DoiEntry(4, root),
        son_b: DoiEntry(4, root),
        grand: DoiEntry(5, son_a),
    }
    tree = await build_focus_view(async_session, root, clan_id, descendant_depth=2, doi_map=doi_map)

    assert tree["generation"] == 3  # focus stamped with base
    # children sorted by birth_order → An (1) before Bình (2), not alphabetical/birth_date
    assert [c["full_name"] for c in tree["children"]] == ["An", "Bình"]
    an = tree["children"][0]
    assert an["generation"] == 4  # base + depth 1
    assert an["branch_name"] == "Chi Nhất" and an["branch_order"] == 1
    chau = an["children"][0]
    assert chau["generation"] == 5 and chau["depth"] == 2
    assert chau["has_more_descendants"] is True  # Chắt exists below the cutoff
    assert tree["children"][1]["has_more_descendants"] is False  # Bình is childless


async def test_build_focus_view_null_base_generation(async_session: AsyncSession) -> None:
    from app.services.tree_builder import build_focus_view

    creator = uuid.uuid4()
    clan_id = await _clan(async_session)
    root = await _person(async_session, clan_id, creator, "Root")
    await _member(async_session, root, clan_id)
    await async_session.commit()

    tree = await build_focus_view(async_session, root, clan_id, 2, None)
    assert tree["generation"] is None  # unknown đời stays null
    assert tree["has_more_descendants"] is False
    assert tree["children"] == []


async def _handler(session: AsyncSession) -> TreeQueryHandler:
    return TreeQueryHandler(SqlAlchemyTreeRepository(session))


async def test_focus_view_at_founder(async_session: AsyncSession) -> None:
    from app.application.tree.queries import GetFocusView
    from app.domain.shared.exceptions import EntityNotFoundError

    creator = uuid.uuid4()
    clan_id = await _clan(async_session)
    to = await _person(async_session, clan_id, creator, "Thủy Tổ")
    son = await _person(async_session, clan_id, creator, "Con")
    grand = await _person(async_session, clan_id, creator, "Cháu")
    await _member(async_session, to, clan_id, is_founder=True)
    await _member(async_session, son, clan_id)
    await _member(async_session, grand, clan_id)
    await _pc(async_session, to, son, clan_id, creator)
    await _pc(async_session, son, grand, clan_id, creator)
    await async_session.commit()

    handler = await _handler(async_session)
    view = await handler.get_focus_view(
        GetFocusView(person_id=to, clan_id=clan_id, descendant_depth=2)
    )

    assert view["focus_person_id"] == str(to)
    assert view["generation_of_focus"] == 1
    assert view["ancestors"] == []  # founder has no breadcrumb
    assert view["focus_subtree"]["generation"] == 1
    assert view["focus_subtree"]["children"][0]["generation"] == 2

    # focus at the grandchild → breadcrumb thủy-tổ-first with correct đời
    view2 = await handler.get_focus_view(GetFocusView(person_id=grand, clan_id=clan_id))
    assert view2["generation_of_focus"] == 3
    crumbs = view2["ancestors"]
    assert [c["full_name"] for c in crumbs] == ["Thủy Tổ", "Con"]
    assert [c["generation"] for c in crumbs] == [1, 2]
    assert crumbs[0]["is_founder"] is True and crumbs[1]["is_founder"] is False
    # grand has no children → childless focus still returns a populated lone node
    assert view2["focus_subtree"]["children"] == []

    with pytest.raises(EntityNotFoundError):
        await handler.get_focus_view(GetFocusView(person_id=uuid.uuid4(), clan_id=clan_id))


async def test_focus_view_no_founder_null_generation(async_session: AsyncSession) -> None:
    from app.application.tree.queries import GetFocusView

    creator = uuid.uuid4()
    clan_id = await _clan(async_session)
    a = await _person(async_session, clan_id, creator, "A")
    b = await _person(async_session, clan_id, creator, "B")
    await _member(async_session, a, clan_id)  # no is_founder anywhere
    await _member(async_session, b, clan_id)
    await _pc(async_session, a, b, clan_id, creator)
    await async_session.commit()

    handler = await _handler(async_session)
    view = await handler.get_focus_view(GetFocusView(person_id=b, clan_id=clan_id))
    assert view["generation_of_focus"] is None
    assert view["focus_subtree"]["generation"] is None
    assert all(c["generation"] is None for c in view["ancestors"])  # view still returned


async def test_focus_view_clan_isolation(async_session: AsyncSession) -> None:
    """A person of clan A must be invisible through clan B: querying it with the
    clan-B header 404s. The other leak direction — foreign-clan edges/spouses never
    surfacing inside a *valid* clan-A focus view — is covered by
    ``test_focus_view_no_cross_clan_leak`` below."""
    from app.application.tree.queries import GetFocusView
    from app.domain.shared.exceptions import EntityNotFoundError

    creator = uuid.uuid4()
    clan_a = await _clan(async_session)
    clan_b = await _clan(async_session)
    pa = await _person(async_session, clan_a, creator, "A-only")
    await _member(async_session, pa, clan_a)
    await async_session.commit()

    handler = await _handler(async_session)
    with pytest.raises(EntityNotFoundError):
        await handler.get_focus_view(GetFocusView(person_id=pa, clan_id=clan_b))


async def test_focus_view_no_cross_clan_leak(async_session: AsyncSession) -> None:
    """The other isolation direction: a clan-A focus person's view must never surface
    edges/spouses recorded by a DIFFERENT clan, even though those edges reference the
    same (clan-A) focus person. A child linked via a clan-B-owned parent_child edge,
    and a spouse linked via a clan-B-owned marriage, must both be absent from a
    clan-A focus view of that person."""
    from app.application.tree.queries import GetFocusView

    creator = uuid.uuid4()
    clan_a = await _clan(async_session)
    clan_b = await _clan(async_session)
    focus = await _person(async_session, clan_a, creator, "Focus")
    await _member(async_session, focus, clan_a)  # focus person is a clan-A member

    # Child reachable from focus only via an edge OWNED by clan B.
    child_b = await _person(async_session, clan_b, creator, "ChildOfClanB")
    await _pc(async_session, focus, child_b, clan_b, creator)

    # Spouse recorded only by clan B.
    spouse_b = await _person(async_session, clan_b, creator, "SpouseOfClanB")
    await _marriage(async_session, focus, spouse_b, clan_b, creator, spouse_order=1)
    await async_session.commit()

    handler = await _handler(async_session)
    view = await handler.get_focus_view(GetFocusView(person_id=focus, clan_id=clan_a))

    assert view["focus_subtree"]["children"] == []  # clan-B-owned child never surfaces
    assert view["focus_subtree"]["spouses"] == []  # clan-B-recorded spouse never surfaces


async def test_focus_view_dedupes_breadcrumb_on_pedigree_collapse(
    async_session: AsyncSession,
) -> None:
    """A grandparent reachable via two parents of the focus person must appear once
    in the breadcrumb (get_ancestors_flat is per-lineage-edge, not deduplicated)."""
    from app.application.tree.queries import GetFocusView

    creator = uuid.uuid4()
    clan_id = await _clan(async_session)
    gp = await _person(async_session, clan_id, creator, "GP")  # shared grandparent
    dad = await _person(async_session, clan_id, creator, "Dad")
    mom = await _person(async_session, clan_id, creator, "Mom")
    child = await _person(async_session, clan_id, creator, "Child")
    for p in (gp, dad, mom, child):
        await _member(async_session, p, clan_id)
    # gp is the parent of BOTH dad and mom → fan-out at the grandparent level,
    # so gp is reachable via two distinct lineage edges in get_ancestors_flat.
    await _pc(async_session, gp, dad, clan_id, creator)
    await _pc(async_session, gp, mom, clan_id, creator)
    await _pc(async_session, dad, child, clan_id, creator)
    await _pc(async_session, mom, child, clan_id, creator)
    await async_session.commit()

    handler = await _handler(async_session)
    view = await handler.get_focus_view(GetFocusView(person_id=child, clan_id=clan_id))

    ids = [c["id"] for c in view["ancestors"]]
    assert len(ids) == len(set(ids)), ids  # gp must not appear twice
    assert str(gp) in ids


async def test_full_tree_generation_is_graph_computed(async_session: AsyncSession) -> None:
    """GET /tree computes đời from the graph (thủy tổ=1), ignoring a wrong hand-entered
    clan_memberships.generation."""
    from app.application.tree.handlers import TreeQueryHandler
    from app.application.tree.queries import GetFullTree

    creator = uuid.uuid4()
    clan_id = await _clan(async_session)
    to = await _person(async_session, clan_id, creator, "To")
    son = await _person(async_session, clan_id, creator, "Con")
    grand = await _person(async_session, clan_id, creator, "Chau")
    await _member(async_session, to, clan_id, is_founder=True)
    # Seed a WRONG hand-entered generation to prove it's ignored.
    await async_session.execute(
        sa.text("UPDATE clan_memberships SET generation = 99 WHERE person_id = :p"), {"p": son}
    )
    await _member(async_session, son, clan_id)
    await _member(async_session, grand, clan_id)
    await _pc(async_session, to, son, clan_id, creator)
    await _pc(async_session, son, grand, clan_id, creator)
    await async_session.commit()

    handler = TreeQueryHandler(SqlAlchemyTreeRepository(async_session))
    result = await handler.get_full_tree(GetFullTree(clan_id=clan_id))
    tree = result["tree"]
    assert tree["generation"] == 1  # thủy tổ
    assert tree["children"][0]["generation"] == 2  # not 99
    assert tree["children"][0]["children"][0]["generation"] == 3


async def test_focus_view_dedup_keeps_shallowest_when_reachable_at_two_depths(
    async_session: AsyncSession,
) -> None:
    """The SAME ancestor reachable at two different depths — once as a direct parent
    (depth 1) and once as a grandparent via a different lineage (depth 2) — must be
    deduped to exactly one breadcrumb entry, and that entry must be the SHALLOWEST
    occurrence. This distinguishes "keep shallowest" from a dedup that merely keeps
    "any" occurrence.

    Post-A4 (ADR-027), đời is graph-absolute per person (compute_generation_map), so
    the old ``x_entry["generation"] == base_generation - 1`` proxy can no longer
    distinguish "kept depth 1" from "kept depth 2". The BLACK-BOX observable that
    still discriminates is breadcrumb ORDER: ancestors are sorted by the SURVIVING
    occurrence's depth (descending), so with X reachable at depths {1, 3} and W fixed
    at depth 2, "shallowest kept" places W strictly BEFORE X in the breadcrumb, while
    a dedup that kept the deepest occurrence would place X (depth 3) before W —
    sabotage-verified: reversing the handler's dedup scan flips this assert."""
    from app.application.tree.queries import GetFocusView
    from app.infrastructure.persistence.tree_repository import SqlAlchemyTreeRepository

    creator = uuid.uuid4()
    clan_id = await _clan(async_session)
    to = await _person(async_session, clan_id, creator, "To")  # thủy tổ, further back
    x = await _person(async_session, clan_id, creator, "X")  # reachable at depth 1 AND 3
    w = await _person(async_session, clan_id, creator, "W")  # fixed at depth 2
    y = await _person(async_session, clan_id, creator, "Y")  # focus's other parent
    f = await _person(async_session, clan_id, creator, "F")  # focus person
    for p in (x, w, y, f):
        await _member(async_session, p, clan_id)
    await _member(async_session, to, clan_id, is_founder=True)

    # to -> x -> f: X is a direct parent of F (depth 1).
    # x -> w -> y -> f: X is ALSO F's great-grandparent via W and Y (depth 3),
    # with W sitting at a fixed depth 2 between the two X occurrences.
    await _pc(async_session, to, x, clan_id, creator)
    await _pc(async_session, x, f, clan_id, creator)
    await _pc(async_session, x, w, clan_id, creator)
    await _pc(async_session, w, y, clan_id, creator)
    await _pc(async_session, y, f, clan_id, creator)
    await async_session.commit()

    # Confirm the setup genuinely puts X at depths {1, 3} and W at exactly {2}.
    raw_chain = await SqlAlchemyTreeRepository(async_session).get_ancestors_flat(f, clan_id, 50)
    x_depths = {row["depth"] for row in raw_chain if row["id"] == str(x)}
    assert x_depths == {1, 3}
    w_depths = {row["depth"] for row in raw_chain if row["id"] == str(w)}
    assert w_depths == {2}

    handler = await _handler(async_session)
    view = await handler.get_focus_view(GetFocusView(person_id=f, clan_id=clan_id))

    ids = [c["id"] for c in view["ancestors"]]
    assert ids.count(str(x)) == 1  # X must not appear twice

    # Breadcrumb order discriminates which occurrence survived: sorted by surviving
    # depth DESC, shallowest-kept gives X depth 1 → W (depth 2) strictly before X;
    # deepest-kept would give X depth 3 → X before W.
    assert ids.index(str(w)) < ids.index(str(x)), (
        f"X's deep occurrence survived dedup — breadcrumb order {ids} places X before W"
    )


async def test_focus_view_generation_independent_of_breadcrumb_depth(
    async_session: AsyncSession,
) -> None:
    """PINS the đời contract: đời is an intrinsic graph property computed from a FULL
    ancestor lookup (fixed max 50), deliberately independent of the request's
    ``ancestor_depth``. A short breadcrumb request must not truncate or null the đời
    labels, even when the founder sits deeper than the requested breadcrumb window.

    Discriminating: if ``_base_generation`` regressed to derive đời from the
    depth-capped breadcrumb ``chain`` (the old inline-loop behavior) instead of a
    fixed full-depth lookup, the founder (at depth 4 from the focus person) would
    never appear in an ancestor_depth=2 chain, and generation_of_focus would come
    back None instead of 5."""
    from app.application.tree.queries import GetFocusView

    creator = uuid.uuid4()
    clan_id = await _clan(async_session)
    to = await _person(async_session, clan_id, creator, "ThuyTo")
    g2 = await _person(async_session, clan_id, creator, "G2")
    g3 = await _person(async_session, clan_id, creator, "G3")
    g4 = await _person(async_session, clan_id, creator, "G4")
    focus = await _person(async_session, clan_id, creator, "Focus")
    await _member(async_session, to, clan_id, is_founder=True)
    for p in (g2, g3, g4, focus):
        await _member(async_session, p, clan_id)
    await _pc(async_session, to, g2, clan_id, creator)
    await _pc(async_session, g2, g3, clan_id, creator)
    await _pc(async_session, g3, g4, clan_id, creator)
    await _pc(async_session, g4, focus, clan_id, creator)
    await async_session.commit()

    handler = await _handler(async_session)
    view = await handler.get_focus_view(
        GetFocusView(person_id=focus, clan_id=clan_id, ancestor_depth=2)
    )

    # ThuyTo(1) -> G2(2) -> G3(3) -> G4(4) -> Focus(5): full founder distance, NOT null.
    assert view["generation_of_focus"] == 5
    assert len(view["ancestors"]) == 2  # breadcrumb itself still honors the requested depth


async def test_get_ancestors_handler_generation_graph_computed(
    async_session: AsyncSession,
) -> None:
    """GET /tree/ancestors computes đời from the graph (thủy tổ=1), the same
    graph-computed contract as every other tree endpoint — ignoring a wrong
    hand-entered clan_memberships.generation."""
    from app.application.tree.queries import GetAncestors

    creator = uuid.uuid4()
    clan_id = await _clan(async_session)
    founder = await _person(async_session, clan_id, creator, "ThuyTo")
    son = await _person(async_session, clan_id, creator, "Con")
    grand = await _person(async_session, clan_id, creator, "Chau")
    await _member(async_session, founder, clan_id, is_founder=True)
    await _member(async_session, son, clan_id)
    await _member(async_session, grand, clan_id)
    # Seed a WRONG hand-entered generation to prove it's ignored.
    await async_session.execute(
        sa.text("UPDATE clan_memberships SET generation = 99 WHERE person_id = :p"), {"p": grand}
    )
    await _pc(async_session, founder, son, clan_id, creator)
    await _pc(async_session, son, grand, clan_id, creator)
    await async_session.commit()

    handler = await _handler(async_session)
    ancestors = await handler.get_ancestors(GetAncestors(person_id=grand, clan_id=clan_id))

    by_id = {a["id"]: a for a in ancestors}
    assert by_id[str(grand)]["generation"] == 3  # not the seeded 99
    assert by_id[str(son)]["generation"] == 2
    assert by_id[str(founder)]["generation"] == 1


async def test_child_nodes_carry_mother_attribution(async_session: AsyncSession) -> None:
    """đa thê: each child node names its mother (which wife) + her spouse_order."""
    from app.application.tree.handlers import TreeQueryHandler
    from app.application.tree.queries import GetSubtree

    creator = uuid.uuid4()
    clan_id = await _clan(async_session)
    father = await _person(async_session, clan_id, creator, "Cha")
    w1 = await _person(async_session, clan_id, creator, "Vo Ca", gender="female")
    w2 = await _person(async_session, clan_id, creator, "Vo Hai", gender="female")
    c1 = await _person(async_session, clan_id, creator, "Con Ba Ca")
    c2 = await _person(async_session, clan_id, creator, "Con Ba Hai")
    for p in (father, w1, w2, c1, c2):
        await _member(async_session, p, clan_id)
    await _marriage(async_session, father, w1, clan_id, creator, spouse_order=1)
    await _marriage(async_session, father, w2, clan_id, creator, spouse_order=2)
    # father→child (paternal descent) AND mother→child (attribution edge)
    await _pc(async_session, father, c1, clan_id, creator)
    await _pc(async_session, w1, c1, clan_id, creator)
    await _pc(async_session, father, c2, clan_id, creator)
    await _pc(async_session, w2, c2, clan_id, creator)
    await async_session.commit()

    handler = TreeQueryHandler(SqlAlchemyTreeRepository(async_session))
    result = await handler.get_subtree(GetSubtree(person_id=father, clan_id=clan_id))
    kids = {c["full_name"]: c for c in result["tree"]["children"]}
    assert kids["Con Ba Ca"]["mother_id"] == str(w1)
    assert kids["Con Ba Ca"]["mother_spouse_order"] == 1
    assert kids["Con Ba Hai"]["mother_id"] == str(w2)
    assert kids["Con Ba Hai"]["mother_spouse_order"] == 2


async def test_child_without_mother_edge_has_null_mother(async_session: AsyncSession) -> None:
    from app.application.tree.handlers import TreeQueryHandler
    from app.application.tree.queries import GetSubtree

    creator = uuid.uuid4()
    clan_id = await _clan(async_session)
    father = await _person(async_session, clan_id, creator, "Cha")
    child = await _person(async_session, clan_id, creator, "Con")
    await _member(async_session, father, clan_id)
    await _member(async_session, child, clan_id)
    await _pc(async_session, father, child, clan_id, creator)  # no mother edge
    await async_session.commit()

    handler = TreeQueryHandler(SqlAlchemyTreeRepository(async_session))
    result = await handler.get_subtree(GetSubtree(person_id=father, clan_id=clan_id))
    kid = result["tree"]["children"][0]
    assert kid["mother_id"] is None and kid["mother_spouse_order"] is None


async def test_tree_handler_output_matches_response_schemas(
    async_session: AsyncSession,
) -> None:
    """Coherence guard: the handler's wire dicts must validate against the
    documentation-only OpenAPI response schemas, so a schema/handler drift fails CI
    instead of shipping a wrong type to codegen. (Focus is omitted — its route
    already coerces to FocusView at runtime, so coherence is guaranteed there.)

    The seeded family includes a pedigree collapse (``child`` descends from GP via
    BOTH ``dad`` and ``mom``) so the ``pedigree_collapse_ref`` stub node (ADR-027,
    H4) is exercised too: model_validate alone would NOT catch a schema regression
    here (pydantic silently drops unknown dict keys by default), so this test reads
    the field back off the VALIDATED model instead of the raw dict — if
    ``pedigree_collapse_ref`` were removed from ``TreeNode``, that attribute access
    would fail instead of silently passing."""
    from app.application.tree.queries import FindPath, GetAncestors, GetFullTree
    from app.schemas.tree import RelationshipPathResponse, TreeNodeDetail, TreeResponse

    creator = uuid.uuid4()
    clan_id = await _clan(async_session)
    gp = await _person(async_session, clan_id, creator, "GP")
    dad = await _person(async_session, clan_id, creator, "Dad")
    mom = await _person(async_session, clan_id, creator, "Mom", gender="female")
    child = await _person(async_session, clan_id, creator, "Child")
    for person, founder in ((gp, True), (dad, False), (mom, False), (child, False)):
        await _member(async_session, person, clan_id, is_founder=founder)
    await _pc(async_session, gp, dad, clan_id, creator)
    await _pc(async_session, gp, mom, clan_id, creator)
    await _pc(async_session, dad, child, clan_id, creator)
    await _pc(async_session, mom, child, clan_id, creator)  # collapse: child descends via both
    await async_session.commit()

    handler = TreeQueryHandler(SqlAlchemyTreeRepository(async_session))

    full = await handler.get_full_tree(
        GetFullTree(clan_id=clan_id, root_person_id=gp, max_generations=10)
    )
    validated_tree = TreeResponse.model_validate(full).tree  # raises on drift

    dad_node = next(c for c in validated_tree.children if c.id == str(dad))
    mom_node = next(c for c in validated_tree.children if c.id == str(mom))
    child_under_dad = next(c for c in dad_node.children if c.id == str(child))
    child_under_mom = next(c for c in mom_node.children if c.id == str(child))
    # dad wins canonical (male beats female at equal type_rank, con theo đời cha):
    # the full node renders under dad, a pedigree_collapse_ref stub under mom.
    assert child_under_dad.pedigree_collapse_ref is False
    assert child_under_mom.pedigree_collapse_ref is True
    assert child_under_mom.children == []

    ancestors = await handler.get_ancestors(GetAncestors(person_id=child, clan_id=clan_id))
    assert ancestors  # non-empty so the loop actually exercises the schema
    for node in ancestors:
        TreeNodeDetail.model_validate(node)  # raises on drift

    path = await handler.find_path(FindPath(from_id=child, to_id=gp, clan_id=clan_id))
    assert path["found"] is True
    RelationshipPathResponse.model_validate(path)  # raises on drift
