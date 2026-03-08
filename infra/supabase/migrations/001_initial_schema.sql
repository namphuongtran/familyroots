-- ============================================================
-- 001_initial_schema.sql
-- Full DDL for FamilyRoots — PostgreSQL 16+
-- Graph model: Person (global nodes), Marriage/ParentChild (edges)
-- ClanMembership (M:N view filter), created_by_clan_id on edges
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

CREATE TYPE clan_role AS ENUM ('admin', 'editor', 'viewer');
-- Note: 'super_admin' lives in user_profiles.platform_role

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
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                    VARCHAR(255) NOT NULL,
    slug                    VARCHAR(100) NOT NULL UNIQUE,  -- url-safe, e.g. "nguyen-bac-ninh"
    description             TEXT,
    origin_place            VARCHAR(255),                  -- quê gốc
    founded_year            SMALLINT,
    avatar_url              VARCHAR(500),
    motto                   TEXT,                          -- gia huấn / châm ngôn
    ancestral_hall_location VARCHAR(500),                  -- nhà thờ tổ
    clan_rules              TEXT,                          -- gia quy
    is_active               BOOLEAN NOT NULL DEFAULT true,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT clans_slug_format CHECK (slug ~ '^[a-z0-9][a-z0-9\-]*[a-z0-9]$'),
    CONSTRAINT clans_founded_year_range CHECK (founded_year BETWEEN 1000 AND 2100)
);

CREATE INDEX idx_clans_slug ON public.clans (slug);
CREATE INDEX idx_clans_is_active ON public.clans (is_active) WHERE is_active = true;

-- ============================================================
-- TABLE: persons
-- Global entity — one row per real person. No clan_id FK.
-- A person can appear in multiple clans via clan_memberships.
-- ============================================================
CREATE TABLE public.persons (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    origin_clan_id  UUID REFERENCES public.clans (id) ON DELETE SET NULL,
    -- origin_clan_id: the clan that first created this person record (nullable)

    -- Identity
    full_name       VARCHAR(255) NOT NULL,
    birth_name      VARCHAR(255),              -- tên khai sinh (nếu khác tên thường dùng)
    courtesy_name   VARCHAR(255),              -- tên tự / tên hiệu
    posthumous_name VARCHAR(255),              -- tên thụy / tên sau khi mất
    alias_name      VARCHAR(255),              -- biệt danh
    gender          gender_type NOT NULL DEFAULT 'unknown',

    -- Dates (nullable — historical figures may have unknown dates)
    birth_date      DATE,
    birth_date_approx BOOLEAN NOT NULL DEFAULT false,  -- true = năm sinh ước tính
    death_date      DATE,
    death_date_approx BOOLEAN NOT NULL DEFAULT false,
    lunar_birth_date VARCHAR(30),              -- ngày sinh âm lịch (free text e.g. "15/01 Canh Tý")
    lunar_death_date VARCHAR(30),              -- ngày mất âm lịch

    -- Places
    birth_place     VARCHAR(255),
    death_place     VARCHAR(255),
    burial_place    VARCHAR(255),              -- nơi an táng
    tomb_location   VARCHAR(500),              -- vị trí mộ (có thể là toạ độ / mô tả)
    residence_place VARCHAR(255),              -- nơi sinh sống

    -- Personal info
    religion        VARCHAR(100),              -- tôn giáo
    nationality     VARCHAR(100) DEFAULT 'VN', -- quốc tịch
    occupation      VARCHAR(255),              -- nghề nghiệp
    education_level VARCHAR(255),              -- trình độ học vấn
    title_rank      VARCHAR(255),              -- chức danh / phẩm hàm
    phone           VARCHAR(50),               -- số điện thoại
    email           VARCHAR(255),              -- email

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

    CONSTRAINT persons_death_after_birth
        CHECK (death_date IS NULL OR birth_date IS NULL OR death_date >= birth_date)
);

