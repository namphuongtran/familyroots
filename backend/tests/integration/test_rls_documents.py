"""RLS pilot: the documents clan-isolation policy enforces isolation under the
non-bypass ``familyroots_app`` role (ADR-008).

Seeds rows as the (bypassing) superuser the conftest connects as, then drops to
``familyroots_app`` via ``SET LOCAL ROLE`` and proves: clan A sees only A's
documents; clan B only B's; an unset ``app.clan_id`` GUC yields zero rows
(default-deny); and the effective role does not bypass RLS.
"""

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine


@pytest.fixture()
async def async_engine(migrated_db_url):
    engine = create_async_engine(migrated_db_url)
    yield engine
    await engine.dispose()


async def _seed_clan_with_doc(conn, clan_id):
    await conn.execute(
        sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :s)"),
        {"id": clan_id, "s": f"c{clan_id.hex[:10]}"},
    )
    doc_id = uuid.uuid4()
    await conn.execute(
        sa.text(
            "INSERT INTO documents (id, clan_id, title, document_type, storage_path, created_by) "
            "VALUES (:id, :c, 't', 'photo', :sp, :cb)"
        ),
        {"id": doc_id, "c": clan_id, "sp": f"p/{doc_id.hex}", "cb": uuid.uuid4()},
    )
    return doc_id


async def _set_app_role(conn: AsyncConnection, clan_id: str | None) -> None:
    await conn.execute(sa.text("SET LOCAL ROLE familyroots_app"))
    if clan_id is not None:
        await conn.execute(sa.text("SELECT set_config('app.clan_id', :c, true)"), {"c": clan_id})


@pytest.mark.asyncio
async def test_documents_rls_enforces_clan_isolation(async_engine: AsyncEngine) -> None:
    clan_a, clan_b = uuid.uuid4(), uuid.uuid4()

    async with async_engine.connect() as conn:
        # Seed as the privileged (RLS-bypassing) connection.
        async with conn.begin():
            doc_a = await _seed_clan_with_doc(conn, clan_a)
            doc_b = await _seed_clan_with_doc(conn, clan_b)

        # As familyroots_app + app.clan_id = A → only A's document, and the role
        # genuinely does not bypass RLS.
        async with conn.begin():
            await _set_app_role(conn, str(clan_a))
            assert (
                await conn.execute(sa.text("SELECT current_user"))
            ).scalar() == "familyroots_app"
            bypass = (
                await conn.execute(
                    sa.text("SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user")
                )
            ).scalar()
            assert bypass is False
            ids = set((await conn.execute(sa.text("SELECT id FROM documents"))).scalars().all())
            assert ids == {doc_a}

        # app.clan_id = B → only B's document (cross-clan is invisible).
        async with conn.begin():
            await _set_app_role(conn, str(clan_b))
            ids = set((await conn.execute(sa.text("SELECT id FROM documents"))).scalars().all())
            assert ids == {doc_b}

        # Default-deny: role set but no app.clan_id → zero rows (fails closed).
        async with conn.begin():
            await _set_app_role(conn, None)
            count = (await conn.execute(sa.text("SELECT count(*) FROM documents"))).scalar()
            assert count == 0
