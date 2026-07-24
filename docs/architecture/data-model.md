# FamilyRoots Database Schema

## Overview

FamilyRoots uses **PostgreSQL 16+** with a single `public` schema. The core data model treats genealogy as a **graph**, not a tree:

- **Node** = `Person` (global entity, independent of any clan)
- **Edge** = `Marriage` | `ParentChild` (global relationships between persons)
- **View** = `ClanMembership` (M:N link filtering persons into clan views)

Data isolation between clans is enforced **in the application/repository layer**
(the active mechanism; DB-level RLS is a deferred layer-2 — see `multi-tenancy.md`):
- `ClanMembership` join scopes person visibility per clan (read)
- `created_by_clan_id` on edges scopes both reads and writes of relationships
- writes validate that referenced persons belong to the acting clan

### Architecture Principle

```text
Person ──────── exists globally (no clan_id)
ClanMembership ── links Person ↔ Clan (M:N, with role + generation)
Marriage ──────── global edge (person1 ↔ person2, created_by_clan_id for write RLS)
ParentChild ───── global edge (parent → child, created_by_clan_id for write RLS)
```

**Example:**
"Đào Thị B" (origin clan Đào) marries "Trần Văn A" (clan Trần). The system handles this with:
- **Two** distinct `Person` records (no duplication).
- A `ClanMembership(B → Trần, role=spouse)`.
- A `Marriage(A ↔ B, created_by_clan_id=Trần)`.
- If clan Đào also uses the system: `ClanMembership(A → Đào, role=spouse)`.