-- Indexes for persons
CREATE INDEX idx_persons_is_deleted ON public.persons (is_deleted) WHERE is_deleted = false;
CREATE INDEX idx_persons_origin_clan ON public.persons (origin_clan_id) WHERE origin_clan_id IS NOT NULL;

-- PG 18 requires IMMUTABLE functions in index expressions.
-- unaccent() is STABLE, so we create an IMMUTABLE wrapper.
CREATE OR REPLACE FUNCTION public.f_unaccent(text)
RETURNS text AS $$
    SELECT public.unaccent('public.unaccent', $1)
$$ LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT;

-- Full-text + trigram search index for Vietnamese names
-- f_unaccent removes diacritics: "Nguyễn" matches "Nguyen"
CREATE INDEX idx_persons_fullname_search
    ON public.persons
    USING gin (
        to_tsvector('simple', public.f_unaccent(full_name))
    );
CREATE INDEX idx_persons_fullname_trgm
    ON public.persons
    USING gin (public.f_unaccent(full_name) gin_trgm_ops);

-- ============================================================
-- TABLE: branches
-- Chi / Phái / Nhánh — sub-lineage within a clan.
-- A branch belongs to exactly one clan and may form a hierarchy.
-- ============================================================
CREATE TABLE public.branches (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    clan_id             UUID NOT NULL REFERENCES public.clans (id) ON DELETE CASCADE,
    name                VARCHAR(255) NOT NULL,
    description         TEXT,
    founder_person_id   UUID REFERENCES public.persons (id) ON DELETE SET NULL,
    parent_branch_id    UUID REFERENCES public.branches (id) ON DELETE SET NULL,
    branch_order        SMALLINT,             -- display order among siblings

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT branches_order_positive CHECK (branch_order IS NULL OR branch_order > 0)
);

CREATE INDEX idx_branches_clan ON public.branches (clan_id);
CREATE INDEX idx_branches_parent ON public.branches (parent_branch_id) WHERE parent_branch_id IS NOT NULL;

-- ============================================================
-- TABLE: clan_memberships
-- M:N join table: which persons belong to which clans.
-- generation and is_founder are per-clan context, not global.
-- ============================================================
CREATE TABLE public.clan_memberships (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id       UUID NOT NULL REFERENCES public.persons (id) ON DELETE CASCADE,
    clan_id         UUID NOT NULL REFERENCES public.clans (id) ON DELETE CASCADE,
    branch_id       UUID REFERENCES public.branches (id) ON DELETE SET NULL,
    -- branch_id: which chi/phái this member belongs to within this clan

    role            VARCHAR(20) NOT NULL DEFAULT 'blood',
    -- role values: 'blood' (huyết thống), 'spouse' (dâu/rể), 'adopted' (con nuôi)
    generation      SMALLINT,                 -- đời thứ mấy (tính từ tổ CỦA CLAN NÀY)
    is_founder      BOOLEAN NOT NULL DEFAULT false,  -- true for the root ancestor of THIS clan
    joined_at       TIMESTAMPTZ,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_clan_memberships_person_clan UNIQUE (person_id, clan_id),
    CONSTRAINT clan_memberships_role_check
        CHECK (role IN ('blood', 'spouse', 'adopted')),
    CONSTRAINT clan_memberships_generation_positive
        CHECK (generation IS NULL OR generation > 0)
);

CREATE INDEX idx_clan_memberships_clan ON public.clan_memberships (clan_id);
CREATE INDEX idx_clan_memberships_person ON public.clan_memberships (person_id);
CREATE INDEX idx_clan_memberships_clan_generation ON public.clan_memberships (clan_id, generation);
CREATE INDEX idx_clan_memberships_founder
    ON public.clan_memberships (clan_id) WHERE is_founder = true;
CREATE INDEX idx_clan_memberships_branch
    ON public.clan_memberships (branch_id) WHERE branch_id IS NOT NULL;

