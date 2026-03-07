"""Initial schema — all tables, enums, indexes, and triggers.

Revision ID: 001_initial
Revises: None
Create Date: 2026-03-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, INET

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- Extensions --
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "unaccent"')

    # -- Enums (created automatically by sa.Enum with create_type=True in create_table below) --

    # -- Table: clans --
    op.create_table(
        "clans",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False, unique=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("origin_place", sa.String(255), nullable=True),
        sa.Column("founded_year", sa.SmallInteger, nullable=True),
        sa.Column("avatar_url", sa.String(500), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.CheckConstraint(r"slug ~ '^[a-z0-9][a-z0-9\-]*[a-z0-9]$'", name="clans_slug_format"),
        sa.CheckConstraint("founded_year BETWEEN 1000 AND 2100", name="clans_founded_year_range"),
    )
    op.create_index("idx_clans_slug", "clans", ["slug"])
    op.execute("CREATE INDEX idx_clans_is_active ON clans (is_active) WHERE is_active = true")

    # -- Table: members --
    op.create_table(
        "members",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("clan_id", UUID(as_uuid=True), sa.ForeignKey("clans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("birth_name", sa.String(255), nullable=True),
        sa.Column("courtesy_name", sa.String(255), nullable=True),
        sa.Column("gender", sa.Enum("male", "female", "unknown", name="gender_type", create_type=True), nullable=False, server_default=sa.text("'unknown'")),
        sa.Column("birth_date", sa.Date, nullable=True),
        sa.Column("birth_date_approx", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("death_date", sa.Date, nullable=True),
        sa.Column("death_date_approx", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("birth_place", sa.String(255), nullable=True),
        sa.Column("death_place", sa.String(255), nullable=True),
        sa.Column("residence_place", sa.String(255), nullable=True),
        sa.Column("generation", sa.SmallInteger, nullable=True),
        sa.Column("is_clan_founder", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("is_clan_member", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("biography", sa.Text, nullable=True),
        sa.Column("avatar_url", sa.String(500), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("is_deleted", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), nullable=False),
        sa.Column("updated_by", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.CheckConstraint(
            "death_date IS NULL OR birth_date IS NULL OR death_date >= birth_date",
            name="members_death_after_birth",
        ),
        sa.CheckConstraint("generation IS NULL OR generation > 0", name="members_generation_positive"),
    )
    op.create_index("idx_members_clan_id", "members", ["clan_id"])
    op.create_index("idx_members_clan_generation", "members", ["clan_id", "generation"])
    op.execute("CREATE INDEX idx_members_is_deleted ON members (clan_id, is_deleted) WHERE is_deleted = false")
    op.create_index("idx_members_birth_date", "members", ["clan_id", "birth_date"])
    op.execute("CREATE INDEX idx_members_is_founder ON members (clan_id) WHERE is_clan_founder = true")
    # PG 18 requires functions in index expressions to be IMMUTABLE.
    # unaccent() is STABLE, so we create an IMMUTABLE wrapper.
    op.execute(
        "CREATE OR REPLACE FUNCTION public.f_unaccent(text) "
        "RETURNS text AS $$ SELECT public.unaccent('public.unaccent', $1) $$ "
        "LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT"
    )
    op.execute(
        "CREATE INDEX idx_members_fullname_search ON members "
        "USING gin (to_tsvector('simple', public.f_unaccent(full_name)))"
    )
    op.execute(
        "CREATE INDEX idx_members_fullname_trgm ON members "
        "USING gin (public.f_unaccent(full_name) gin_trgm_ops)"
    )

    # -- Table: relationships --
    op.create_table(
        "relationships",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("clan_id", UUID(as_uuid=True), sa.ForeignKey("clans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("member_id", UUID(as_uuid=True), sa.ForeignKey("members.id", ondelete="CASCADE"), nullable=False),
        sa.Column("related_id", UUID(as_uuid=True), sa.ForeignKey("members.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relation_type", sa.Enum("parent", "child", "spouse", name="relation_type", create_type=True), nullable=False),
        sa.Column("relation_subtype", sa.Enum("biological", "adoptive", "step", "foster", "married", "divorced", "widowed", "partner", name="relation_subtype", create_type=True), nullable=False),
        sa.Column("start_date", sa.Date, nullable=True),
        sa.Column("end_date", sa.Date, nullable=True),
        sa.Column("is_primary", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.CheckConstraint("member_id != related_id", name="relationships_no_self_loop"),
        sa.CheckConstraint(
            "(relation_type IN ('parent', 'child') AND relation_subtype IN ('biological','adoptive','step','foster')) "
            "OR (relation_type = 'spouse' AND relation_subtype IN ('married','divorced','widowed','partner'))",
            name="relationships_subtype_matches_type",
        ),
    )
    op.execute(
        "CREATE UNIQUE INDEX idx_relationships_unique_edge "
        "ON relationships (member_id, related_id, relation_type, relation_subtype) "
        "WHERE relation_type != 'spouse'"
    )
    op.execute(
        "CREATE UNIQUE INDEX idx_relationships_one_active_spouse "
        "ON relationships (member_id, relation_type) "
        "WHERE relation_type = 'spouse' AND end_date IS NULL"
    )
    op.create_index("idx_relationships_member", "relationships", ["clan_id", "member_id", "relation_type"])
    op.create_index("idx_relationships_related", "relationships", ["clan_id", "related_id", "relation_type"])

    # -- Table: documents --
    op.create_table(
        "documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("clan_id", UUID(as_uuid=True), sa.ForeignKey("clans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("member_id", UUID(as_uuid=True), sa.ForeignKey("members.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("document_type", sa.Enum("photo", "id_document", "certificate", "audio", "video", "other", name="document_type", create_type=True), nullable=False),
        sa.Column("storage_path", sa.String(500), nullable=False, unique=True),
        sa.Column("file_size_bytes", sa.BigInteger, nullable=True),
        sa.Column("mime_type", sa.String(100), nullable=True),
        sa.Column("original_filename", sa.String(255), nullable=True),
        sa.Column("taken_date", sa.Date, nullable=True),
        sa.Column("taken_place", sa.String(255), nullable=True),
        sa.Column("is_avatar", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_by", UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.CheckConstraint(
            "file_size_bytes IS NULL OR file_size_bytes <= 52428800",
            name="documents_file_size_limit",
        ),
    )
    op.create_index("idx_documents_clan", "documents", ["clan_id"])
    op.execute("CREATE INDEX idx_documents_member ON documents (member_id) WHERE member_id IS NOT NULL")
    op.create_index("idx_documents_type", "documents", ["clan_id", "document_type"])
    op.execute("CREATE INDEX idx_documents_avatar ON documents (member_id) WHERE is_avatar = true")

    # -- Table: events --
    op.create_table(
        "events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("clan_id", UUID(as_uuid=True), sa.ForeignKey("clans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("member_id", UUID(as_uuid=True), sa.ForeignKey("members.id", ondelete="CASCADE"), nullable=True),
        sa.Column("event_type", sa.Enum("death_anniversary", "birthday", "wedding_anniversary", "clan_ceremony", "custom", name="event_type", create_type=True), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("event_date", sa.Date, nullable=False),
        sa.Column("is_lunar_calendar", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("is_recurring", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("notify_days_before", sa.SmallInteger, nullable=False, server_default=sa.text("7")),
        sa.Column("created_by", UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.CheckConstraint("notify_days_before BETWEEN 0 AND 30", name="events_notify_range"),
    )
    op.create_index("idx_events_clan", "events", ["clan_id"])
    op.execute("CREATE INDEX idx_events_member ON events (member_id) WHERE member_id IS NOT NULL")
    op.create_index("idx_events_date", "events", ["clan_id", "event_date"])
    op.execute("CREATE INDEX idx_events_recurring_date ON events (clan_id, event_date) WHERE is_recurring = true")

    # -- Table: user_clan_roles --
    op.create_table(
        "user_clan_roles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("clan_id", UUID(as_uuid=True), sa.ForeignKey("clans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("member_id", UUID(as_uuid=True), sa.ForeignKey("members.id", ondelete="SET NULL"), nullable=True),
        sa.Column("role", sa.Enum("admin", "editor", "viewer", name="clan_role", create_type=True), nullable=False, server_default=sa.text("'viewer'")),
        sa.Column("is_approved", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("approved_by", UUID(as_uuid=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invited_by", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.CheckConstraint(
            "(is_approved = false AND approved_by IS NULL AND approved_at IS NULL) "
            "OR (is_approved = true AND approved_by IS NOT NULL AND approved_at IS NOT NULL)",
            name="user_clan_roles_approval_consistency",
        ),
    )
    op.execute("CREATE UNIQUE INDEX idx_user_clan_roles_user_clan ON user_clan_roles (user_id, clan_id)")
    op.create_index("idx_user_clan_roles_clan", "user_clan_roles", ["clan_id"])
    op.execute(
        "CREATE INDEX idx_user_clan_roles_pending ON user_clan_roles (clan_id, is_approved) "
        "WHERE is_approved = false"
    )

    # -- Table: platform_users --
    op.create_table(
        "platform_users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("role", sa.String(50), nullable=False, server_default=sa.text("'super_admin'")),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.CheckConstraint("role = 'super_admin'", name="platform_users_only_super_admin"),
    )
    op.execute("CREATE UNIQUE INDEX idx_platform_users_single_super_admin ON platform_users (role)")

    # -- Table: audit_logs --
    op.create_table(
        "audit_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("clan_id", UUID(as_uuid=True), sa.ForeignKey("clans.id", ondelete="SET NULL"), nullable=True),
        sa.Column("actor_id", UUID(as_uuid=True), nullable=False),
        sa.Column("actor_role", sa.String(50), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("resource_id", UUID(as_uuid=True), nullable=True),
        sa.Column("old_value", JSONB, nullable=True),
        sa.Column("new_value", JSONB, nullable=True),
        sa.Column("ip_address", INET, nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("idx_audit_logs_clan", "audit_logs", ["clan_id", sa.text("created_at DESC")])
    op.create_index("idx_audit_logs_actor", "audit_logs", ["actor_id", sa.text("created_at DESC")])
    op.create_index("idx_audit_logs_resource", "audit_logs", ["resource_type", "resource_id"])

    # -- Table: notification_log --
    op.create_table(
        "notification_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("clan_id", UUID(as_uuid=True), sa.ForeignKey("clans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_id", UUID(as_uuid=True), sa.ForeignKey("events.id", ondelete="SET NULL"), nullable=True),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("notification_type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("fcm_token", sa.String(500), nullable=True),
        sa.Column("status", sa.Enum("pending", "sent", "failed", name="notification_status", create_type=True), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("idx_notification_log_clan_date", "notification_log", ["clan_id", sa.text("created_at DESC")])
    op.execute(
        "CREATE UNIQUE INDEX idx_notification_log_dedup "
        "ON notification_log (user_id, event_id, notification_type, "
        "CAST(created_at AT TIME ZONE 'UTC' AS date))"
    )

    # -- Triggers: auto-update updated_at --
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)

    for table in ("clans", "members", "relationships", "documents", "events", "user_clan_roles"):
        op.execute(
            f"CREATE TRIGGER trg_{table}_updated_at "
            f"BEFORE UPDATE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()"
        )


def downgrade() -> None:
    # Drop triggers
    for table in ("user_clan_roles", "events", "documents", "relationships", "members", "clans"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_updated_at ON {table}")
    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column()")

    # Drop tables in reverse dependency order
    op.drop_table("notification_log")
    op.drop_table("audit_logs")
    op.drop_table("platform_users")
    op.drop_table("user_clan_roles")
    op.drop_table("events")
    op.drop_table("documents")
    op.drop_table("relationships")
    op.drop_table("members")
    op.drop_table("clans")

    # Drop enums
    op.execute("DROP TYPE IF EXISTS notification_status")
    op.execute("DROP TYPE IF EXISTS document_type")
    op.execute("DROP TYPE IF EXISTS event_type")
    op.execute("DROP TYPE IF EXISTS clan_role")
    op.execute("DROP TYPE IF EXISTS relation_subtype")
    op.execute("DROP TYPE IF EXISTS relation_type")
    op.execute("DROP TYPE IF EXISTS gender_type")

    # Drop immutable unaccent wrapper
    op.execute("DROP FUNCTION IF EXISTS public.f_unaccent(text)")
