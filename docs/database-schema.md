# Database Schema

## Overview

FamilyRoots uses **PostgreSQL 16+** with a single `public` schema. The core data model treats genealogy as a **graph**, not a tree:

- **Node** = `Person` (global entity, independent of any clan)
- **Edge** = `Marriage` | `ParentChild` (global relationships between persons)
- **View** = `ClanMembership` (M:N link filtering persons into clan views)

Data isolation between clans is enforced by:
- `ClanMembership` for person visibility (read RLS)
- `created_by_clan_id` on edges for write control (write RLS)
- Supabase Row Level Security (RLS) policies at the database level

### Architecture Principle

```
Person ──────── exists globally (no clan_id)
ClanMembership ── links Person ↔ Clan (M:N, with role + generation)
Marriage ──────── global edge (person1 ↔ person2, created_by_clan_id for write RLS)
ParentChild ───── global edge (parent → child, created_by_clan_id for write RLS)
```

A person like "Đào Thị B" (origin clan Đào) who marries "Trần Văn A" (clan Trần) has:
- **One** Person record (no duplication)
- A `ClanMembership(B → Trần, role=spouse)`
- A `Marriage(A ↔ B, created_by_clan_id=Trần)`
- If clan Đào also uses the system: `ClanMembership(A → Đào, role=spouse)`

---

## ER Diagram

