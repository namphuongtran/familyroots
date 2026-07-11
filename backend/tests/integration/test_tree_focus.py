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
    s: AsyncSession, clan_id: uuid.UUID, creator: uuid.UUID, name: str = "P"
) -> uuid.UUID:
    pid = uuid.uuid4()
    await s.execute(
        sa.text(
            "INSERT INTO persons (id, full_name, gender, created_by_clan_id, created_by) "
            "VALUES (:id, :n, 'male', :c, :cb)"
        ),
        {"id": pid, "n": name, "c": clan_id, "cb": creator},
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
    from app.services.tree_builder import build_focus_view

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

    tree = await build_focus_view(
        async_session, root, clan_id, descendant_depth=2, base_generation=3
    )

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
    """A person of clan A must be invisible through clan B (404), both directions."""
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
