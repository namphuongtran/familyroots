-- ============================================================
-- 001_initial_schema.sql
-- Full DDL for FamilyRoots — PostgreSQL 15+
-- Single public schema, clan_id isolation via RLS
-- ============================================================

-- ============================================================
-- EXTENSIONS
-- ============================================================
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";      -- trigram index for fuzzy name search
CREATE EXTENSION IF NOT EXISTS "unaccent";     -- accent-insensitive search (Vietnamese names)

-- ============================================================
-- ENUMS
-- ============================================================
CREATE TYPE gender_type AS ENUM ('male', 'female', 'unknown');

CREATE TYPE relation_type AS ENUM ('parent', 'child', 'spouse');

CREATE TYPE relation_subtype AS ENUM (
    -- for parent/child
    'biological', 'adoptive', 'step', 'foster',
    -- for spouse
    'married', 'divorced', 'widowed', 'partner'
);

CREATE TYPE clan_role AS ENUM ('admin', 'editor', 'viewer');
-- Note: 'super_admin' lives only in platform_users, not here

CREATE TYPE event_type AS ENUM (
    'death_anniversary',   -- ngày giỗ
    'birthday',            -- sinh nhật
    'wedding_anniversary', -- kỷ niệm ngày cưới
    'clan_ceremony',       -- lễ kỵ, giỗ tổ
    'custom'
);

CREATE TYPE document_type AS ENUM (
    'photo',        -- ảnh
    'id_document',  -- giấy tờ tùy thân
    'certificate',  -- giấy khai sinh, giấy kết hôn...
    'audio',        -- ghi âm
    'video',        -- video
    'other'
);

CREATE TYPE notification_status AS ENUM ('pending', 'sent', 'failed');

-- ============================================================
-- TABLE: clans
-- One row per family clan registered on the platform.
-- ============================================================
CREATE TABLE public.clans (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(255) NOT NULL,
    slug            VARCHAR(100) NOT NULL UNIQUE,  -- url-safe, e.g. "nguyen-bac-ninh"
    description     TEXT,
    origin_place    VARCHAR(255),                  -- quê gốc
    founded_year    SMALLINT,
    avatar_url      VARCHAR(500),
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT clans_slug_format CHECK (slug ~ '^[a-z0-9][a-z0-9\-]*[a-z0-9]$'),
    CONSTRAINT clans_founded_year_range CHECK (founded_year BETWEEN 1000 AND 2100)
);

CREATE INDEX idx_clans_slug ON public.clans (slug);
CREATE INDEX idx_clans_is_active ON public.clans (is_active) WHERE is_active = true;

-- ============================================================
-- TABLE: members
-- Core table. One row per person in a clan's family tree.
-- A spouse from outside the clan is still stored here as a member
-- with is_clan_member = false.
-- ============================================================
CREATE TABLE public.members (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    clan_id         UUID NOT NULL REFERENCES public.clans (id) ON DELETE CASCADE,

    -- Identity
    full_name       VARCHAR(255) NOT NULL,
    birth_name      VARCHAR(255),              -- tên khai sinh (nếu khác tên thường dùng)
    courtesy_name   VARCHAR(255),              -- tên tự / tên hiệu (common in old Vietnamese genealogy)
    gender          gender_type NOT NULL DEFAULT 'unknown',

    -- Dates (nullable — historical figures may have unknown dates)
    birth_date      DATE,
    birth_date_approx BOOLEAN NOT NULL DEFAULT false,  -- true = năm sinh ước tính
    death_date      DATE,
    death_date_approx BOOLEAN NOT NULL DEFAULT false,

    -- Places
    birth_place     VARCHAR(255),
    death_place     VARCHAR(255),
    residence_place VARCHAR(255),              -- nơi sinh sống

    -- Genealogy metadata
    generation      SMALLINT,                 -- đời thứ mấy (tính từ tổ của clan)
    is_clan_founder BOOLEAN NOT NULL DEFAULT false,  -- true for the root ancestor
    is_clan_member  BOOLEAN NOT NULL DEFAULT true,
    -- is_clan_member = false: người này là vợ/chồng từ dòng họ khác,
    -- có trong hệ thống để hoàn thiện cây nhưng không thuộc dòng họ này

    -- Content
    biography       TEXT,
    avatar_url      VARCHAR(500),
    notes           TEXT,

    -- Soft delete
    is_deleted      BOOLEAN NOT NULL DEFAULT false,
    deleted_at      TIMESTAMPTZ,
    deleted_by      UUID,                     -- user_id who deleted

    -- Audit
    created_by      UUID NOT NULL,            -- user_id
    updated_by      UUID,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT members_death_after_birth
        CHECK (death_date IS NULL OR birth_date IS NULL OR death_date >= birth_date),
    CONSTRAINT members_generation_positive
        CHECK (generation IS NULL OR generation > 0)
);