```mermaid
erDiagram
    clans {
        uuid id PK
        varchar name
        varchar slug UK
        text description
        varchar origin_place
        smallint founded_year
        varchar avatar_url
        text motto
        varchar ancestral_hall_location
        text clan_rules
        boolean is_active
        timestamptz created_at
        timestamptz updated_at
    }

    persons {
        uuid id PK
        uuid origin_clan_id FK "nullable - original clan"
        varchar full_name
        varchar birth_name
        varchar courtesy_name
        varchar posthumous_name
        varchar alias_name
        varchar gender
        date birth_date
        boolean birth_date_approx
        date death_date
        boolean death_date_approx
        varchar lunar_birth_date
        varchar lunar_death_date
        varchar birth_place
        varchar death_place
        varchar burial_place
        varchar tomb_location
        varchar residence_place
        varchar religion
        varchar nationality
        varchar occupation
        varchar education_level
        varchar title_rank
        varchar phone
        varchar email
        text biography
        varchar avatar_url
        text notes
        boolean is_deleted
        timestamptz deleted_at
        uuid deleted_by
        uuid created_by
        uuid updated_by
        timestamptz created_at
        timestamptz updated_at
    }

    user_profiles {
        uuid id PK "Supabase auth.users.id"
        varchar email UK
        varchar display_name
        varchar avatar_url
        varchar language "default vi"
        varchar timezone "default Asia/Ho_Chi_Minh"
        boolean is_active
        varchar platform_role "user | super_admin"
        timestamptz last_login_at
        timestamptz created_at
        timestamptz updated_at
    }

    user_devices {
        uuid id PK
        uuid user_id FK
        varchar fcm_token UK
        varchar device_name
        varchar platform "ios | android | web"
        boolean is_active
        timestamptz last_used_at
        timestamptz created_at
    }

    clan_memberships {
        uuid id PK
        uuid person_id FK
        uuid clan_id FK
        varchar role "blood | spouse | adopted"
        smallint generation "relative to clan"
        boolean is_founder
        timestamptz joined_at
        timestamptz created_at
        timestamptz updated_at
    }

    marriages {
        uuid id PK
        uuid person1_id FK
        uuid person2_id FK
        uuid created_by_clan_id FK "managing clan - write RLS"
        date marriage_date
        date divorce_date
        varchar marriage_place
        varchar status "married | divorced | widowed | separated"
        smallint spouse_order "1st wife, 2nd wife..."
        text notes
        uuid created_by
        timestamptz created_at
        timestamptz updated_at
    }

    parent_child {
        uuid id PK
        uuid parent_id FK
        uuid child_id FK
        uuid created_by_clan_id FK "managing clan - write RLS"
        varchar relationship_type "biological | adopted | step | foster"
        text notes
        uuid created_by
        timestamptz created_at
        timestamptz updated_at
    }

    user_clan_roles {
        uuid id PK
        uuid clan_id FK
        uuid user_id FK "FK to user_profiles"
        uuid person_id FK "nullable - linked person record"
        varchar role "admin | editor | viewer"
        boolean is_approved
        uuid approved_by
        timestamptz approved_at
        uuid invited_by
        timestamptz created_at
        timestamptz updated_at
    }

    clan_settings {
        uuid id PK
        uuid clan_id FK UK "one per clan"
        jsonb approval_config
        varchar default_language "default vi"
        varchar tree_display_mode "vertical | horizontal"
        boolean allow_public_tree
        jsonb notification_defaults
        varchar privacy_level "private | clan_members | public"
        smallint max_upload_size_mb "default 10"
        timestamptz created_at
        timestamptz updated_at
    }

    clan_invitations {
        uuid id PK
        uuid clan_id FK
        varchar email
        varchar role "default viewer"
        uuid invited_by
        varchar token UK
        timestamptz expires_at
        timestamptz accepted_at "nullable"
        timestamptz created_at
    }

    events {
        uuid id PK
        uuid clan_id FK
        uuid person_id FK "nullable"
        varchar event_type
        varchar title
        text description
        date event_date
        boolean is_lunar_calendar
        boolean is_recurring
        smallint notify_days_before
        uuid created_by
        timestamptz created_at
        timestamptz updated_at
    }

    documents {
        uuid id PK
        uuid clan_id FK
        uuid person_id FK "nullable"
        varchar title
        text description
        varchar document_type
        varchar storage_path UK
        bigint file_size_bytes
        varchar mime_type
        varchar original_filename
        date taken_date
        varchar taken_place
        boolean is_avatar
        uuid created_by
        timestamptz created_at
        timestamptz updated_at
    }

    change_requests {
        uuid id PK
        uuid clan_id FK
        uuid requester_id
        varchar action "create | update | delete"
        varchar resource_type "person | marriage | parent_child | event | document"
        uuid resource_id "nullable - null for create"
        jsonb payload
        varchar status "pending | approved | rejected"
        uuid reviewed_by
        timestamptz reviewed_at
        text review_notes
        timestamptz created_at
    }

    audit_logs {
        uuid id PK
        uuid clan_id
        uuid actor_id
        varchar actor_role
        varchar action
        varchar resource_type
        uuid resource_id
        jsonb old_value
        jsonb new_value
        inet ip_address
        varchar user_agent
        timestamptz created_at
    }

    notification_log {
        uuid id PK
        uuid clan_id FK
        uuid event_id FK
        uuid user_id
        varchar notification_type
        varchar title
        text body
        varchar status
        timestamptz sent_at
        text error_message
        timestamptz created_at
    }

    %% ── Relationships ──
    user_profiles ||--o{ user_clan_roles : "has clan roles"
    user_profiles ||--o{ user_devices : "has devices"
    clans ||--o{ clan_memberships : "has members"
    clans ||--o{ user_clan_roles : "has roles"
    clans ||--|| clan_settings : "has settings"
    clans ||--o{ clan_invitations : "has invitations"
    clans ||--o{ events : "has"
    clans ||--o{ documents : "has"
    clans ||--o{ change_requests : "has"
    clans ||--o{ notification_log : "has"
    clans ||--o{ marriages : "created_by_clan"
    clans ||--o{ parent_child : "created_by_clan"
    clans ||--o{ audit_logs : "has logs"
    persons ||--o{ clan_memberships : "belongs to clans"
    persons ||--o{ marriages : "person1"
    persons ||--o{ marriages : "person2"
    persons ||--o{ parent_child : "as parent"
    persons ||--o{ parent_child : "as child"
    persons ||--o{ events : "about"
    persons ||--o{ documents : "attached"
    persons |o--o| user_clan_roles : "linked account"
    persons }o--o| clans : "origin_clan"
    events ||--o{ notification_log : "triggers"
```

---

## Table Details

### `clans`

Central registry of family clans (dòng họ). Each clan is a tenant.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `name` | VARCHAR(255) | NOT NULL | Display name (e.g. "Họ Trần Văn") |
| `slug` | VARCHAR(100) | UNIQUE, NOT NULL | URL-safe identifier |
| `description` | TEXT | | |
| `origin_place` | VARCHAR(255) | | Quê quán gốc |
| `founded_year` | SMALLINT | | Năm thành lập |
| `avatar_url` | VARCHAR(500) | | |
| `motto` | TEXT | | Phương châm gia tộc |
| `ancestral_hall_location` | VARCHAR(500) | | Địa chỉ nhà thờ tổ |
| `clan_rules` | TEXT | | Gia huấn |
| `is_active` | BOOLEAN | DEFAULT true | |
| `created_at` | TIMESTAMPTZ | NOT NULL, auto | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, auto | |