-- ============================================================
-- TABLE: marriages
-- Global edge: person1 ↔ person2.
-- created_by_clan_id tracks which clan created this record.
-- Handles: polygamy, divorce, remarriage, widowed.
-- ============================================================
CREATE TABLE public.marriages (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    person1_id        UUID NOT NULL REFERENCES public.persons (id) ON DELETE CASCADE,
    person2_id        UUID NOT NULL REFERENCES public.persons (id) ON DELETE CASCADE,
    created_by_clan_id UUID NOT NULL REFERENCES public.clans (id) ON DELETE CASCADE,

    marriage_date     DATE,                    -- ngày cưới (solar)
    divorce_date      DATE,                    -- ngày ly hôn
    marriage_place    VARCHAR(255),            -- nơi kết hôn
    status            VARCHAR(20) NOT NULL DEFAULT 'married',
    -- status values: 'married', 'divorced', 'widowed', 'separated'
    spouse_order      SMALLINT,               -- thứ tự (vợ cả = 1, vợ hai = 2, etc.)
    notes             TEXT,

    -- Soft delete
    is_deleted        BOOLEAN NOT NULL DEFAULT false,
    deleted_at        TIMESTAMPTZ,
    deleted_by        UUID,

    -- Audit
    created_by        UUID NOT NULL,           -- user_id
    updated_by        UUID,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT marriages_no_self CHECK (person1_id != person2_id),
    CONSTRAINT marriages_status_check
        CHECK (status IN ('married', 'divorced', 'widowed', 'separated')),
    CONSTRAINT marriages_divorce_after_marriage
        CHECK (divorce_date IS NULL OR marriage_date IS NULL OR divorce_date >= marriage_date),
    CONSTRAINT marriages_spouse_order_positive
        CHECK (spouse_order IS NULL OR spouse_order > 0)
);

CREATE INDEX idx_marriages_person1 ON public.marriages (person1_id);
CREATE INDEX idx_marriages_person2 ON public.marriages (person2_id);
CREATE INDEX idx_marriages_clan ON public.marriages (created_by_clan_id);
CREATE INDEX idx_marriages_is_deleted ON public.marriages (is_deleted) WHERE is_deleted = false;
-- Prevent duplicate active marriages between the same pair
CREATE UNIQUE INDEX idx_marriages_unique_pair
    ON public.marriages (LEAST(person1_id, person2_id), GREATEST(person1_id, person2_id), status)
    WHERE status = 'married' AND is_deleted = false;

-- ============================================================
-- TABLE: parent_child
-- Global directed edge: parent → child.
-- created_by_clan_id tracks which clan created this record.
-- Handles: biological, adopted, step, foster.
-- ============================================================
CREATE TABLE public.parent_child (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_id           UUID NOT NULL REFERENCES public.persons (id) ON DELETE CASCADE,
    child_id            UUID NOT NULL REFERENCES public.persons (id) ON DELETE CASCADE,
    created_by_clan_id  UUID NOT NULL REFERENCES public.clans (id) ON DELETE CASCADE,

    relationship_type   VARCHAR(20) NOT NULL DEFAULT 'biological',
    -- values: 'biological', 'adopted', 'step', 'foster'
    birth_order         SMALLINT,              -- thứ tự sinh (con thứ mấy)
    notes               TEXT,

    -- Soft delete
    is_deleted          BOOLEAN NOT NULL DEFAULT false,
    deleted_at          TIMESTAMPTZ,
    deleted_by          UUID,

    -- Audit
    created_by          UUID NOT NULL,         -- user_id
    updated_by          UUID,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT parent_child_no_self CHECK (parent_id != child_id),
    CONSTRAINT parent_child_type_check
        CHECK (relationship_type IN ('biological', 'adopted', 'step', 'foster'))
);

