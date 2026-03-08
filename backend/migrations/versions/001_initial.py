"""Initial schema — all tables, enums, indexes, and triggers.

Revision ID: 001_initial
Revises: None
Create Date: 2026-03-07

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # -- Extensions --
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "unaccent"')

    # -- Table: clans --
    op.create_table(
        "clans",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False, unique=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("origin_place", sa.String(255), nullable=True),
        sa.Column("founded_year", sa.SmallInteger, nullable=True),
        sa.Column("avatar_url", sa.String(500), nullable=True),
        sa.Column("motto", sa.Text, nullable=True),
        sa.Column("ancestral_hall_location", sa.String(500), nullable=True),
        sa.Column("clan_rules", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
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
        sa.CheckConstraint(r"slug ~ '^[a-z0-9][a-z0-9\-]*[a-z0-9]$'", name="clans_slug_format"),
        sa.CheckConstraint("founded_year BETWEEN 1000 AND 2100", name="clans_founded_year_range"),
    )
    op.create_index("idx_clans_slug", "clans", ["slug"])
    op.execute("CREATE INDEX idx_clans_is_active ON clans (is_active) WHERE is_active = true")

    # -- Table: persons (global entity — no clan_id) --
    op.create_table(
        "persons",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "origin_clan_id",
            UUID(as_uuid=True),
            sa.ForeignKey("clans.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # Identity
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("birth_name", sa.String(255), nullable=True),
        sa.Column("courtesy_name", sa.String(255), nullable=True),
        sa.Column("posthumous_name", sa.String(255), nullable=True),
        sa.Column("alias_name", sa.String(255), nullable=True),
        sa.Column(
            "gender",
            sa.Enum("male", "female", "unknown", name="gender_type", create_type=True),
            nullable=False,
            server_default=sa.text("'unknown'"),
        ),
        # Dates
        sa.Column("birth_date", sa.Date, nullable=True),
        sa.Column("birth_date_approx", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("death_date", sa.Date, nullable=True),
        sa.Column("death_date_approx", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("lunar_birth_date", sa.String(30), nullable=True),
        sa.Column("lunar_death_date", sa.String(30), nullable=True),
        # Places
        sa.Column("birth_place", sa.String(255), nullable=True),
        sa.Column("death_place", sa.String(255), nullable=True),
        sa.Column("burial_place", sa.String(255), nullable=True),
        sa.Column("tomb_location", sa.String(500), nullable=True),
        sa.Column("residence_place", sa.String(255), nullable=True),
        # Personal info
        sa.Column("religion", sa.String(100), nullable=True),
        sa.Column("nationality", sa.String(100), nullable=True, server_default=sa.text("'VN'")),
        sa.Column("occupation", sa.String(255), nullable=True),
        sa.Column("education_level", sa.String(255), nullable=True),
        sa.Column("title_rank", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        # Content
        sa.Column("biography", sa.Text, nullable=True),
        sa.Column("avatar_url", sa.String(500), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        # Soft delete
        sa.Column("is_deleted", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", UUID(as_uuid=True), nullable=True),
        # Audit
        sa.Column("created_by", UUID(as_uuid=True), nullable=False),
        sa.Column("updated_by", UUID(as_uuid=True), nullable=True),
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
        sa.CheckConstraint(
            "death_date IS NULL OR birth_date IS NULL OR death_date >= birth_date",
            name="persons_death_after_birth",
        ),
    )
    op.execute(
        "CREATE INDEX idx_persons_is_deleted ON persons "
        "(is_deleted) WHERE is_deleted = false"
    )
    op.execute(
        "CREATE INDEX idx_persons_origin_clan ON persons "
        "(origin_clan_id) WHERE origin_clan_id IS NOT NULL"
    )
    # Immutable unaccent wrapper for index expressions
    op.execute(
        "CREATE OR REPLACE FUNCTION public.f_unaccent(text) "
        "RETURNS text AS $$ SELECT public.unaccent('public.unaccent', $1) $$ "
        "LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT"
    )
    op.execute(
        "CREATE INDEX idx_persons_fullname_search ON persons "
        "USING gin (to_tsvector('simple', public.f_unaccent(full_name)))"
    )
    op.execute(
        "CREATE INDEX idx_persons_fullname_trgm ON persons "
        "USING gin (public.f_unaccent(full_name) gin_trgm_ops)"
    )

    # -- Table: clan_memberships (M:N person ↔ clan) --
    op.create_table(
        "clan_memberships",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "person_id",
            UUID(as_uuid=True),
            sa.ForeignKey("persons.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "clan_id",
            UUID(as_uuid=True),
            sa.ForeignKey("clans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "role",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'blood'"),
        ),
        sa.Column("generation", sa.SmallInteger, nullable=True),
        sa.Column("is_founder", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.UniqueConstraint("person_id", "clan_id", name="uq_clan_memberships_person_clan"),
        sa.CheckConstraint(
            "role IN ('blood', 'spouse', 'adopted')",
            name="clan_memberships_role_check",
        ),
        sa.CheckConstraint(
            "generation IS NULL OR generation > 0",
            name="clan_memberships_generation_positive",
        ),
    )
    op.create_index("idx_clan_memberships_clan", "clan_memberships", ["clan_id"])
    op.create_index("idx_clan_memberships_person", "clan_memberships", ["person_id"])
    op.create_index(
        "idx_clan_memberships_clan_generation", "clan_memberships", ["clan_id", "generation"]
    )
    op.execute(
        "CREATE INDEX idx_clan_memberships_founder ON clan_memberships "
        "(clan_id) WHERE is_founder = true"
    )

    # -- Table: marriages (global edge: person1 ↔ person2) --
    op.create_table(
        "marriages",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "person1_id",
            UUID(as_uuid=True),
            sa.ForeignKey("persons.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "person2_id",
            UUID(as_uuid=True),
            sa.ForeignKey("persons.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_by_clan_id",
            UUID(as_uuid=True),
            sa.ForeignKey("clans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("marriage_date", sa.Date, nullable=True),
        sa.Column("divorce_date", sa.Date, nullable=True),
        sa.Column("marriage_place", sa.String(255), nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'married'"),
        ),
        sa.Column("spouse_order", sa.SmallInteger, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), nullable=False),
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
        sa.CheckConstraint("person1_id != person2_id", name="marriages_no_self"),
        sa.CheckConstraint(
            "status IN ('married', 'divorced', 'widowed', 'separated')",
            name="marriages_status_check",
        ),
        sa.CheckConstraint(
            "divorce_date IS NULL OR marriage_date IS NULL OR divorce_date >= marriage_date",
            name="marriages_divorce_after_marriage",
        ),
        sa.CheckConstraint(
            "spouse_order IS NULL OR spouse_order > 0",
            name="marriages_spouse_order_positive",
        ),
    )
    op.create_index("idx_marriages_person1", "marriages", ["person1_id"])
    op.create_index("idx_marriages_person2", "marriages", ["person2_id"])
    op.create_index("idx_marriages_clan", "marriages", ["created_by_clan_id"])
    op.execute(
        "CREATE UNIQUE INDEX idx_marriages_unique_pair "
        "ON marriages (LEAST(person1_id, person2_id), GREATEST(person1_id, person2_id), status) "
        "WHERE status = 'married'"
    )

    # -- Table: parent_child (global edge: parent → child) --
    op.create_table(
        "parent_child",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "parent_id",
            UUID(as_uuid=True),
            sa.ForeignKey("persons.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "child_id",
            UUID(as_uuid=True),
            sa.ForeignKey("persons.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_by_clan_id",
            UUID(as_uuid=True),
            sa.ForeignKey("clans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "relationship_type",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'biological'"),
        ),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), nullable=False),
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
        sa.CheckConstraint("parent_id != child_id", name="parent_child_no_self"),
        sa.CheckConstraint(
            "relationship_type IN ('biological', 'adopted', 'step', 'foster')",
            name="parent_child_type_check",
        ),
    )
    op.execute(
        "CREATE UNIQUE INDEX idx_parent_child_unique_edge "
        "ON parent_child (parent_id, child_id, relationship_type)"
    )
    op.create_index("idx_parent_child_parent", "parent_child", ["parent_id"])
    op.create_index("idx_parent_child_child", "parent_child", ["child_id"])
    op.create_index("idx_parent_child_clan", "parent_child", ["created_by_clan_id"])

    # -- Table: documents --
    op.create_table(
        "documents",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "clan_id",
            UUID(as_uuid=True),
            sa.ForeignKey("clans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "person_id",
            UUID(as_uuid=True),
            sa.ForeignKey("persons.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "document_type",
            sa.Enum(
                "photo",
                "id_document",
                "certificate",
                "audio",
                "video",
                "other",
                name="document_type",
                create_type=True,
            ),
            nullable=False,
        ),
        sa.Column("storage_path", sa.String(500), nullable=False, unique=True),
        sa.Column("file_size_bytes", sa.BigInteger, nullable=True),
        sa.Column("mime_type", sa.String(100), nullable=True),
        sa.Column("original_filename", sa.String(255), nullable=True),
        sa.Column("taken_date", sa.Date, nullable=True),
        sa.Column("taken_place", sa.String(255), nullable=True),
        sa.Column("is_avatar", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_by", UUID(as_uuid=True), nullable=False),
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
        sa.CheckConstraint(
            "file_size_bytes IS NULL OR file_size_bytes <= 52428800",
            name="documents_file_size_limit",
        ),
    )
    op.create_index("idx_documents_clan", "documents", ["clan_id"])
    op.execute(
        "CREATE INDEX idx_documents_person ON documents (person_id) WHERE person_id IS NOT NULL"
    )
    op.create_index("idx_documents_type", "documents", ["clan_id", "document_type"])
    op.execute("CREATE INDEX idx_documents_avatar ON documents (person_id) WHERE is_avatar = true")

    # -- Table: events --
    op.create_table(
        "events",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "clan_id",
            UUID(as_uuid=True),
            sa.ForeignKey("clans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "person_id",
            UUID(as_uuid=True),
            sa.ForeignKey("persons.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "event_type",
            sa.Enum(
                "death_anniversary",
                "birthday",
                "wedding_anniversary",
                "clan_ceremony",
                "custom",
                name="event_type",
                create_type=True,
            ),
            nullable=False,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("event_date", sa.Date, nullable=False),
        sa.Column("is_lunar_calendar", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("is_recurring", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column(
            "notify_days_before", sa.SmallInteger, nullable=False, server_default=sa.text("7")
        ),
        sa.Column("created_by", UUID(as_uuid=True), nullable=False),
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
        sa.CheckConstraint("notify_days_before BETWEEN 0 AND 30", name="events_notify_range"),
    )
    op.create_index("idx_events_clan", "events", ["clan_id"])
    op.execute("CREATE INDEX idx_events_person ON events (person_id) WHERE person_id IS NOT NULL")
    op.create_index("idx_events_date", "events", ["clan_id", "event_date"])
    op.execute(
        "CREATE INDEX idx_events_recurring_date ON events "
        "(clan_id, event_date) WHERE is_recurring = true"
    )

    # -- Table: user_profiles --
    op.create_table(
        "user_profiles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("avatar_url", sa.String(500), nullable=True),
        sa.Column("language", sa.String(10), nullable=False, server_default=sa.text("'vi'")),
        sa.Column("timezone", sa.String(50), nullable=False, server_default=sa.text("'Asia/Ho_Chi_Minh'")),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("platform_role", sa.String(50), nullable=False, server_default=sa.text("'user'")),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
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

    # -- Table: user_devices --
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

    # -- Table: clan_settings --
    op.create_table(
        "clan_settings",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "clan_id",
            UUID(as_uuid=True),
            sa.ForeignKey("clans.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("approval_config", JSONB, nullable=True),
        sa.Column("default_language", sa.String(10), nullable=False, server_default=sa.text("'vi'")),
        sa.Column("tree_display_mode", sa.String(20), nullable=False, server_default=sa.text("'vertical'")),
        sa.Column("allow_public_tree", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("notification_defaults", JSONB, nullable=True),
        sa.Column("privacy_level", sa.String(20), nullable=False, server_default=sa.text("'clan_members'")),
        sa.Column("max_upload_size_mb", sa.SmallInteger, nullable=False, server_default=sa.text("10")),
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

    # -- Table: clan_invitations --
    op.create_table(
        "clan_invitations",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "clan_id",
            UUID(as_uuid=True),
            sa.ForeignKey("clans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default=sa.text("'viewer'")),
        sa.Column("invited_by", UUID(as_uuid=True), nullable=False),
        sa.Column("token", sa.String(255), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index("ix_clan_invitations_clan_id", "clan_invitations", ["clan_id"])
    op.create_index("ix_clan_invitations_clan_email", "clan_invitations", ["clan_id", "email"])

    # -- Table: user_clan_roles --
    op.create_table(
        "user_clan_roles",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "clan_id",
            UUID(as_uuid=True),
            sa.ForeignKey("clans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("user_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "person_id",
            UUID(as_uuid=True),
            sa.ForeignKey("persons.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "role",
            sa.Enum("admin", "editor", "viewer", name="clan_role", create_type=True),
            nullable=False,
            server_default=sa.text("'viewer'"),
        ),
        sa.Column("is_approved", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("approved_by", UUID(as_uuid=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invited_by", UUID(as_uuid=True), nullable=True),
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
        sa.CheckConstraint(
            "(is_approved = false AND approved_by IS NULL AND approved_at IS NULL) "
            "OR (is_approved = true AND approved_by IS NOT NULL AND approved_at IS NOT NULL)",
            name="user_clan_roles_approval_consistency",
        ),
    )
    op.execute(
        "CREATE UNIQUE INDEX idx_user_clan_roles_user_clan ON user_clan_roles (user_id, clan_id)"
    )
    op.create_index("idx_user_clan_roles_clan", "user_clan_roles", ["clan_id"])
    op.execute(
        "CREATE INDEX idx_user_clan_roles_pending ON user_clan_roles (clan_id, is_approved) "
        "WHERE is_approved = false"
    )

    # -- Table: change_requests --
    op.create_table(
        "change_requests",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "clan_id",
            UUID(as_uuid=True),
            sa.ForeignKey("clans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("requester_id", UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("resource_id", UUID(as_uuid=True), nullable=True),
        sa.Column("payload", JSONB, nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("reviewed_by", UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_notes", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "action IN ('create', 'update', 'delete')",
            name="change_requests_action_check",
        ),
        sa.CheckConstraint(
            "resource_type IN ('person', 'marriage', 'parent_child', 'event', 'document')",
            name="change_requests_resource_type_check",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="change_requests_status_check",
        ),
    )
    op.create_index("idx_change_requests_clan", "change_requests", ["clan_id"])
    op.execute(
        "CREATE INDEX idx_change_requests_pending ON change_requests "
        "(clan_id, status) WHERE status = 'pending'"
    )

    # -- Table: audit_logs --
    op.create_table(
        "audit_logs",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "clan_id",
            UUID(as_uuid=True),
            sa.ForeignKey("clans.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("actor_id", UUID(as_uuid=True), nullable=False),
        sa.Column("actor_role", sa.String(50), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("resource_id", UUID(as_uuid=True), nullable=True),
        sa.Column("old_value", JSONB, nullable=True),
        sa.Column("new_value", JSONB, nullable=True),
        sa.Column("ip_address", INET, nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index("idx_audit_logs_clan", "audit_logs", ["clan_id", sa.text("created_at DESC")])
    op.create_index("idx_audit_logs_actor", "audit_logs", ["actor_id", sa.text("created_at DESC")])
    op.create_index("idx_audit_logs_resource", "audit_logs", ["resource_type", "resource_id"])

    # -- Table: notification_log --
    op.create_table(
        "notification_log",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "clan_id",
            UUID(as_uuid=True),
            sa.ForeignKey("clans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "event_id",
            UUID(as_uuid=True),
            sa.ForeignKey("events.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("notification_type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "sent", "failed", name="notification_status", create_type=True),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index(
        "idx_notification_log_clan_date",
        "notification_log",
        ["clan_id", sa.text("created_at DESC")],
    )
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

    for table in (
        "clans", "persons", "clan_memberships", "marriages", "parent_child",
        "documents", "events", "user_profiles", "clan_settings",
        "user_clan_roles", "change_requests",
    ):
        op.execute(
            f"CREATE TRIGGER trg_{table}_updated_at "
            f"BEFORE UPDATE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()"
        )


def downgrade() -> None:
    # Drop triggers
    for table in (
        "change_requests", "clan_settings", "user_clan_roles", "events", "documents",
        "parent_child", "marriages", "clan_memberships", "user_profiles", "persons", "clans",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_updated_at ON {table}")
    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column()")

    # Drop tables in reverse dependency order
    op.drop_table("notification_log")
    op.drop_table("audit_logs")
    op.drop_table("change_requests")
    op.drop_table("clan_invitations")
    op.drop_table("clan_settings")
    op.drop_table("user_clan_roles")
    op.drop_table("events")
    op.drop_table("documents")
    op.drop_table("parent_child")
    op.drop_table("marriages")
    op.drop_table("clan_memberships")
    op.drop_table("user_devices")
    op.drop_table("user_profiles")
    op.drop_table("persons")
    op.drop_table("clans")

    # Drop enums
    op.execute("DROP TYPE IF EXISTS notification_status")
    op.execute("DROP TYPE IF EXISTS document_type")
    op.execute("DROP TYPE IF EXISTS event_type")
    op.execute("DROP TYPE IF EXISTS clan_role")
    op.execute("DROP TYPE IF EXISTS gender_type")

    # Drop immutable unaccent wrapper
    op.execute("DROP FUNCTION IF EXISTS public.f_unaccent(text)")