**Design notes:**
- `approval_config` lives in `clan_settings` table (never on `clans`).

### `user_profiles`

Local cache of Supabase Auth user data. Created lazily on first login via `ensure_user_profile()`. The primary key is the Supabase `auth.users.id` UUID.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | Supabase `auth.users.id` (not auto-generated) |
| `email` | VARCHAR(255) | UNIQUE, NOT NULL | Synced from JWT on first login |
| `display_name` | VARCHAR(255) | | From JWT `user_metadata.full_name` or email prefix |
| `avatar_url` | VARCHAR(500) | | Profile avatar |
| `language` | VARCHAR(10) | DEFAULT 'vi' | UI language preference |
| `timezone` | VARCHAR(50) | DEFAULT 'Asia/Ho_Chi_Minh' | User timezone |
| `is_active` | BOOLEAN | DEFAULT true | App-level suspension |
| `platform_role` | VARCHAR(50) | DEFAULT 'user' | `user` or `super_admin` |
| `last_login_at` | TIMESTAMPTZ | | Updated on login (throttled to every 5 min) |
| `created_at` | TIMESTAMPTZ | NOT NULL, auto | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, auto | |

**Sync strategy:** On-first-login (lazy creation). When `get_current_user()` validates the JWT, `ensure_user_profile()` checks if a `user_profiles` row exists. If not, it creates one from JWT claims. No Supabase webhooks or triggers needed.

### `user_devices`

Tracks FCM tokens per user device for push notifications. Replaces the old `fcm_token` column on `notification_log`.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `user_id` | UUID | FK → user_profiles.id (CASCADE), NOT NULL | |
| `fcm_token` | VARCHAR(500) | UNIQUE, NOT NULL | Firebase Cloud Messaging token |
| `device_name` | VARCHAR(255) | | e.g. "iPhone 15 Pro" |
| `platform` | VARCHAR(20) | NOT NULL | `ios`, `android`, `web` |
| `is_active` | BOOLEAN | DEFAULT true | Deactivated when token expires |
| `last_used_at` | TIMESTAMPTZ | | |
| `created_at` | TIMESTAMPTZ | NOT NULL, auto | |

### `persons`

Global person entity — independent of any clan. A person exists once and can appear in multiple clans via `clan_memberships`.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `origin_clan_id` | UUID | FK → clans.id (SET NULL), nullable | Họ gốc (reference only) |
| `full_name` | VARCHAR(255) | NOT NULL | Tên đầy đủ |
| `birth_name` | VARCHAR(255) | | Tên khai sinh |
| `courtesy_name` | VARCHAR(255) | | Tên tự / tên chữ |
| `posthumous_name` | VARCHAR(255) | | Tên huý / tên thụy (ancestor worship) |
| `alias_name` | VARCHAR(255) | | Biệt danh / tên thường gọi |
| `gender` | VARCHAR(20) | NOT NULL, DEFAULT 'unknown' | male, female, unknown |
| `birth_date` | DATE | | Solar calendar (canonical for sorting) |
| `birth_date_approx` | BOOLEAN | DEFAULT false | True if date is estimated |
| `death_date` | DATE | | Solar calendar |
| `death_date_approx` | BOOLEAN | DEFAULT false | |
| `lunar_birth_date` | VARCHAR(30) | | Display only, e.g. "15/08 Nhâm Tý" |
| `lunar_death_date` | VARCHAR(30) | | Display only |
| `birth_place` | VARCHAR(255) | | Nơi sinh |
| `death_place` | VARCHAR(255) | | Nơi mất |
| `burial_place` | VARCHAR(255) | | Nơi an táng |
| `tomb_location` | VARCHAR(500) | | Phần mộ hiện tại (may differ from burial) |
| `residence_place` | VARCHAR(255) | | Chỗ ở hiện tại |
| `religion` | VARCHAR(100) | | Tôn giáo |
| `nationality` | VARCHAR(100) | DEFAULT 'VN' | Quốc tịch |
| `occupation` | VARCHAR(255) | | Nghề nghiệp |
| `education_level` | VARCHAR(255) | | Học vấn |
| `title_rank` | VARCHAR(255) | | Chức danh, phẩm hàm |
| `phone` | VARCHAR(50) | | Số điện thoại |
| `email` | VARCHAR(255) | | Email liên hệ |
| `biography` | TEXT | | Tiểu sử |
| `avatar_url` | VARCHAR(500) | | Ảnh đại diện |
| `notes` | TEXT | | Ghi chú |
| `is_deleted` | BOOLEAN | DEFAULT false | Soft delete |
| `deleted_at` | TIMESTAMPTZ | | |
| `deleted_by` | UUID | | |
| `created_by` | UUID | NOT NULL | |
| `updated_by` | UUID | | |
| `created_at` | TIMESTAMPTZ | NOT NULL, auto | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, auto | |