-- Indexes for members
CREATE INDEX idx_members_clan_id ON public.members (clan_id);
CREATE INDEX idx_members_clan_generation ON public.members (clan_id, generation);
CREATE INDEX idx_members_is_deleted ON public.members (clan_id, is_deleted) WHERE is_deleted = false;
CREATE INDEX idx_members_birth_date ON public.members (clan_id, birth_date);
CREATE INDEX idx_members_is_founder ON public.members (clan_id) WHERE is_clan_founder = true;

-- PG 18 requires IMMUTABLE functions in index expressions.
-- unaccent() is STABLE, so we create an IMMUTABLE wrapper.
CREATE OR REPLACE FUNCTION public.f_unaccent(text)
RETURNS text AS $$
    SELECT public.unaccent('public.unaccent', $1)
$$ LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT;

-- Full-text + trigram search index for Vietnamese names
-- f_unaccent removes diacritics: "Nguyễn" matches "Nguyen"
CREATE INDEX idx_members_fullname_search
    ON public.members
    USING gin (
        to_tsvector('simple', public.f_unaccent(full_name))
    );
CREATE INDEX idx_members_fullname_trgm
    ON public.members
    USING gin (public.f_unaccent(full_name) gin_trgm_ops);

-- ============================================================
-- TABLE: relationships
-- Edge list for the family graph.
-- Stores directed edges: member_id --[relation_type]--> related_id
-- ============================================================
CREATE TABLE public.relationships (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    clan_id          UUID NOT NULL REFERENCES public.clans (id) ON DELETE CASCADE,

    member_id        UUID NOT NULL REFERENCES public.members (id) ON DELETE CASCADE,
    related_id       UUID NOT NULL REFERENCES public.members (id) ON DELETE CASCADE,

    relation_type    relation_type NOT NULL,
    relation_subtype relation_subtype NOT NULL,

    -- For spouse relationships: marriage timeline
    start_date       DATE,       -- ngày kết hôn / ngày nhận con nuôi
    end_date         DATE,       -- ngày ly hôn / ngày mất (null = still active)
    is_primary       BOOLEAN NOT NULL DEFAULT true,
    -- is_primary = false for non-primary spouses in polygamous historical marriages
    -- is_primary = true for the main/current marriage

    notes            TEXT,

    created_by       UUID NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Prevent duplicate edges
    CONSTRAINT relationships_no_self_loop
        CHECK (member_id != related_id),

    -- Spouse edges: stored once only (member_id < related_id by convention)
    -- Enforced by application layer + unique index below
    CONSTRAINT relationships_subtype_matches_type CHECK (
        (relation_type IN ('parent', 'child') AND relation_subtype IN ('biological','adoptive','step','foster'))
        OR
        (relation_type = 'spouse' AND relation_subtype IN ('married','divorced','widowed','partner'))
    )
);

-- Prevent exact duplicate relationships
CREATE UNIQUE INDEX idx_relationships_unique_edge
    ON public.relationships (member_id, related_id, relation_type, relation_subtype)
    WHERE relation_type != 'spouse';

-- For spouse: only one active (non-divorced/widowed) marriage at a time per person
CREATE UNIQUE INDEX idx_relationships_one_active_spouse
    ON public.relationships (member_id, relation_type)
    WHERE relation_type = 'spouse' AND end_date IS NULL;

-- Performance indexes for tree traversal
CREATE INDEX idx_relationships_member ON public.relationships (clan_id, member_id, relation_type);
CREATE INDEX idx_relationships_related ON public.relationships (clan_id, related_id, relation_type);

