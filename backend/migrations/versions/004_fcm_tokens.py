"""Create user_fcm_tokens (the table the runtime code actually uses); drop the
orphan user_devices table.

The FCM repository (app/infrastructure/persistence/auth_repository.py) and the
notification service (app/services/notification.py) both read/write
``public.user_fcm_tokens(user_id, token, device_platform)`` via raw SQL, but no
Alembic migration ever created that table — so POST/DELETE /auth/me/fcm-token and
the anniversary push JOIN both raised ``UndefinedTable`` (see the 2026-06-28
backend design review, finding C1). A parallel ``user_devices`` table (with an ORM
model + a ``UserProfile.devices`` relationship) was the only push-token table in
the Alembic schema, but nothing at runtime ever referenced it.

This consolidates onto a single source of truth: it creates ``user_fcm_tokens``
with the exact column contract the runtime code expects, and drops the unused
``user_devices`` table. The ORM model + relationship for ``user_devices`` are
removed in the same change so autogenerate drift detection stays clean.

Revision ID: 004_fcm_tokens
Revises: 003_tree_functions
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "004_fcm_tokens"
down_revision: str | None = "003_tree_functions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_fcm_tokens",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("user_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # The code does INSERT ... ON CONFLICT (token): a push token is globally
        # unique to one device, so a re-register moves it to the current user.
        sa.Column("token", sa.Text(), nullable=False, unique=True),
        sa.Column("device_platform", sa.String(20), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index("ix_user_fcm_tokens_user_id", "user_fcm_tokens", ["user_id"])

    # Drop the orphan table: no runtime code references user_devices.
    op.drop_index("ix_user_devices_user_id", table_name="user_devices")
    op.drop_table("user_devices")


def downgrade() -> None:
    # Recreate user_devices exactly as 001_initial defined it.
    op.create_table(
        "user_devices",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("user_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("fcm_token", sa.String(500), nullable=False, unique=True),
        sa.Column("device_name", sa.String(255), nullable=True),
        sa.Column("platform", sa.String(20), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index("ix_user_devices_user_id", "user_devices", ["user_id"])

    op.drop_index("ix_user_fcm_tokens_user_id", table_name="user_fcm_tokens")
    op.drop_table("user_fcm_tokens")