> **💡 Note (VN) - Global Person Architecture:** 
> Hệ thống được thiết kế theo mô hình **Global Person (Nhân vật Toàn cục)**. Thay vì mỗi dòng họ có một bản ghi riêng cho cùng một người (dễ dẫn tới rác dữ liệu ở các họ có liên hôn), một người chỉ tồn tại duy nhất 1 lần trên toàn hệ thống. Các dòng họ quản lý thành viên thông qua `clan_memberships`. Các mối quan hệ (Cưới hỏi, Cha con) là liên kết toàn cầu nhưng được kiểm soát quyền "Write" bởi dòng họ tạo ra nó thông qua `created_by_clan_id`.

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
        uuid created_by_clan_id FK "nullable - reference to creator clan"
        varchar full_name
        varchar birth_name
        varchar courtesy_name
        varchar posthumous_name
        varchar alias_name
        varchar gender
        date birth_date
        varchar birth_date_precision
        varchar birth_date_display
        date death_date
        varchar death_date_precision
        varchar death_date_display
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
        integer version "OCC (ADR-017), default 1"
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
        uuid person_id FK "nullable UK - canonical link to person"
        timestamptz last_login_at
        timestamptz created_at
        timestamptz updated_at
    }

    user_fcm_tokens {
        uuid id PK
        uuid user_id FK
        text token UK
        varchar device_platform "ios | android | web"
        timestamptz created_at
        timestamptz updated_at
    }

    clan_memberships {
        uuid id PK
        uuid person_id FK
        uuid clan_id FK
        varchar role "blood | spouse | adopted"
        smallint generation "relative to clan"
        boolean is_founder
        uuid branch_id FK "nullable - chi/phái"
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
        smallint spouse_order "1st wife, 2nd wife... (from person1)"
        text notes
        uuid created_by
        uuid updated_by
        boolean is_deleted
        timestamptz deleted_at
        uuid deleted_by
        timestamptz created_at
        timestamptz updated_at
        integer version "OCC (ADR-017), default 1"
    }

    parent_child {
        uuid id PK
        uuid parent_id FK
        uuid child_id FK
        uuid created_by_clan_id FK "managing clan - write RLS"
        varchar relationship_type "biological | adopted | step | foster"
        smallint birth_order "con cả=1, con thứ=2..."
        text notes
        uuid created_by
        uuid updated_by
        boolean is_deleted
        timestamptz deleted_at
        uuid deleted_by
        timestamptz created_at
        timestamptz updated_at
        integer version "OCC (ADR-017), default 1"
    }

    user_clan_roles {
        uuid id PK
        uuid clan_id FK
        uuid user_id FK "FK to user_profiles"
        varchar role "admin | editor | viewer"
        boolean is_approved
        uuid approved_by
        timestamptz approved_at
        uuid invited_by
        timestamptz created_at
        timestamptz updated_at
    }

    identity_claims {
        uuid id PK
        uuid user_id FK
        uuid person_id FK
        varchar status "PENDING | APPROVED | REJECTED | CANCELLED"
        text requester_note
        text reviewer_note
        uuid reviewed_by
        timestamptz reviewed_at
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
        varchar resource_type
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

    branches {
        uuid id PK
        uuid clan_id FK
        varchar name "Chi Hai, Phái Bắc..."
        text description
        uuid founder_person_id FK "nullable - ông tổ chi"
        uuid parent_branch_id FK "nullable - self-ref"
        smallint branch_order "thứ tự hiển thị"
        timestamptz created_at
        timestamptz updated_at
    }

    %% ── Relationships ──
    user_profiles ||--o{ user_clan_roles : "has clan roles"
    user_profiles ||--o{ user_fcm_tokens : "has FCM tokens"
    user_profiles ||--o| identity_claims : "submits"
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
    clans ||--o{ branches : "has branches"
    persons ||--o{ clan_memberships : "belongs to clans"
    persons ||--o{ marriages : "person1"
    persons ||--o{ marriages : "person2"
    persons ||--o{ parent_child : "as parent"
    persons ||--o{ parent_child : "as child"
    persons ||--o{ events : "about"
    persons ||--o{ documents : "attached"
    persons ||--o{ identity_claims : "claimed by"
    persons |o--o| user_profiles : "canonical user link"
    persons }o--o| clans : "created_by_clan"
    events ||--o{ notification_log : "triggers"
    branches ||--o{ clan_memberships : "has members"
    branches |o--o| persons : "founder"
```

---

## Table Details

### `clans`
Central registry of family clans (dòng họ). Each clan is a tenant.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `name` | VARCHAR(255) | NOT NULL | Display name (e.g. "Họ Trần Văn") / Tên dòng họ |
| `slug` | VARCHAR(100) | UNIQUE, NOT NULL | URL-safe identifier / Đường dẫn thân thiện |
| `description` | TEXT | | Mô tả / Lịch sử dòng họ |
| `origin_place` | VARCHAR(255) | | Quê quán gốc |
| `founded_year` | SMALLINT | | Năm thành lập |
| `avatar_url` | VARCHAR(500) | | Logo / Gia huy dòng họ |
| `motto` | TEXT | | Phương châm gia tộc / Khẩu hiệu |
| `ancestral_hall_location` | VARCHAR(500) | | Địa chỉ nhà thờ tổ |
| `clan_rules` | TEXT | | Gia huấn / Quy định của họ |
| `is_active` | BOOLEAN | DEFAULT true | Trạng thái hoạt động |
| `created_at` | TIMESTAMPTZ | NOT NULL, auto | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, auto | |

### `user_profiles`
Local cache of Supabase Auth user data. Mapped 1:1 to a real-world Identity via `person_id`.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | Supabase `auth.users.id` |
| `email` | VARCHAR(255) | UNIQUE, NOT NULL | Synced from JWT |
| `display_name` | VARCHAR(255) | | Tên hiển thị |
| `avatar_url` | VARCHAR(500) | | Ảnh đại diện tài khoản |
| `language` | VARCHAR(10) | DEFAULT 'vi' | Ngôn ngữ giao diện |
| `timezone` | VARCHAR(50) | DEFAULT 'Asia/Ho_Chi_Minh' | Múi giờ |
| `is_active` | BOOLEAN | DEFAULT true | Tài khoản còn hoạt động không |
| `platform_role` | VARCHAR(50) | DEFAULT 'user' | Quyền trên toàn hệ thống (`user` | `super_admin`) |
| `person_id` | UUID | FK → persons.id (SET NULL) | UNIQUE. Canonical link to person / Link định danh với nhân vật trong gia phả. |
| `last_login_at` | TIMESTAMPTZ | | Lần đăng nhập cuối |
| `created_at` | TIMESTAMPTZ | NOT NULL, auto | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, auto | |

> **💡 Note (VN) - User vs Person Profile:**
> Tại sao KHÔNG để `clan_id` ở `user_profile`? Một user có thể tham gia nhiều gia phả (nội, ngoại, vợ). Việc phân quyền thuộc về bảng vòng `user_clan_roles`. Giá trị `person_id` ở đây là liên kết hệ thống: Nó ánh xạ User (tài khoản số) tới Person (nhân vật lịch sử). 

### `identity_claims`
Workflow queue for users claiming an identity in the family tree.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `user_id` | UUID | FK → user_profiles.id | Requester / Người gửi yêu cầu |
| `person_id` | UUID | FK → persons.id | Identity to claim / Nhân vật muốn nhận diện |
| `status` | VARCHAR | | PENDING, APPROVED, REJECTED, CANCELLED |
| `requester_note` | TEXT | | User justification / Lý do từ phía user (ví dụ: tôi là con ông B) |
| `reviewer_note` | TEXT | | Admin feedback / Lý do duyệt/từ chối của admin |
| `reviewed_by` | UUID | | Admin ID / Người duyệt |
| `reviewed_at` | TIMESTAMPTZ | | |
| `created_at` | TIMESTAMPTZ | NOT NULL | |
| `updated_at` | TIMESTAMPTZ | NOT NULL | |

> **💡 Note (VN) - Ngăn Spam & Race Condition:** 
> Hệ thống chặn spam bằng Constraint `UNIQUE(user_id) WHERE status = 'PENDING'` (một user chỉ có 1 request đang chờ). Khi claim được Approve, hệ thống gán `user_profile.person_id` và tự động Reject toàn bộ các claims Pending khác vào cùng nhân vật này, ngăn Race Condition.

### `persons`
Global person entity — independent of any clan. A person exists once and can appear in multiple clans via `clan_memberships`.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `created_by_clan_id` | UUID | FK → clans.id | Creator clan / Dòng họ Owner tạo ra bản ghi này |
| `full_name` | VARCHAR(255) | NOT NULL | Tên đầy đủ |
| `birth_name` | VARCHAR(255) | | Tên khai sinh |
| `courtesy_name` | VARCHAR(255) | | Tên tự / Tên chữ |
| `posthumous_name` | VARCHAR(255) | | Tên huý / Tên thụy (dùng trong cúng giỗ) |
| `alias_name` | VARCHAR(255) | | Biệt danh / Tên thường gọi |
| `gender` | VARCHAR(20) | NOT NULL, DEFAULT 'unknown' | Giới tính (male, female, unknown) |
| `birth_date` | DATE | | Ngày sinh (Dương lịch - canonical, điểm mốc tốt nhất) |
| `birth_date_precision` | VARCHAR(10) | NOT NULL, DEFAULT 'exact' | Độ chính xác: exact \| year \| month \| circa \| unknown |
| `birth_date_display` | VARCHAR(100) | | Text hiển thị khi precision != exact (vd "khoảng 1750") |
| `death_date` | DATE | | Ngày mất (Dương lịch) |
| `death_date_precision` | VARCHAR(10) | NOT NULL, DEFAULT 'exact' | Như trên |
| `death_date_display` | VARCHAR(100) | | Như trên |
| `lunar_birth_date` | VARCHAR(30) | | Ngày sinh Âm lịch (chỉ để display/lưu text) |
| `lunar_death_date` | VARCHAR(30) | | Ngày mất Âm lịch (chỉ để display/lưu text) |

> **💡 HistoricalDate (2026-07-11, migrations 012→014):** các cột `*_date_approx`
> (boolean) đã bị **DROP** — `precision` thay thế (backfill: approx→`circa`,
> có date→`exact`, null→`unknown`). API serialize mỗi ngày thành object
> `{date, precision, display, lunar}` (xem `docs/contracts/README.md` và ADR-011).
> `events` có `event_date_precision/_display`; `marriages` có
> `marriage_date_precision/_display` + `divorce_date_precision/_display` (migration 012).
| `birth_place` | VARCHAR(255) | | Nơi sinh |
| `death_place` | VARCHAR(255) | | Nơi mất |
| `burial_place` | VARCHAR(255) | | Nơi an táng |
| `tomb_location` | VARCHAR(500) | | Tọa độ/Vị trí phần mộ hiện tại |
| `residence_place` | VARCHAR(255) | | Địa chỉ chỗ ở thường trú |
| `religion` | VARCHAR(100) | | Tôn giáo |
| `nationality` | VARCHAR(100) | DEFAULT 'VN' | Quốc tịch |
| `occupation` | VARCHAR(255) | | Nghề nghiệp hiện tại / lúc sinh thời |
| `education_level` | VARCHAR(255) | | Trình độ học vấn |
| `title_rank` | VARCHAR(255) | | Chức danh, phẩm hàm, tước vị |
| `phone` | VARCHAR(50) | | Số điện thoại liên hệ |
| `email` | VARCHAR(255) | | Email liên hệ |
| `biography` | TEXT | | Tiểu sử / Câu chuyện cuộc đời |
| `avatar_url` | VARCHAR(500) | | Link ảnh đại diện chân dung |
| `notes` | TEXT | | Ghi chú nội bộ |
| `is_deleted` | BOOLEAN | DEFAULT false | Soft delete / Đã xoá mềm |
| `deleted_at` | TIMESTAMPTZ | | |
| `deleted_by` | UUID | | |
| `created_by` | UUID | NOT NULL | Người tạo bản ghi |
| `updated_by` | UUID | | |
| `created_at` | TIMESTAMPTZ | NOT NULL, auto | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, auto | |
| `version` | INTEGER | NOT NULL, DEFAULT 1 | Optimistic concurrency (ADR-017, migration `015_data_integrity`) — bumped by 1 on every write (including delete/restore); `PATCH` must send the matching `expected_version` or gets 409 `stale_write` |

> **💡 Note (VN) - Data Ownership:**
> Cột `created_by_clan_id` giúp xác định ai là "Chủ Thực Sự" (Owner) của bản ghi này. Dòng họ Owner có quyển Edit lớn nhất, trong khi các dòng họ khác chỉ có thể link (tạo Reference) hoặc Submit các Change Request xuyên dòng họ.

### `clan_memberships`
M:N link between persons and clans. Determines which persons appear in which clan's tree.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `person_id` | UUID | FK → persons.id (CASCADE), NOT NULL | Thực thể Nhân vật |
| `clan_id` | UUID | FK → clans.id (RESTRICT), NOT NULL | Thuộc Dòng họ nào |
| `role` | VARCHAR(20) | DEFAULT 'blood' | Vai trò huyết thống: blood (rút ruột), spouse (dâu rể), adopted (con nuôi) |
| `generation` | SMALLINT | | Đời thứ mấy — relative to this clan |
| `is_founder` | BOOLEAN | DEFAULT false | Là Thuỷ tổ (người sáng lập dòng họ này) |
| `branch_id` | UUID | FK → branches.id (SET NULL), nullable | Thuộc chi/phái nào trong họ |
| `joined_at` | TIMESTAMPTZ | | Thời điểm gắn vào họ |
| `created_at` | TIMESTAMPTZ | NOT NULL, auto | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, auto | |

> **💡 Note (VN) - Thế Thứ Tương Đối:**
> Tại sao `generation` (đời thứ mấy) nằm ở đây thay vì ở `persons`? Vì ở họ của mẹ, người này có thể thuộc đời thứ 5, nhưng khi họ lập ra một chi báo/dòng họ mới của bản thân, họ lại là đời số 1 (Thuỷ tổ) của dòng họ đó!

> **Note — exactly one live founder per clan (ADR-026):** partial unique index
> `uq_clan_memberships_one_founder (clan_id) WHERE is_founder = true`
> (migration `023_one_founder_per_clan`) enforces at most one `is_founder = true`
> row per clan at the DB level. Only write path is `PUT /clans/me/founder`
> (admin-only) — see [rest-clans-api.md](../contracts/rest-clans-api.md#founder-designation-thủy-tổ).
> `generation` on this table is display-only legacy storage — every tree/export
> read path computes đời from the graph instead (`clan_memberships.generation`
> is deprecated as a display source, ADR-012); it is not kept in sync with the
> computed value.

### `marriages`
Global edge linking two persons. Supports polygamy, divorce, remarriage.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `person1_id` | UUID | FK → persons.id (RESTRICT), NOT NULL | Sinh ra từ gốc dòng họ chính |
| `person2_id` | UUID | FK → persons.id (RESTRICT), NOT NULL | Dâu / Rể |
| `created_by_clan_id` | UUID | FK → clans.id (RESTRICT), NOT NULL | Clan managing this record / Dòng họ nắm quyền Write RLS |
| `marriage_date` | DATE | | Ngày cưới |
| `marriage_date_precision` | VARCHAR(10) | NOT NULL, DEFAULT 'exact' | exact \| year \| month \| circa \| unknown (migration 012) |
| `marriage_date_display` | VARCHAR(100) | | Text hiển thị khi precision != exact |
| `divorce_date` | DATE | | Ngày ly dị |
| `divorce_date_precision` | VARCHAR(10) | NOT NULL, DEFAULT 'exact' | Như trên |
| `divorce_date_display` | VARCHAR(100) | | Như trên |
| `marriage_place` | VARCHAR(255) | | Nơi tổ chức lễ cưới |
| `status` | VARCHAR(20) | DEFAULT 'married' | Tình trạng: married, divorced, widowed (góa), separated (ly thân) |
| `spouse_order` | SMALLINT | | Thứ tự hôn nhân (Vợ cả=1, vợ hai=2...) |
| `notes` | TEXT | | Ghi chú |
| `created_by` | UUID | NOT NULL | |
| `updated_by` | UUID | | |
| `is_deleted` | BOOLEAN | DEFAULT false | |
| `deleted_at` | TIMESTAMPTZ | | |
| `deleted_by` | UUID | | |
| `created_at` | TIMESTAMPTZ | NOT NULL, auto | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, auto | |
| `version` | INTEGER | NOT NULL, DEFAULT 1 | Optimistic concurrency (ADR-017, migration `015_data_integrity`) — bumped by 1 on every write (including soft-delete); `PATCH` must send the matching `expected_version` or gets 409 `stale_write` |

### `parent_child`
Global edge linking parent to child. Supports biological, adopted, step, foster.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `parent_id` | UUID | FK → persons.id (RESTRICT), NOT NULL | Cha / Mẹ |
| `child_id` | UUID | FK → persons.id (RESTRICT), NOT NULL | Con |
| `created_by_clan_id` | UUID | FK → clans.id (RESTRICT), NOT NULL | Clan managing this record / Dòng họ nắm quyền Write RLS |
| `relationship_type` | VARCHAR(20) | DEFAULT 'biological' | Loại quan hệ: biological (con đẻ), adopted (con nuôi), step (con riêng của vợ/chồng), foster (con đỡ đầu) |
| `birth_order` | SMALLINT | | Thứ tự sinh (con cả=1, con thứ=2...) |
| `notes` | TEXT | | Ghi chú |
| `created_by` | UUID | NOT NULL | |
| `updated_by` | UUID | | |
| `is_deleted` | BOOLEAN | DEFAULT false | |
| `deleted_at` | TIMESTAMPTZ | | |
| `deleted_by` | UUID | | |
| `created_at` | TIMESTAMPTZ | NOT NULL, auto | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, auto | |
| `version` | INTEGER | NOT NULL, DEFAULT 1 | Optimistic concurrency (ADR-017, migration `015_data_integrity`) — bumped by 1 on every write (including soft-delete); `PATCH` must send the matching `expected_version` or gets 409 `stale_write` |

> **💡 Note (VN) - Edge uniqueness là PER-CLAN, widened to match app invariants
> (migration 007, widened 022 — ADR-025):**
> Unique index của `marriages` và `parent_child` bao gồm `created_by_clan_id`:
> `idx_marriages_unique_pair (created_by_clan_id, LEAST(person1_id,person2_id),
> GREATEST(person1_id,person2_id)) WHERE status <> 'divorced' AND is_deleted =
> false` — tối đa **một** cuộc hôn nhân còn sống, không phải `divorced`, cho mỗi
> cặp/clan (khớp `has_active_marriage`, không chỉ riêng `status='married'` như
> trước 022) — và `idx_parent_child_unique_edge (created_by_clan_id, parent_id,
> child_id) WHERE is_deleted = false` — tối đa **một** cạnh còn sống cho mỗi
> (parent, child)/clan, bất kể `relationship_type` (trước 022, `relationship_type`
> nằm trong khóa nên `biological` + `adopted` đồng thời cho cùng một cặp vẫn lọt
> qua). Nghĩa là **mỗi clan được ghi cạnh của riêng mình** cho person dùng
> chung — Họ Nguyễn đã ghi "A là con B" thì Họ Lê **vẫn** ghi được bản của họ; chống
> trùng chỉ áp dụng bên trong một clan. Đây là nền của cơ chế clan-scoped edges
> (mỗi cây chỉ đọc cạnh do clan mình tạo).

> **💡 Note (VN) - `spouse_order` uniqueness là two-sided per-person, index vẫn
> person1-keyed (migration `015_data_integrity`; app-layer widened, ADR-029,
> không migration mới):**
> Partial unique index `uq_marriages_spouse_order (created_by_clan_id, person1_id,
> spouse_order) WHERE spouse_order IS NOT NULL AND is_deleted = false AND status <>
> 'divorced'` vẫn chỉ key trên `person1_id` — không đổi từ migration 015. Nhưng
> `person1_id`/`person2_id` là cặp **không thứ tự** (person nào cũng có thể nằm ở
> cột nào), nên validator tầng domain (`check_spouse_order` /
> `has_spouse_order_conflict`) đã **mở rộng hai chiều (ADR-029)**: kiểm tra CẢ
> `person1_id` lẫn `person2_id` của cả hai người tham gia, đảm bảo **không một
> người nào** (dù nằm ở cột nào) có hai cuộc hôn nhân active cùng `spouse_order`.
> Trước ADR-029, ghi đa thê theo chiều `(vợ hai, chồng)` thay vì `(chồng, vợ hai)`
> lọt qua check vì tra chỉ đúng cột `person1_id`. Active nghĩa là **bất kỳ status
> nào khác `divorced`** (married, widowed/góa, separated/ly thân đều tính), khớp
> với định nghĩa active của `has_active_marriage`; chỉ ly dị/xóa mềm thì không
> tính. Validator chặn trước ở tầng application (409
> `relationship.duplicate_spouse_order`); index (vẫn person1-keyed) chỉ là lớp
> chặn cuối cho race condition **cùng chiều** (raw SQL bypass → `23505` → 409) —
> một race giữa hai insert **khác chiều** cùng lúc không được index này chặn
> (residual đã ghi trong ADR-029, hiếm ở tốc độ chỉnh sửa gia phả của người
> dùng thật). Hệ quả được chấp nhận: một người không thể là vợ/chồng cùng thứ
> hạng (vd. vợ cả) trong hai cuộc hôn nhân active **đồng thời** — over-reject
> trường hợp hiếm đa phu (polyandry), chấp nhận theo mô hình đa thê (ADR-029).
> Migration có bước pre-check: nếu dữ liệu hiện có đã vi phạm, migration **fail
> rõ ràng** và liệt kê các dòng vi phạm — không tự động renumber lịch sử.

> **💡 Note (VN) - Xóa clan (`ON DELETE RESTRICT`, migration 010):** mọi FK
> trỏ về `clans.id` (memberships, marriages, parent_child, branches,
> invitations, settings, change_requests, events, documents, notification_log,
> user_clan_roles) dùng **RESTRICT** — một `DELETE FROM clans` thủ công sẽ fail
> rõ ràng thay vì cascade mất toàn bộ gia phả. Ngoại lệ giữ `SET NULL`:
> `persons.created_by_clan_id` (person được de-provenance, không bị hủy) và
> `audit_logs.clan_id` (audit được giữ lại). Không có luồng xóa clan trong app —
> clan chỉ suspend/reactivate.

> **💡 Note (VN) - Xóa person & cạnh mồ côi (`ON DELETE RESTRICT`):**
> FK `person1_id/person2_id` (marriages) và `parent_id/child_id` (parent_child) dùng
> **`RESTRICT`**, KHÔNG phải CASCADE — vì `persons` dùng **soft-delete**, không bao giờ
> hard-delete. Hệ quả: khi soft-delete một person, các cạnh của họ **không tự động ẩn**
> ở tầng dữ liệu (tree query đã lọc `is_deleted=false` nên không hiện trong cây, nhưng
> cạnh vẫn tồn tại). **Quyết định (2026-07-02):** khi soft-delete một person sẽ **ẩn
> luôn (soft-delete) các cạnh** của người đó — *hạng mục roadmap* (cần thiết kế cả logic
> `restore`: chỉ khôi phục cạnh đã bị ẩn bởi chính lần xóa person đó).

### `user_clan_roles`
Maps users to clans with RBAC roles.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `clan_id` | UUID | FK → clans.id (RESTRICT), NOT NULL | Thuộc dòng họ nào |
| `user_id` | UUID | FK → user_profiles.id (CASCADE), NOT NULL | Tài khoản User |
| `role` | VARCHAR(20) | DEFAULT 'viewer' | admin, editor, viewer |
| `is_approved` | BOOLEAN | DEFAULT false | Pending admin approval / Đã được admin duyệt chưa |
| `approved_by` | UUID | | Người duyệt |
| `approved_at` | TIMESTAMPTZ | | |
| `invited_by` | UUID | | Phân biệt tự xin vào (join request) hay được admin mời |
| `created_at` | TIMESTAMPTZ | NOT NULL, auto | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, auto | |

### `user_fcm_tokens`
Firebase Cloud Messaging tokens per device, for push notifications. This is the
table the runtime actually uses (migration `004_fcm_tokens`); the earlier
`user_devices` table was removed as an unused duplicate.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `user_id` | UUID | FK → user_profiles.id (CASCADE), NOT NULL | Tài khoản User |
| `token` | TEXT | UNIQUE, NOT NULL | Firebase token — `INSERT ... ON CONFLICT (token)`: re-register moves the token to the current user |
| `device_platform` | VARCHAR(20) | nullable | `ios`, `android`, `web` |
| `created_at` | TIMESTAMPTZ | NOT NULL, auto | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, auto | |

### `change_requests`
Configurable cross-approval workflow. Uses `clan_settings.approval_config`.

> ⚠️ **Status (2026-07-02) — dormant / not implemented.** The table + ORM model +
> Pydantic schema exist, but **no runtime code** references them (no domain context,
> handler, or route). This is a planned feature (cross-clan propose-and-approve)
> on the roadmap (D1).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `clan_id` | UUID | FK → clans.id (RESTRICT), NOT NULL | |
| `requester_id` | UUID | NOT NULL | User who proposed the change / Người đề xuất thay đổi |
| `action` | VARCHAR(20) | NOT NULL | create, update, delete |
| `resource_type` | VARCHAR(50) | NOT NULL | person, marriage, parent_child, event, document / Loại dữ liệu |
| `resource_id` | UUID | | NULL for create; existing id for update/delete |
| `payload` | JSONB | | The proposed data / Dữ liệu đề xuất (JSON) |
| `status` | VARCHAR(20) | DEFAULT 'pending' | pending, approved, rejected |
| `reviewed_by` | UUID | | Người duyệt / Admin thực hiện duyệt |
| `reviewed_at` | TIMESTAMPTZ | | |
| `review_notes` | TEXT | | Lý do từ chối/duyệt |
| `created_at` | TIMESTAMPTZ | NOT NULL, auto | |

### `branches`
Chi/phái/nhánh within a clan. Supports nested hierarchy.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `clan_id` | UUID | FK → clans.id (RESTRICT), NOT NULL | Thuộc dòng họ nào |
| `name` | VARCHAR(255) | NOT NULL | "Chi Hai", "Phái Bắc" / Tên đại diện nhánh |
| `description` | TEXT | | Mô tả |
| `founder_person_id` | UUID | FK → persons.id (SET NULL), nullable | Ông tổ chi này |
| `parent_branch_id` | UUID | FK → branches.id (SET NULL), nullable | Nhánh cha (tree structure) / Chi gốc chứa nhánh này |
| `branch_order` | SMALLINT | | Thứ tự hiển thị |
| `created_at` | TIMESTAMPTZ | NOT NULL, auto | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, auto | |

### `clan_settings`
Per-clan configuration. Auto-created with new clans.

> ⚠️ **Status (2026-07-02) — mostly not enforced yet.** Only the row/columns exist;
> the runtime does **not** read most knobs. In particular `max_upload_size_mb`
> (default 10) is **not** applied — the document domain hard-codes a **50 MB** limit,
> so the two disagree and must be reconciled when this is built. `privacy_level`,
> `allow_public_tree`, `tree_display_mode`, `approval_config`,
> `notification_defaults` are also inert. Roadmap item D3.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `clan_id` | UUID | FK → clans.id (RESTRICT), UNIQUE, NOT NULL | One settings row per clan |
| `approval_config` | JSONB | | Configurable approval workflow / Cấu hình duyệt dữ liệu (theo quyền hạn) |
| `default_language` | VARCHAR(10) | DEFAULT 'vi' | Default UI language for clan members |
| `tree_display_mode` | VARCHAR(20) | DEFAULT 'vertical' | `vertical` or `horizontal` tree rendering / Hiển thị cây dọc hay ngang |
| `allow_public_tree` | BOOLEAN | DEFAULT false | Whether the family tree is publicly viewable / Có cho phép public cây gia phả không |
| `notification_defaults` | JSONB | | Default notification settings for new members / Cấu hình thông báo mặc định cho member |
| `privacy_level` | VARCHAR(20) | DEFAULT 'clan_members' | `private`, `clan_members`, or `public` |
| `max_upload_size_mb` | SMALLINT | DEFAULT 10 | Max file upload size in MB / Dung lượng tối đa cho phép upload |
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
Tracks pending email invitations to join a clan.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `clan_id` | UUID | FK → clans.id (RESTRICT), NOT NULL | |
| `email` | VARCHAR(255) | NOT NULL | Invited email address / Email người được mời |
| `role` | VARCHAR(20) | DEFAULT 'viewer' | Role assigned upon acceptance / Vai trò (admin, editor, viewer) |
| `invited_by` | UUID | NOT NULL | Admin who created the invite / Admin gửi lời mời |
| `token` | VARCHAR(255) | UNIQUE, NOT NULL | Secure invite token for the link / Mã token trên URL thư mời |
| `expires_at` | TIMESTAMPTZ | NOT NULL | Invitation expiry / Hạn sử dụng lời mời |
| `accepted_at` | TIMESTAMPTZ | | NULL = still pending / Thời điểm chấp nhận |
| `created_at` | TIMESTAMPTZ | NOT NULL, auto | |

### `events`
Family events and milestones. Clan-scoped.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `clan_id` | UUID | FK → clans.id (RESTRICT), NOT NULL | |
| `person_id` | UUID | FK → persons.id (CASCADE) | Nullable — clan-wide events have no person / Sự kiện cá nhân hay dòng họ |
| `event_type` | VARCHAR(30) | NOT NULL | death_anniversary (giỗ), birthday (sinh nhật), wedding_anniversary, clan_ceremony (lễ họ), custom |
| `title` | VARCHAR(255) | NOT NULL | Tiêu đề sự kiện |
| `description` | TEXT | | Nội dung |
| `event_date` | DATE | NOT NULL | Ngày diễn ra |
| `event_date_precision` | VARCHAR(10) | NOT NULL, DEFAULT 'exact' | exact \| year \| month \| circa \| unknown (migration 012) |
| `event_date_display` | VARCHAR(100) | | Text hiển thị khi precision != exact |
| `is_lunar_calendar` | BOOLEAN | DEFAULT false | Tính theo âm lịch không? (điều khiển scheduler giỗ) |
| `is_recurring` | BOOLEAN | DEFAULT true | Lặp lại hằng năm? |
| `notify_days_before` | SMALLINT | DEFAULT 7 | Báo trước bao nhiêu ngày |
| `created_by` | UUID | NOT NULL | Người tạo |
| `created_at` | TIMESTAMPTZ | NOT NULL, auto | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, auto | |

### `documents`
Uploaded files (photos, certificates, audio/video). Clan-scoped.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `clan_id` | UUID | FK → clans.id (RESTRICT), NOT NULL | |
| `person_id` | UUID | FK → persons.id (SET NULL) | |
| `title` | VARCHAR(255) | NOT NULL | Tiêu đề tài liệu / Tên file |
| `description` | TEXT | | Ghi chú |
| `document_type` | VARCHAR(20) | NOT NULL | photo, id_document, certificate, audio, video, other / Loại tài liệu |
| `storage_path` | VARCHAR(500) | UNIQUE, NOT NULL | Supabase Storage path |
| `file_size_bytes` | BIGINT | | Dung lượng file |
| `mime_type` | VARCHAR(100) | | |
| `original_filename` | VARCHAR(255) | | Tên file gốc |
| `taken_date` | DATE | | Ngày tháng của tài liệu (ví dụ: ngày chụp ảnh) |
| `taken_place` | VARCHAR(255) | | Địa điểm của tài liệu (ví dụ: nơi chụp ảnh) |
| `is_avatar` | BOOLEAN | DEFAULT false | Có dùng làm avatar không |
| `is_deleted` | BOOLEAN | NOT NULL, DEFAULT false | Soft-delete flag (migration 016, ADR-019) — `DELETE` sets this instead of removing the row; blob untouched until purge |
| `deleted_at` | TIMESTAMPTZ | | When soft-deleted; retention purge job removes row+blob once older than `DOCUMENT_RETENTION_DAYS` |
| `deleted_by` | UUID | | Actor who soft-deleted |
| `created_by` | UUID | NOT NULL | |
| `created_at` | TIMESTAMPTZ | NOT NULL, auto | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, auto | |

Partial index `idx_documents_is_deleted ON documents (is_deleted) WHERE
is_deleted = false` backs the live-only read path. See
[ADR-019](../decisions/019-document-soft-delete-purge.md).

### `audit_logs`
Immutable log of all write actions. Not clan-scoped.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `clan_id` | UUID | | Nullable for platform-level actions / Null nếu thao tác hệ thống |
| `actor_id` | UUID | NOT NULL | The user ID / Người thực hiện |
| `actor_role` | VARCHAR(50) | NOT NULL | Editor, Viewer, SuperAdmin / Role của người thực hiện |
| `action` | VARCHAR(100) | NOT NULL | e.g. 'person.create', 'claim.approve' |
| `resource_type` | VARCHAR(50) | NOT NULL | 'person', 'claim' / Cấu phần dữ liệu bị ảnh hưởng |
| `resource_id` | UUID | | ID của resource |
| `old_value` | JSONB | | Snapshot before change / Dữ liệu trước khi đổi |
| `new_value` | JSONB | | Snapshot after change / Dữ liệu sau khi đổi |
| `ip_address` | INET | | Địa chỉ IP thao tác |
| `user_agent` | VARCHAR(500) | | Trình duyệt/Thiết bị |
| `created_at` | TIMESTAMPTZ | NOT NULL, auto | |

### `notification_log`
Tracks push notification delivery. FCM tokens are stored in `user_fcm_tokens` (not per-notification).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `clan_id` | UUID | FK → clans.id (RESTRICT), NOT NULL | |
| `event_id` | UUID | FK → events.id (SET NULL) | Sự kiện liên quan |
| `user_id` | UUID | NOT NULL | Người nhận thông báo |
| `notification_type` | VARCHAR(50) | NOT NULL | Loại thông báo (event_reminder, claim_approved ...) |
| `title` | VARCHAR(255) | NOT NULL | Tiêu đề |
| `body` | TEXT | NOT NULL | Nội dung |
| `status` | VARCHAR(20) | DEFAULT 'pending' | pending, sent, failed |
| `sent_at` | TIMESTAMPTZ | | Thời điểm gửi |
| `error_message` | TEXT | | Lỗi nếu có |
| `created_at` | TIMESTAMPTZ | NOT NULL, auto | |

---

## Indexes & Performance Tuning

```sql
-- Identity Claims
CREATE UNIQUE INDEX idx_identity_claims_pending_user ON identity_claims(user_id) WHERE status = 'PENDING';

-- Person lookups within a clan (the most common query)
CREATE INDEX idx_clan_memberships_clan_id ON clan_memberships(clan_id);
CREATE INDEX idx_clan_memberships_person_id ON clan_memberships(person_id);
CREATE INDEX idx_clan_memberships_branch ON clan_memberships(branch_id);

-- Exactly one live founder (thủy tổ) per clan (migration 023_one_founder_per_clan, ADR-026)
CREATE UNIQUE INDEX uq_clan_memberships_one_founder ON clan_memberships (clan_id)
    WHERE is_founder = true;

-- Tree traversal: find all children of a parent
CREATE INDEX idx_parent_child_parent_id ON parent_child(parent_id);
CREATE INDEX idx_parent_child_child_id ON parent_child(child_id);
CREATE INDEX idx_parent_child_clan ON parent_child(created_by_clan_id);
CREATE INDEX idx_parent_child_is_deleted ON parent_child(is_deleted) WHERE is_deleted = false;

-- Marriage lookups
CREATE INDEX idx_marriages_person1 ON marriages(person1_id);
CREATE INDEX idx_marriages_person2 ON marriages(person2_id);
CREATE INDEX idx_marriages_clan ON marriages(created_by_clan_id);
CREATE INDEX idx_marriages_is_deleted ON marriages(is_deleted) WHERE is_deleted = false;

-- spouse_order uniqueness per person1, active (non-divorced) marriages only (migration 015_data_integrity, ADR-017 sibling fix)
CREATE UNIQUE INDEX uq_marriages_spouse_order ON marriages (created_by_clan_id, person1_id, spouse_order)
    WHERE spouse_order IS NOT NULL AND is_deleted = false AND status <> 'divorced';

-- Branches
CREATE INDEX idx_branches_clan ON branches(clan_id);
CREATE INDEX idx_branches_parent ON branches(parent_branch_id);

-- Person origin clan
CREATE INDEX idx_persons_created_by_clan ON persons(created_by_clan_id);

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

-- FCM tokens
CREATE INDEX ix_user_fcm_tokens_user_id ON user_fcm_tokens(user_id);

-- Clan invitations
CREATE INDEX ix_clan_invitations_clan_id ON clan_invitations(clan_id);
CREATE INDEX ix_clan_invitations_clan_email ON clan_invitations(clan_id, email);
```

---

## RLS Policies

> **Status (2026-06-28) — ASPIRATIONAL, not yet active.** The policies below are
> the *target* design for the deferred RLS layer-2 (ADR-008). They are **not**
> applied to the running database, and the GUC shown here (`app.current_clan_id`)
> differs from the one the implemented pilot uses (`app.clan_id`). What ships today:
> a single `documents` pilot policy (`ENABLE`d, not `FORCE`d) under a non-bypass
> `familyroots_app` role, while the app still connects as a bypass role — so these
> reads/writes are gated by the **application/repository layer**, not RLS. See
> `multi-tenancy.md` and ADR-008. Treat the SQL below
> as the spec for a future activation phase, not a description of current behavior.

**Read Access** *(target design — not active)*
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

**Write Access**
```sql
-- Marriages & ParentChild: writable only by the managing clan
CREATE POLICY marriages_write ON marriages FOR ALL USING (
  created_by_clan_id = current_setting('app.current_clan_id')::uuid
);

CREATE POLICY parent_child_write ON parent_child FOR ALL USING (
  created_by_clan_id = current_setting('app.current_clan_id')::uuid
);

-- Clan-scoped tables (events, documents): standard clan_id check
CREATE POLICY clan_scoped_access ON events FOR ALL USING (
  clan_id = current_setting('app.current_clan_id')::uuid
);
```

## Storage Strategy

Single shared Supabase Storage bucket with path-based clan isolation:

```text
family-roots-files/
├── clans/{clan_id}/persons/{person_id}/avatar.jpg
├── clans/{clan_id}/persons/{person_id}/photos/
├── clans/{clan_id}/documents/
└── clans/{clan_id}/events/
```

RLS policy on `storage.objects` ensures users can only access files under their clan's path.

## Migrations

Managed via Alembic. Migrations live in `backend/migrations/versions/` and operate on the single `public` schema. No multi-schema complexity.