**Design notes:**
- **No `clan_id`** — Person is a global entity. Clan association is via `clan_memberships`.
- **Lunar dates as VARCHAR** — Lunar calendar doesn't map 1:1 to solar (leap months, can chi). Stored as display text. Solar DATE columns remain canonical for computation/sorting.
- **`origin_clan_id`** — Soft reference to original clan. Not required. Useful for display ("Họ gốc: Đào").

### `clan_memberships`

M:N link between persons and clans. Determines which persons appear in which clan's tree.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `person_id` | UUID | FK → persons.id (CASCADE), NOT NULL | |
| `clan_id` | UUID | FK → clans.id (CASCADE), NOT NULL | |
| `role` | VARCHAR(20) | DEFAULT 'blood' | blood, spouse, adopted |
| `generation` | SMALLINT | | Đời thứ mấy — relative to this clan |
| `is_founder` | BOOLEAN | DEFAULT false | Thuỷ tổ |
| `joined_at` | TIMESTAMPTZ | | |
| `created_at` | TIMESTAMPTZ | NOT NULL, auto | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, auto | |

**Constraints:** `UNIQUE(person_id, clan_id)` — a person can only have one membership per clan.

**Why `generation` is here, not on `persons`:** The same person can be generation 5 in clan Trần but generation 1 (founder) if they start a new branch/clan. Generation is relative to the clan context.

### `marriages`

Global edge linking two persons. Supports polygamy, divorce, remarriage.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `person1_id` | UUID | FK → persons.id (CASCADE), NOT NULL | |
| `person2_id` | UUID | FK → persons.id (CASCADE), NOT NULL | |
| `created_by_clan_id` | UUID | FK → clans.id (CASCADE), NOT NULL | Clan that manages this record |
| `marriage_date` | DATE | | Ngày cưới |
| `divorce_date` | DATE | | Ngày ly hôn |
| `marriage_place` | VARCHAR(255) | | Nơi kết hôn |
| `status` | VARCHAR(20) | DEFAULT 'married' | married, divorced, widowed, separated |
| `spouse_order` | SMALLINT | | Vợ cả=1, vợ hai=2, vợ ba=3... |
| `notes` | TEXT | | |
| `created_by` | UUID | NOT NULL | User who created |
| `created_at` | TIMESTAMPTZ | NOT NULL, auto | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, auto | |

**`created_by_clan_id` — not `clan_id`:** The marriage is a global fact. The clan only manages write access. RLS policy: `allow write if created_by_clan_id = current_clan`. Both clans can read.

**Real-world cases handled:**

| Case | Model |
|------|-------|
| Cụ ông lấy 3 bà | 3 Marriage rows: A-B, A-C, A-D with `spouse_order` 1, 2, 3 |
| Ly hôn | `status='divorced'`, `divorce_date` set |
| Tái hôn | New Marriage row with new spouse |
| Goá | `status='widowed'` |
| Con ngoài giá thú | No Marriage needed — only ParentChild edges |

### `parent_child`

Global edge linking parent to child. Supports biological, adopted, step, foster.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `parent_id` | UUID | FK → persons.id (CASCADE), NOT NULL | |
| `child_id` | UUID | FK → persons.id (CASCADE), NOT NULL | |
| `created_by_clan_id` | UUID | FK → clans.id (CASCADE), NOT NULL | Clan that manages this record |
| `relationship_type` | VARCHAR(20) | DEFAULT 'biological' | biological, adopted, step, foster |
| `notes` | TEXT | | |
| `created_by` | UUID | NOT NULL | |
| `created_at` | TIMESTAMPTZ | NOT NULL, auto | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, auto | |

**Every child has up to 2 ParentChild rows** (one per parent). This naturally handles:

| Case | Model |
|------|-------|
| Con ruột (A + B → child) | `ParentChild(A→child, bio)` + `ParentChild(B→child, bio)` |
| Con nuôi | `ParentChild(A→child, adopted)` — UI renders as dashed line |
| Con riêng (step) | `ParentChild(A→child, step)` |
| Con ngoài giá thú (A + C → child, but A married B) | `ParentChild(A→child, bio)` + `ParentChild(C→child, bio)`, no Marriage A-C needed |

### `user_clan_roles`

Maps users to clans with RBAC roles. A user may belong to **multiple clans** — each with an independent role. The active clan is selected at runtime via the `X-Current-Clan-Id` header.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `clan_id` | UUID | FK → clans.id (CASCADE), NOT NULL | |
| `user_id` | UUID | FK → user_profiles.id (CASCADE), NOT NULL, indexed | |
| `person_id` | UUID | FK → persons.id (SET NULL) | Links user account to their person record |
| `role` | VARCHAR(20) | DEFAULT 'viewer' | admin, editor, viewer |
| `is_approved` | BOOLEAN | DEFAULT false | Pending approval by admin |
| `approved_by` | UUID | | Admin who approved |
| `approved_at` | TIMESTAMPTZ | | |
| `invited_by` | UUID | | User who sent the invite |
| `created_at` | TIMESTAMPTZ | NOT NULL, auto | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, auto | |

**Constraints:** `UNIQUE(user_id, clan_id)` — one role per user per clan.

**Role hierarchy:** `viewer` < `editor` < `admin`. Super admin is checked via `user_profiles.platform_role`.

### `change_requests`

Configurable cross-approval workflow. When `clan_settings.approval_config` requires approval for an action, changes go through this queue instead of being applied directly.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `clan_id` | UUID | FK → clans.id (CASCADE), NOT NULL | |
| `requester_id` | UUID | NOT NULL | User who proposed the change |
| `action` | VARCHAR(20) | NOT NULL | create, update, delete |
| `resource_type` | VARCHAR(50) | NOT NULL | person, marriage, parent_child, event, document |
| `resource_id` | UUID | | NULL for create; existing id for update/delete |
| `payload` | JSONB | | The proposed data |
| `status` | VARCHAR(20) | DEFAULT 'pending' | pending, approved, rejected |
| `reviewed_by` | UUID | | Admin who approved/rejected |
| `reviewed_at` | TIMESTAMPTZ | | |
| `review_notes` | TEXT | | Reviewer comments |
| `created_at` | TIMESTAMPTZ | NOT NULL, auto | |

**Workflow:** Editor creates change_request → Different admin reviews (cross-approval to prevent errors) → System applies the change on approval.

### `clan_settings`

Per-clan configuration. One row per clan (enforced by `UNIQUE(clan_id)`). Created automatically when a new clan is provisioned.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `clan_id` | UUID | FK → clans.id (CASCADE), UNIQUE, NOT NULL | One settings row per clan |
| `approval_config` | JSONB | | Configurable approval workflow |
| `default_language` | VARCHAR(10) | DEFAULT 'vi' | Default UI language for clan members |
| `tree_display_mode` | VARCHAR(20) | DEFAULT 'vertical' | `vertical` or `horizontal` tree rendering |
| `allow_public_tree` | BOOLEAN | DEFAULT false | Whether the family tree is publicly viewable |
| `notification_defaults` | JSONB | | Default notification settings for new members |
| `privacy_level` | VARCHAR(20) | DEFAULT 'clan_members' | `private`, `clan_members`, or `public` |
| `max_upload_size_mb` | SMALLINT | DEFAULT 10 | Max file upload size in MB |
| `created_at` | TIMESTAMPTZ | NOT NULL, auto | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, auto | |

**`approval_config` JSONB structure:**

```json
{
  "require_approval": {
    "person_create": true,
    "person_update": false,
    "person_delete": true,
    "marriage_create": true,
    "marriage_delete": true,
    "parent_child_create": true,
    "parent_child_delete": true
  },
  "auto_approve_roles": ["admin"]
}
```

**`notification_defaults` JSONB structure:**

```json
{
  "notify_days_before": 7,
  "event_types": ["death_anniversary", "birthday", "clan_ceremony"]
}
```

### `clan_invitations`

