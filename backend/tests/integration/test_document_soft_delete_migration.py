"""Migration 016: documents gain soft-delete columns (they never had them)."""

import pytest
import sqlalchemy as sa

pytestmark = pytest.mark.integration


def test_document_soft_delete_columns_exist(sync_engine):
    insp = sa.inspect(sync_engine)
    cols = {c["name"]: c for c in insp.get_columns("documents")}
    assert "is_deleted" in cols and cols["is_deleted"]["nullable"] is False
    assert "deleted_at" in cols and cols["deleted_at"]["nullable"] is True
    assert "deleted_by" in cols and cols["deleted_by"]["nullable"] is True


def test_partial_index_exists(sync_engine):
    with sync_engine.connect() as conn:
        row = conn.execute(
            sa.text("SELECT indexdef FROM pg_indexes WHERE indexname = 'idx_documents_is_deleted'")
        ).first()
    assert row is not None and "WHERE (is_deleted = false)" in row[0]