-- ============================================================
-- TABLE: documents
-- Photos, certificates, audio/video attached to a member.
-- ============================================================
CREATE TABLE public.documents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    clan_id         UUID NOT NULL REFERENCES public.clans (id) ON DELETE CASCADE,
    member_id       UUID REFERENCES public.members (id) ON DELETE SET NULL,
    -- member_id nullable: documents can belong to clan (not a specific member)

    title           VARCHAR(255) NOT NULL,
    description     TEXT,
    document_type   document_type NOT NULL,

    -- Supabase Storage
    storage_path    VARCHAR(500) NOT NULL UNIQUE,
    -- format: clans/{clan_id}/members/{member_id}/{uuid}.{ext}
    file_size_bytes BIGINT,
    mime_type       VARCHAR(100),
    original_filename VARCHAR(255),

    -- For photos: optional metadata
    taken_date      DATE,
    taken_place     VARCHAR(255),

    is_avatar       BOOLEAN NOT NULL DEFAULT false,
    -- is_avatar = true means this is the member's profile photo

    created_by      UUID NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT documents_file_size_limit
        CHECK (file_size_bytes IS NULL OR file_size_bytes <= 52428800)
        -- Max 50MB per file
);

CREATE INDEX idx_documents_clan ON public.documents (clan_id);
CREATE INDEX idx_documents_member ON public.documents (member_id) WHERE member_id IS NOT NULL;
CREATE INDEX idx_documents_type ON public.documents (clan_id, document_type);
CREATE INDEX idx_documents_avatar ON public.documents (member_id) WHERE is_avatar = true;