Tracks pending invitations to join a clan. Supports secure invite links with expiration.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `clan_id` | UUID | FK → clans.id (CASCADE), NOT NULL | |
| `email` | VARCHAR(255) | NOT NULL | Invited email address |
| `role` | VARCHAR(20) | DEFAULT 'viewer' | Role assigned upon acceptance |
| `invited_by` | UUID | NOT NULL | Admin who created the invite |
| `token` | VARCHAR(255) | UNIQUE, NOT NULL | Secure invite token for the link |
| `expires_at` | TIMESTAMPTZ | NOT NULL | Invitation expiry |
| `accepted_at` | TIMESTAMPTZ | | NULL = still pending |
| `created_at` | TIMESTAMPTZ | NOT NULL, auto | |

**Index:** `(clan_id, email)` for fast lookup of pending invitations per clan.

### `events`

Family events and milestones. Clan-scoped (uses `ClanScopedMixin`).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `clan_id` | UUID | FK → clans.id (CASCADE), NOT NULL | |
| `person_id` | UUID | FK → persons.id (CASCADE) | Nullable — clan-wide events have no person |
| `event_type` | VARCHAR(30) | NOT NULL | death_anniversary, birthday, wedding_anniversary, clan_ceremony, custom |
| `title` | VARCHAR(255) | NOT NULL | |
| `description` | TEXT | | |
| `event_date` | DATE | NOT NULL | |
| `is_lunar_calendar` | BOOLEAN | DEFAULT false | |
| `is_recurring` | BOOLEAN | DEFAULT true | |
| `notify_days_before` | SMALLINT | DEFAULT 7 | |
| `created_by` | UUID | NOT NULL | |
| `created_at` | TIMESTAMPTZ | NOT NULL, auto | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, auto | |

### `documents`

Uploaded files (photos, certificates, audio/video). Clan-scoped.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `clan_id` | UUID | FK → clans.id (CASCADE), NOT NULL | |
| `person_id` | UUID | FK → persons.id (SET NULL) | |
| `title` | VARCHAR(255) | NOT NULL | |
| `description` | TEXT | | |
| `document_type` | VARCHAR(20) | NOT NULL | photo, id_document, certificate, audio, video, other |
| `storage_path` | VARCHAR(500) | UNIQUE, NOT NULL | Supabase Storage path |
| `file_size_bytes` | BIGINT | | |
| `mime_type` | VARCHAR(100) | | |
| `original_filename` | VARCHAR(255) | | |
| `taken_date` | DATE | | |
| `taken_place` | VARCHAR(255) | | |
| `is_avatar` | BOOLEAN | DEFAULT false | |
| `created_by` | UUID | NOT NULL | |
| `created_at` | TIMESTAMPTZ | NOT NULL, auto | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, auto | |

### `audit_logs`

Immutable log of all write actions. Not clan-scoped (uses own timestamps).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `clan_id` | UUID | | Nullable for platform-level actions |
| `actor_id` | UUID | NOT NULL | |
| `actor_role` | VARCHAR(50) | NOT NULL | |
| `action` | VARCHAR(100) | NOT NULL | |
| `resource_type` | VARCHAR(50) | NOT NULL | |
| `resource_id` | UUID | | |
| `old_value` | JSONB | | Snapshot before change |
| `new_value` | JSONB | | Snapshot after change |
| `ip_address` | INET | | |
| `user_agent` | VARCHAR(500) | | |
| `created_at` | TIMESTAMPTZ | NOT NULL, auto | |

### `notification_log`

Tracks push notification delivery. FCM tokens are now stored in `user_devices` (not per-notification).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `clan_id` | UUID | FK → clans.id (CASCADE), NOT NULL | |
| `event_id` | UUID | FK → events.id (SET NULL) | |
| `user_id` | UUID | NOT NULL | |
| `notification_type` | VARCHAR(50) | NOT NULL | |
| `title` | VARCHAR(255) | NOT NULL | |
| `body` | TEXT | NOT NULL | |
| `status` | VARCHAR(20) | DEFAULT 'pending' | |
| `sent_at` | TIMESTAMPTZ | | |
| `error_message` | TEXT | | |
| `created_at` | TIMESTAMPTZ | NOT NULL, auto | |

---

## Indexes

### Recommended indexes for common query patterns

