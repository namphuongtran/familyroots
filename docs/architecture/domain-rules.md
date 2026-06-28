# Domain Rules Reference

The genealogy and integrity rules enforced inside the domain layer
(`backend/app/domain/`). These are the invariants that keep family data correct
regardless of which client or API path triggers a write. Each rule lists the
**error code** raised so clients and contract docs stay aligned.

> All rules live in pure-domain code (no FastAPI / SQLAlchemy). Domain exceptions
> are mapped to the structured error envelope by `app/core/exceptions.py`
> (`{ "error": { "code", "message", "detail" } }`). See [API Design](api-design.md).

## Exception types

Defined in `app/domain/shared/exceptions.py`:

| Exception | Meaning | Typical HTTP |
|-----------|---------|--------------|
| `EntityNotFoundError` | Aggregate not found / not in clan | 404 |
| `BusinessRuleViolation` | Domain invariant broken | 422 |
| `ConflictError` | Duplicate / conflicting state | 409 |
| `ForbiddenError` | Permission denied at domain level | 403 |
| `ValidationError` | Input shape invalid | 422 |
| `AuthenticationError` | Auth failure | 401 |

## Relationship rules

Enforced by `RelationshipDomainValidator` (`app/domain/relationship/validator.py`)
and the `Marriage` / `ParentChild` aggregates (`app/domain/relationship/entities.py`).

| Rule | Condition | Error code | Type |
|------|-----------|------------|------|
| No self-marriage | `person1_id == person2_id` | `self_marriage_not_allowed` | BusinessRuleViolation |
| No self-parent | `parent_id == child_id` | `self_parent_not_allowed` | BusinessRuleViolation |
| Max 2 biological parents | child already has ≥2 `biological` parents | `relationship.too_many_biological_parents` | ConflictError |
| Minimum parent age gap | parent <12 yrs older than child | `relationship.parent_too_young` (detail: `{min_age_gap: 12, actual}`) | BusinessRuleViolation |
| Unusual age gap | parent >80 yrs older than child | *(no error — returns `{warning}`)* | warning |
| Cycle prevention | new parent is already a descendant of child | `relationship.creates_cycle` | BusinessRuleViolation |
| No duplicate parent-child | link already exists | `relationship.duplicate_parent_child` | ConflictError |
| No duplicate marriage | active marriage already exists | `relationship.duplicate_marriage` | ConflictError |

Age gap is computed as `(child_birth - parent_birth).days / 365.25`; the check is
skipped when either birth date is missing. Ancestry/cycle and biological-parent
counts are queried through `RelationshipQueryPort` (kept infrastructure-free).

The parent-child validation pipeline (`validate_parent_child`):

```mermaid
flowchart TD
    A["validate_parent_child()"] --> B{"parent_id == child_id?"}
    B -->|"có"| E1["❌ self_parent_not_allowed"]
    B -->|"không"| C{"biological & đã có ≥2 cha/mẹ ruột?"}
    C -->|"có"| E2["❌ too_many_biological_parents"]
    C -->|"không"| D{"có đủ ngày sinh 2 người?"}
    D -->|"không"| G{"tạo vòng lặp huyết thống?"}
    D -->|"có"| F{"chênh lệch tuổi < 12?"}
    F -->|"có"| E3["❌ parent_too_young"]
    F -->|"không"| H{"chênh lệch tuổi > 80?"}
    H -->|"có"| W["⚠️ trả về warning<br/>(bỏ qua cycle check)"]
    H -->|"không"| G
    G -->|"có"| E4["❌ creates_cycle"]
    G -->|"không"| OK["✅ hợp lệ"]
```

> 🇻🇳 **Lưu ý:** khi chênh lệch tuổi **> 80 năm**, validator trả về cảnh báo
> (`warning`) và **dừng luôn** — *không* chạy kiểm tra vòng lặp huyết thống. Đây là
> hành vi hiện tại của code (`validator.py`), cần biết để không hiểu nhầm là đã
> kiểm tra cycle trong nhánh này.

## Person rules

`app/domain/person/entity.py`:

- **Clan-scoped, not globally shared.** A `Person` is distinct from the
  authenticated user; `created_by_clan_id` is both the write gate and the read
  scope — a clan sees only the persons it created. Cross-clan reads return
  not-found. Isolation is enforced in the application/repository layer (every
  clan-scoped read passes `clan_id`); RLS is a planned SP-3 defense-in-depth
  addition, not yet active.
  *(Legacy note: earlier docs described persons as "globally shared / visible across
  clans". That model was superseded by strict isolation in SP-2B.)*
- **Soft delete.** `soft_delete()` sets `is_deleted`, `deleted_at`, `deleted_by` and
  emits `PersonDeleted`; `restore()` clears them and emits `PersonRestored`.
  Records are never physically removed. See [ADR-006](../decisions/006-soft-vs-hard-delete.md).
- **Audited updates.** `update()` records old/new values into the `PersonUpdated`
  event for the audit trail.

### Identity claims

`IdentityClaim` entity — links a `user_id` to a `person_id` so a user can claim
"this is me". Full flow in [ADR-007](../decisions/007-identity-claims-workflow.md).

```mermaid
stateDiagram-v2
    [*] --> PENDING: tạo claim
    PENDING --> APPROVED: approve(admin)
    PENDING --> REJECTED: reject(admin) / reject_as_duplicate()
    PENDING --> CANCELLED: cancel(requester)
    APPROVED --> [*]
    REJECTED --> [*]
    CANCELLED --> [*]
```

- Status machine: `PENDING → APPROVED | REJECTED | CANCELLED`.
- `cancel(user_id)` — only the original requester, only while `PENDING`.
- `approve(admin_id, note)` / `reject(admin_id, note)` — only from `PENDING`.
- `reject_as_duplicate()` — idempotent rejection.
- **Invariant:** at most **one PENDING claim per user globally** (unique constraint).

> 🇻🇳 **Ghi chú:** Đây là cơ chế "nhận thân" — người dùng (`user`) xác nhận một bản
> ghi nhân khẩu (`person`) trong gia phả chính là mình. Mỗi người dùng chỉ được có
> **một yêu cầu đang chờ duyệt (PENDING)** tại một thời điểm để chống spam. Quản trị
> dòng họ (admin) là người duyệt/từ chối. Chi tiết: [ADR-007](../decisions/007-identity-claims-workflow.md).

## Branch rules

`app/domain/branch/entity.py`:

| Rule | Error code | Type |
|------|------------|------|
| A branch cannot be its own parent (`parent_branch_id == id`) | `branch_cannot_be_own_parent` | BusinessRuleViolation |
| Only whitelisted fields are updatable (`name`, `description`, `founder_person_id`, `parent_branch_id`, `branch_order`) | `field_not_updatable` | BusinessRuleViolation |

Branches are **hard-deleted** (no soft-delete flag) — see [ADR-006](../decisions/006-soft-vs-hard-delete.md).

## Document rules

`app/domain/document/entity.py`:

| Rule | Constraint | Error code |
|------|-----------|------------|
| Valid document type | `{photo, id_document, certificate, audio, video, other}` | `invalid_document_type` |
| Allowed MIME type | jpeg, png, webp, heic, pdf, mpeg, wav, mp4, quicktime | `invalid_mime_type` |
| File size limit | ≤ 50 MB | `file_too_large` |
| Avatar needs a person | `set_avatar()` requires `person_id` | `document_not_linked_to_person` |
| Only photos as avatar | `document_type == "photo"` | `only_photo_can_be_avatar` |

Documents are **hard-deleted**; the storage object is removed via `StoragePort`
(`app/infrastructure/storage/supabase_adapter.py`). Storage layout is path-isolated
per clan: `clans/{clan_id}/...`.

## Event rules

`app/domain/event/entity.py`:

| Rule | Constraint | Error code |
|------|-----------|------------|
| Valid event type | `{death_anniversary, birthday, wedding_anniversary, clan_ceremony, custom}` | `invalid_event_type` |
| Whitelisted updates only | `event_type`, `title`, `description`, `event_date`, `is_lunar_calendar`, `is_recurring`, `notify_days_before` | `field_not_updatable` |

Events support lunar-calendar dates (`is_lunar_calendar`) and recurrence
(`is_recurring`), with per-event notification lead time (`notify_days_before`,
default 7). Anniversary reminders are driven by APScheduler — see `backend/CLAUDE.md`
(`NOTIFICATION_CRON_HOUR` / `NOTIFICATION_DAYS_BEFORE`).

## Clan membership rules

`app/domain/clan/` (administration over the ORM `Clan` / `UserClanRole`):

- Roles: `viewer < editor < admin` (clan) plus platform `super_admin`. See [RBAC](rbac.md).
- Membership requires `is_approved = True` before access is granted.
- Admin actions emit auditable events: `UserApproved`, `UserRejected`,
  `UserRoleChanged`, `UserRemoved`, `ClanUpdated`.
- `count_admins()` is used to guard against removing/demoting the last admin.

## Soft-delete vs hard-delete summary

| Aggregate | Delete strategy |
|-----------|-----------------|
| Person | Soft (`is_deleted`, restorable) |
| Marriage, ParentChild | Soft |
| Document, Event, Branch | Hard |

Rationale and the consistency concern are recorded in
[ADR-006](../decisions/006-soft-vs-hard-delete.md).

## 🇻🇳 Thuật ngữ gia phả Việt Nam (glossary)

Các trường dữ liệu mang đặc thù văn hóa Việt — ghi lại ý nghĩa để cả người không
rành gia phả lẫn lập trình viên hiểu đúng. Tên trường lấy từ `Person`
(`app/domain/person/entity.py`) và bảng `persons` ([data-model.md](data-model.md)).

### Các loại tên gọi (`Person`)
| Trường | Tiếng Việt | Giải thích |
|--------|-----------|-----------|
| `full_name` | Họ và tên đầy đủ | Tên dùng hiển thị chính |
| `birth_name` | Tên húy / tên khai sinh | Tên thật lúc sinh, thường kiêng gọi |
| `courtesy_name` | Tên tự (tên chữ) | Tên đặt khi trưởng thành |
| `posthumous_name` | Tên thụy / tên hèm | Tên dùng khi cúng giỗ sau khi mất |
| `alias_name` | Biệt hiệu / tên hiệu | Tên gọi khác, bút danh |
| `title_rank` | Chức tước / phẩm hàm | Tước vị, học vị, chức quan |

### Lịch âm và ngày tháng
- `birth_date` / `death_date` — ngày **dương lịch** (có cờ `*_approx` cho ngày ước lượng).
- `lunar_birth_date` / `lunar_death_date` — ngày **âm lịch**, chỉ dùng để *hiển thị*
  (display-only), không dùng cho tính toán.
- Sự kiện (`Event`) có cờ `is_lunar_calendar` để đánh dấu ngày theo âm lịch —
  quan trọng với ngày giỗ.

### Loại sự kiện (`event_type`)
| Mã | Tiếng Việt |
|----|-----------|
| `death_anniversary` | Ngày giỗ |
| `birthday` | Sinh nhật |
| `wedding_anniversary` | Kỷ niệm ngày cưới |
| `clan_ceremony` | Lễ/việc họ (giỗ tổ, tế lễ…) |
| `custom` | Tùy chỉnh |

### Vai trò (role) trong dòng họ
| Mã | Tiếng Việt | Quyền |
|----|-----------|-------|
| `admin` | Quản trị dòng họ | Quản lý thành viên, duyệt, sửa cấu hình |
| `editor` | Biên tập viên | Thêm/sửa nhân khẩu, quan hệ, tài liệu, sự kiện |
| `viewer` | Người xem | Chỉ đọc |
| `super_admin` | Quản trị nền tảng | Cấp toàn hệ thống (xem [RBAC](rbac.md)) |

## Related docs

- [Bounded Contexts](bounded-contexts.md)
- [Domain Events Catalog](../contracts/domain-events-catalog.md)
- [API Design](api-design.md) — how error codes surface to clients
- [RBAC](rbac.md)