-- Prevent exact duplicate parent-child edges (only among active records)
CREATE UNIQUE INDEX idx_parent_child_unique_edge
    ON public.parent_child (parent_id, child_id, relationship_type)
    WHERE is_deleted = false;

CREATE INDEX idx_parent_child_parent ON public.parent_child (parent_id);
CREATE INDEX idx_parent_child_child ON public.parent_child (child_id);
CREATE INDEX idx_parent_child_clan ON public.parent_child (created_by_clan_id);
CREATE INDEX idx_parent_child_is_deleted ON public.parent_child (is_deleted) WHERE is_deleted = false;

-- ============================================================
-- TABLE: documents
-- Photos, certificates, audio/video attached to a person.
-- ============================================================
CREATE TABLE public.documents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    clan_id         UUID NOT NULL REFERENCES public.clans (id) ON DELETE CASCADE,
    person_id       UUID REFERENCES public.persons (id) ON DELETE SET NULL,
    -- person_id nullable: documents can belong to clan (not a specific person)

    title           VARCHAR(255) NOT NULL,
    description     TEXT,
    document_type   document_type NOT NULL,

    -- Supabase Storage
    storage_path    VARCHAR(500) NOT NULL UNIQUE,
    -- format: clans/{clan_id}/persons/{person_id}/{uuid}.{ext}
    file_size_bytes BIGINT,
    mime_type       VARCHAR(100),
    original_filename VARCHAR(255),

    -- For photos: optional metadata
    taken_date      DATE,
    taken_place     VARCHAR(255),

    is_avatar       BOOLEAN NOT NULL DEFAULT false,
    -- is_avatar = true means this is the person's profile photo

    created_by      UUID NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT documents_file_size_limit
        CHECK (file_size_bytes IS NULL OR file_size_bytes <= 52428800)
        -- Max 50MB per file
);

CREATE INDEX idx_documents_clan ON public.documents (clan_id);
CREATE INDEX idx_documents_person ON public.documents (person_id) WHERE person_id IS NOT NULL;
CREATE INDEX idx_documents_type ON public.documents (clan_id, document_type);
CREATE INDEX idx_documents_avatar ON public.documents (person_id) WHERE is_avatar = true;