-- ============================================================
-- TABLE: events
-- Ngày giỗ, sinh nhật, lễ kỵ, and custom clan events.
-- ============================================================
CREATE TABLE public.events (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    clan_id             UUID NOT NULL REFERENCES public.clans (id) ON DELETE CASCADE,
    member_id           UUID REFERENCES public.members (id) ON DELETE CASCADE,
    -- member_id nullable for clan-level ceremonies not tied to a specific person

    event_type          event_type NOT NULL,
    title               VARCHAR(255) NOT NULL,
    description         TEXT,

    -- Date handling for lunar/solar calendar
    event_date          DATE NOT NULL,         -- Gregorian date
    is_lunar_calendar   BOOLEAN NOT NULL DEFAULT false,
    -- is_lunar_calendar = true: event_date is in lunar calendar
    -- Frontend must convert for display

    is_recurring        BOOLEAN NOT NULL DEFAULT true,
    -- true: repeats annually (most death anniversaries)
    -- false: one-time event

    notify_days_before  SMALLINT NOT NULL DEFAULT 7
                        CHECK (notify_days_before BETWEEN 0 AND 30),

    created_by          UUID NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_events_clan ON public.events (clan_id);
CREATE INDEX idx_events_member ON public.events (member_id) WHERE member_id IS NOT NULL;
CREATE INDEX idx_events_date ON public.events (clan_id, event_date);
-- Index for scheduler: find events happening in next N days
CREATE INDEX idx_events_recurring_date
    ON public.events (clan_id, event_date)
    WHERE is_recurring = true;

-- ============================================================
-- TABLE: user_clan_roles
-- Which Supabase Auth user belongs to which clan, with what role.
-- A user can belong to at most one clan (enforced by unique index).
-- ============================================================
CREATE TABLE public.user_clan_roles (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    clan_id         UUID NOT NULL REFERENCES public.clans (id) ON DELETE CASCADE,
    user_id         UUID NOT NULL,             -- Supabase Auth user id
    member_id       UUID REFERENCES public.members (id) ON DELETE SET NULL,
    -- member_id: links this user account to their member profile in the tree
    -- nullable: admin account may not be a member in the tree

    role            clan_role NOT NULL DEFAULT 'viewer',
    is_approved     BOOLEAN NOT NULL DEFAULT false,
    -- New users start unapproved; clan admin must approve

    approved_by     UUID,                     -- user_id of approving admin
    approved_at     TIMESTAMPTZ,
    invited_by      UUID,                     -- user_id who sent invite (if invited)

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT user_clan_roles_approval_consistency
        CHECK (
            (is_approved = false AND approved_by IS NULL AND approved_at IS NULL)
            OR
            (is_approved = true AND approved_by IS NOT NULL AND approved_at IS NOT NULL)
        )
);

-- One membership per user per clan (multi-clan support)
CREATE UNIQUE INDEX idx_user_clan_roles_user_clan ON public.user_clan_roles (user_id, clan_id);
CREATE INDEX idx_user_clan_roles_clan ON public.user_clan_roles (clan_id);
CREATE INDEX idx_user_clan_roles_pending
    ON public.user_clan_roles (clan_id, is_approved)
    WHERE is_approved = false;

-- ============================================================
-- TABLE: platform_users
-- Super admin only. Created via bootstrap script (Prompt 1.5).
-- ============================================================
CREATE TABLE public.platform_users (
    id              UUID PRIMARY KEY,          -- Must match Supabase Auth user id
    email           VARCHAR(255) NOT NULL UNIQUE,
    role            VARCHAR(50) NOT NULL DEFAULT 'super_admin',
    is_active       BOOLEAN NOT NULL DEFAULT true,
    last_login_at   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT platform_users_only_super_admin CHECK (role = 'super_admin')
);

-- Only one super_admin can ever exist
CREATE UNIQUE INDEX idx_platform_users_single_super_admin
    ON public.platform_users (role);

-- ============================================================
-- TABLE: audit_logs
-- Immutable log of all write actions across the system.
-- Written by FastAPI service layer, never updated or deleted.
-- ============================================================
CREATE TABLE public.audit_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    clan_id         UUID REFERENCES public.clans (id) ON DELETE SET NULL,
    -- clan_id nullable for platform-level actions (super admin)

    actor_id        UUID NOT NULL,             -- user_id performing the action
    actor_role      VARCHAR(50) NOT NULL,      -- role at time of action

    action          VARCHAR(100) NOT NULL,
    -- Format: "{resource}.{verb}" e.g. "member.create", "relationship.delete"

    resource_type   VARCHAR(50) NOT NULL,      -- "member", "relationship", "document"...
    resource_id     UUID,                      -- id of affected row (nullable for bulk)

    old_value       JSONB,                     -- snapshot before change (for updates/deletes)
    new_value       JSONB,                     -- snapshot after change (for creates/updates)

    ip_address      INET,
    user_agent      VARCHAR(500),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_logs_clan ON public.audit_logs (clan_id, created_at DESC);
CREATE INDEX idx_audit_logs_actor ON public.audit_logs (actor_id, created_at DESC);
CREATE INDEX idx_audit_logs_resource ON public.audit_logs (resource_type, resource_id);
-- Partition hint: in future, partition by created_at month if table grows large

-- ============================================================
-- TABLE: notification_log
-- Tracks FCM push notification delivery status.
-- Prevents duplicate sends for the same event+user.
-- ============================================================
CREATE TABLE public.notification_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    clan_id         UUID NOT NULL REFERENCES public.clans (id) ON DELETE CASCADE,
    event_id        UUID REFERENCES public.events (id) ON DELETE SET NULL,
    user_id         UUID NOT NULL,

    notification_type VARCHAR(50) NOT NULL,    -- "death_anniversary", "birthday", etc.
    title           VARCHAR(255) NOT NULL,
    body            TEXT NOT NULL,
    fcm_token       VARCHAR(500),
    status          notification_status NOT NULL DEFAULT 'pending',
    sent_at         TIMESTAMPTZ,
    error_message   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_notification_log_clan_date
    ON public.notification_log (clan_id, created_at DESC);
-- Deduplication: one notification per user per event per day
CREATE UNIQUE INDEX idx_notification_log_dedup
    ON public.notification_log (user_id, event_id, notification_type, CAST(created_at AT TIME ZONE 'UTC' AS date));

-- ============================================================
-- TRIGGERS: auto-update updated_at
-- ============================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_clans_updated_at
    BEFORE UPDATE ON public.clans
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_members_updated_at
    BEFORE UPDATE ON public.members
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_relationships_updated_at
    BEFORE UPDATE ON public.relationships
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_documents_updated_at
    BEFORE UPDATE ON public.documents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_events_updated_at
    BEFORE UPDATE ON public.events
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_user_clan_roles_updated_at
    BEFORE UPDATE ON public.user_clan_roles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