```sql
-- Person lookups within a clan (the most common query)
CREATE INDEX idx_clan_memberships_clan_id ON clan_memberships(clan_id);
CREATE INDEX idx_clan_memberships_person_id ON clan_memberships(person_id);

-- Tree traversal: find all children of a parent
CREATE INDEX idx_parent_child_parent_id ON parent_child(parent_id);
CREATE INDEX idx_parent_child_child_id ON parent_child(child_id);
CREATE INDEX idx_parent_child_clan ON parent_child(created_by_clan_id);

-- Marriage lookups
CREATE INDEX idx_marriages_person1 ON marriages(person1_id);
CREATE INDEX idx_marriages_person2 ON marriages(person2_id);
CREATE INDEX idx_marriages_clan ON marriages(created_by_clan_id);

-- Person origin clan
CREATE INDEX idx_persons_origin_clan ON persons(origin_clan_id);

-- User role lookups
CREATE INDEX idx_user_clan_roles_user ON user_clan_roles(user_id);
CREATE INDEX idx_user_clan_roles_clan ON user_clan_roles(clan_id);

-- Events by clan and person
CREATE INDEX idx_events_clan ON events(clan_id);
CREATE INDEX idx_events_person ON events(person_id);
CREATE INDEX idx_events_date ON events(event_date);

-- Documents by clan and person
CREATE INDEX idx_documents_clan ON documents(clan_id);
CREATE INDEX idx_documents_person ON documents(person_id);

-- Change requests queue
CREATE INDEX idx_change_requests_clan_status ON change_requests(clan_id, status);

-- Audit log lookups
CREATE INDEX idx_audit_logs_clan ON audit_logs(clan_id);
CREATE INDEX idx_audit_logs_actor ON audit_logs(actor_id);
CREATE INDEX idx_audit_logs_resource ON audit_logs(resource_type, resource_id);

-- Notifications
CREATE INDEX idx_notification_log_clan ON notification_log(clan_id);
CREATE INDEX idx_notification_log_event ON notification_log(event_id);

-- User devices
CREATE INDEX ix_user_devices_user_id ON user_devices(user_id);

-- Clan invitations
CREATE INDEX ix_clan_invitations_clan_id ON clan_invitations(clan_id);
CREATE INDEX ix_clan_invitations_clan_email ON clan_invitations(clan_id, email);
```

---

## RLS Policies

### Read access

```sql
-- Persons: visible if person is in user's current clan
CREATE POLICY persons_select ON persons FOR SELECT USING (
  EXISTS (
    SELECT 1 FROM clan_memberships cm
    WHERE cm.person_id = persons.id
    AND cm.clan_id = current_setting('app.current_clan_id')::uuid
  )
);

-- Marriages: visible if either person is in user's current clan
CREATE POLICY marriages_select ON marriages FOR SELECT USING (
  EXISTS (
    SELECT 1 FROM clan_memberships cm
    WHERE (cm.person_id = marriages.person1_id OR cm.person_id = marriages.person2_id)
    AND cm.clan_id = current_setting('app.current_clan_id')::uuid
  )
);

-- ParentChild: visible if either person is in user's current clan
CREATE POLICY parent_child_select ON parent_child FOR SELECT USING (
  EXISTS (
    SELECT 1 FROM clan_memberships cm
    WHERE (cm.person_id = parent_child.parent_id OR cm.person_id = parent_child.child_id)
    AND cm.clan_id = current_setting('app.current_clan_id')::uuid
  )
);
```

### Write access

```sql
-- Marriages: writable only by the managing clan
CREATE POLICY marriages_write ON marriages FOR ALL USING (
  created_by_clan_id = current_setting('app.current_clan_id')::uuid
);

-- ParentChild: writable only by the managing clan
CREATE POLICY parent_child_write ON parent_child FOR ALL USING (
  created_by_clan_id = current_setting('app.current_clan_id')::uuid
);

-- Clan-scoped tables (events, documents): standard clan_id check
CREATE POLICY events_access ON events FOR ALL USING (
  clan_id = current_setting('app.current_clan_id')::uuid
);
CREATE POLICY documents_access ON documents FOR ALL USING (
  clan_id = current_setting('app.current_clan_id')::uuid
);
```

---

## Storage

Single shared Supabase Storage bucket with path-based clan isolation:

```
family-roots-files/
├── clans/{clan_id}/persons/{person_id}/avatar.jpg
├── clans/{clan_id}/persons/{person_id}/photos/
├── clans/{clan_id}/documents/
└── clans/{clan_id}/events/
```

RLS policy on `storage.objects` ensures users can only access files under their clan's path.

---

## Migrations

Managed via Alembic. Migrations live in `backend/migrations/versions/` and operate on the single `public` schema. No multi-schema complexity.