-- ============================================================
-- TABLE: events
-- Ngày giỗ, sinh nhật, lễ kỵ, and custom clan events.
-- ============================================================
CREATE TABLE public.events (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    clan_id             UUID NOT NULL REFERENCES public.clans (id) ON DELETE CASCADE,
    person_id           UUID REFERENCES public.persons (id) ON DELETE CASCADE,
    -- person_id nullable for clan-level ceremonies not tied to a specific person

    event_type          event_type NOT NULL,
    title               VARCHAR(255) NOT NULL,
    description         TEXT,

    -- Date handling for lunar/solar calendar
    event_date          DATE NOT NULL,         -- Gregorian date
    is_lunar_calendar   BOOLEAN NOT NULL DEFAULT false,

    is_recurring        BOOLEAN NOT NULL DEFAULT true,

    notify_days_before  SMALLINT NOT NULL DEFAULT 7
                        CHECK (notify_days_before BETWEEN 0 AND 30),

    created_by          UUID NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_events_clan ON public.events (clan_id);
CREATE INDEX idx_events_person ON public.events (person_id) WHERE person_id IS NOT NULL;
CREATE INDEX idx_events_date ON public.events (clan_id, event_date);
CREATE INDEX idx_events_recurring_date
    ON public.events (clan_id, event_date)
    WHERE is_recurring = true;

-- ============================================================
-- TABLE: user_profiles
-- Local cache of Supabase Auth users, synced on first login.
-- ============================================================
CREATE TABLE public.user_profiles (
    id              UUID PRIMARY KEY,          -- Must match Supabase Auth user id
    email           VARCHAR(255) NOT NULL UNIQUE,
    display_name    VARCHAR(255),
    avatar_url      VARCHAR(500),
    language        VARCHAR(10) NOT NULL DEFAULT 'vi',
    timezone        VARCHAR(50) NOT NULL DEFAULT 'Asia/Ho_Chi_Minh',
    is_active       BOOLEAN NOT NULL DEFAULT true,
    platform_role   VARCHAR(50) NOT NULL DEFAULT 'user',  -- 'user' or 'super_admin'
    person_id       UUID UNIQUE REFERENCES public.persons (id) ON DELETE SET NULL,
    -- person_id: canonical link from user account → person node in the tree (nullable)
    last_login_at   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- TABLE: user_devices
-- FCM tokens per user device for push notifications.
-- ============================================================
CREATE TABLE public.user_devices (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES public.user_profiles (id) ON DELETE CASCADE,
    fcm_token       VARCHAR(500) NOT NULL UNIQUE,
    device_name     VARCHAR(255),
    platform        VARCHAR(20) NOT NULL,      -- 'ios', 'android', 'web'
    is_active       BOOLEAN NOT NULL DEFAULT true,
    last_used_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_user_devices_user_id ON public.user_devices (user_id);

-- ============================================================
-- TABLE: clan_settings
-- Per-clan configuration (one row per clan).
-- ============================================================
CREATE TABLE public.clan_settings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    clan_id         UUID NOT NULL UNIQUE REFERENCES public.clans (id) ON DELETE CASCADE,
    approval_config JSONB,                     -- {"require_approval": true, ...}
    default_language VARCHAR(10) NOT NULL DEFAULT 'vi',
    tree_display_mode VARCHAR(20) NOT NULL DEFAULT 'vertical',
    allow_public_tree BOOLEAN NOT NULL DEFAULT false,
    notification_defaults JSONB,
    privacy_level   VARCHAR(20) NOT NULL DEFAULT 'clan_members',
    max_upload_size_mb SMALLINT NOT NULL DEFAULT 10,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- TABLE: clan_invitations
-- Secure invite links with expiration for joining a clan.
-- ============================================================
CREATE TABLE public.clan_invitations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    clan_id         UUID NOT NULL REFERENCES public.clans (id) ON DELETE CASCADE,
    email           VARCHAR(255) NOT NULL,
    role            VARCHAR(20) NOT NULL DEFAULT 'viewer',
    invited_by      UUID NOT NULL,
    token           VARCHAR(255) NOT NULL UNIQUE,
    expires_at      TIMESTAMPTZ NOT NULL,
    accepted_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_clan_invitations_clan_id ON public.clan_invitations (clan_id);
CREATE INDEX ix_clan_invitations_clan_email ON public.clan_invitations (clan_id, email);

-- ============================================================
-- TABLE: user_clan_roles
-- Which Supabase Auth user belongs to which clan, with what role.
-- ============================================================
CREATE TABLE public.user_clan_roles (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    clan_id         UUID NOT NULL REFERENCES public.clans (id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES public.user_profiles (id) ON DELETE CASCADE,
    person_id       UUID REFERENCES public.persons (id) ON DELETE SET NULL,
    -- person_id: links this user account to their person profile in the tree
    -- nullable: admin account may not be a person in the tree

    role            clan_role NOT NULL DEFAULT 'viewer',
    is_approved     BOOLEAN NOT NULL DEFAULT false,

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

CREATE UNIQUE INDEX idx_user_clan_roles_user_clan ON public.user_clan_roles (user_id, clan_id);
CREATE INDEX idx_user_clan_roles_clan ON public.user_clan_roles (clan_id);
CREATE INDEX idx_user_clan_roles_pending
    ON public.user_clan_roles (clan_id, is_approved)
    WHERE is_approved = false;

-- ============================================================
-- TABLE: change_requests
-- Approval workflow for edits submitted by editors/viewers.
-- ============================================================
CREATE TABLE public.change_requests (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    clan_id         UUID NOT NULL REFERENCES public.clans (id) ON DELETE CASCADE,
    requester_id    UUID NOT NULL,             -- user_id who submitted the request
    action          VARCHAR(20) NOT NULL,      -- 'create', 'update', 'delete'
    resource_type   VARCHAR(50) NOT NULL,      -- 'person', 'marriage', 'parent_child', 'event', 'document'
    resource_id     UUID,                      -- id of existing resource (null for create)
    payload         JSONB,                     -- proposed changes
    status          VARCHAR(20) NOT NULL DEFAULT 'pending',
    -- status values: 'pending', 'approved', 'rejected'
    reviewed_by     UUID,                      -- user_id of reviewer
    reviewed_at     TIMESTAMPTZ,
    review_notes    TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT change_requests_action_check
        CHECK (action IN ('create', 'update', 'delete')),
    CONSTRAINT change_requests_resource_type_check
        CHECK (resource_type IN ('person', 'marriage', 'parent_child', 'event', 'document')),
    CONSTRAINT change_requests_status_check
        CHECK (status IN ('pending', 'approved', 'rejected'))
);

CREATE INDEX idx_change_requests_clan ON public.change_requests (clan_id);
CREATE INDEX idx_change_requests_pending
    ON public.change_requests (clan_id, status)
    WHERE status = 'pending';

-- ============================================================
-- TABLE: audit_logs
-- Immutable log of all write actions across the system.
-- ============================================================
CREATE TABLE public.audit_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    clan_id         UUID REFERENCES public.clans (id) ON DELETE SET NULL,

    actor_id        UUID NOT NULL,
    actor_role      VARCHAR(50) NOT NULL,

    action          VARCHAR(100) NOT NULL,
    -- Format: "{resource}.{verb}" e.g. "person.create", "marriage.delete"

    resource_type   VARCHAR(50) NOT NULL,
    resource_id     UUID,

    old_value       JSONB,
    new_value       JSONB,

    ip_address      INET,
    user_agent      VARCHAR(500),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_logs_clan ON public.audit_logs (clan_id, created_at DESC);
CREATE INDEX idx_audit_logs_actor ON public.audit_logs (actor_id, created_at DESC);
CREATE INDEX idx_audit_logs_resource ON public.audit_logs (resource_type, resource_id);

-- ============================================================
-- TABLE: notification_log
-- Tracks FCM push notification delivery status.
-- ============================================================
CREATE TABLE public.notification_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    clan_id         UUID NOT NULL REFERENCES public.clans (id) ON DELETE CASCADE,
    event_id        UUID REFERENCES public.events (id) ON DELETE SET NULL,
    user_id         UUID NOT NULL,

    notification_type VARCHAR(50) NOT NULL,
    title           VARCHAR(255) NOT NULL,
    body            TEXT NOT NULL,
    status          notification_status NOT NULL DEFAULT 'pending',
    sent_at         TIMESTAMPTZ,
    error_message   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_notification_log_clan_date
    ON public.notification_log (clan_id, created_at DESC);
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

CREATE TRIGGER trg_persons_updated_at
    BEFORE UPDATE ON public.persons
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_clan_memberships_updated_at
    BEFORE UPDATE ON public.clan_memberships
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_marriages_updated_at
    BEFORE UPDATE ON public.marriages
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_parent_child_updated_at
    BEFORE UPDATE ON public.parent_child
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_documents_updated_at
    BEFORE UPDATE ON public.documents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_events_updated_at
    BEFORE UPDATE ON public.events
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_user_profiles_updated_at
    BEFORE UPDATE ON public.user_profiles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_clan_settings_updated_at
    BEFORE UPDATE ON public.clan_settings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_user_clan_roles_updated_at
    BEFORE UPDATE ON public.user_clan_roles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_change_requests_updated_at
    BEFORE UPDATE ON public.change_requests
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_branches_updated_at
    BEFORE UPDATE ON public.branches
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
