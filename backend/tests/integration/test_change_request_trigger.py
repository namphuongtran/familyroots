"""H4 — a change_requests row must be UPDATE-able.

Migration 001 mis-attached the shared ``updated_at`` trigger to change_requests,
which has no ``updated_at`` column, so any UPDATE errored at the DB
(`record "new" has no field "updated_at"`) — breaking the approval workflow the
table exists for. Migration 008 drops that trigger. This drives a real
insert → UPDATE against the migrated schema; it errors (and rolls back) on the
pre-008 schema, and succeeds after.
"""

import uuid

import sqlalchemy as sa


def test_change_request_status_update_succeeds(sync_engine: sa.Engine) -> None:
    cr_id, clan_id, requester = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    with sync_engine.begin() as conn:
        conn.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'CR', :slug)"),
            {"id": clan_id, "slug": f"cr-{clan_id.hex[:8]}"},
        )
        conn.execute(
            sa.text(
                "INSERT INTO change_requests "
                "(id, clan_id, requester_id, action, resource_type, status) "
                "VALUES (:id, :clan, :req, 'create', 'person', 'pending')"
            ),
            {"id": cr_id, "clan": clan_id, "req": requester},
        )
        # The mis-attached trigger fired here before migration 008 and raised.
        conn.execute(
            sa.text(
                "UPDATE change_requests SET status = 'approved', reviewed_by = :req WHERE id = :id"
            ),
            {"req": requester, "id": cr_id},
        )
        status = conn.execute(
            sa.text("SELECT status FROM change_requests WHERE id = :id"), {"id": cr_id}
        ).scalar_one()
        # Clean up within the same transaction so the shared DB stays pristine.
        conn.execute(sa.text("DELETE FROM change_requests WHERE id = :id"), {"id": cr_id})
        conn.execute(sa.text("DELETE FROM clans WHERE id = :id"), {"id": clan_id})

    assert status == "approved"
