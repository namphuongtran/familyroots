# FamilyRoots API Reference

## Base URL

```
/api/v1/
```

## Authentication

All endpoints (except register/login) require a **Bearer JWT** token issued by Supabase Auth.

```
Authorization: Bearer <access_token>
X-Current-Clan-Id: <uuid>
Accept-Language: vi | en | fr | zh
```

- `X-Current-Clan-Id` — required for all clan-scoped endpoints. Determines which clan's data to access.
- `Accept-Language` — optional. Determines the language for error messages and kinship terms. Defaults to `vi`.

## Health

| Method | Path      | Auth | Description       |
|--------|-----------|------|-------------------|
| GET    | `/health` | No   | Liveness check    |

Returns `{"status": "ok"}`.

---

## Auth (`/api/v1/auth/`)

| Method | Path               | Auth | Role | Description                     |
|--------|--------------------|------|------|---------------------------------|
| POST   | `/register`        | No   | —    | Register + join/create clan     |
| POST   | `/login`           | No   | —    | Login via Supabase, get profile |
| POST   | `/logout`          | Yes  | —    | Sign out                        |
| POST   | `/refresh`         | No   | —    | Refresh access token            |
| GET    | `/me`              | Yes  | —    | Get current user profile        |
| PATCH  | `/me`              | Yes  | —    | Update display name             |
| POST   | `/me/fcm-token`    | Yes  | —    | Upsert FCM device token         |
| DELETE | `/me/fcm-token`    | Yes  | —    | Remove FCM device token         |

### POST `/register`

```json
{
  "email": "user@example.com",
  "password": "secure-password",
  "full_name": "Nguyễn Văn A",
  "clan_action": "join",        // "join" or "create"
  "clan_id": "uuid",            // required when clan_action=join
  "clan_name": "Nguyễn Đức",    // required when clan_action=create
  "clan_slug": "nguyen-duc"     // required when clan_action=create
}
```

---

## Me (`/api/v1/me/`)

| Method | Path               | Auth | Description                        |
|--------|--------------------|------|------------------------------------|
| GET    | `/clans`           | Yes  | List clans the user belongs to     |
| POST   | `/switch-clan`     | Yes  | Switch active clan                 |

---

## Clans (`/api/v1/clans/`)

All endpoints scoped to the caller's current clan via `X-Current-Clan-Id`.

| Method | Path                           | Auth | Role   | Description               |
|--------|--------------------------------|------|--------|---------------------------|
| GET    | `/me`                          | Yes  | viewer | Get current clan info     |
| PATCH  | `/me`                          | Yes  | admin  | Update clan settings      |
| GET    | `/me/users`                    | Yes  | admin  | List clan users (paginated) |
| GET    | `/me/users/pending`            | Yes  | admin  | List pending users        |
| POST   | `/me/users/{user_id}/approve`  | Yes  | admin  | Approve pending user      |
| POST   | `/me/users/{user_id}/reject`   | Yes  | admin  | Reject pending user       |
| PATCH  | `/me/users/{user_id}/role`     | Yes  | admin  | Change user role          |
| DELETE | `/me/users/{user_id}`          | Yes  | admin  | Remove user from clan     |

---

## Members (`/api/v1/members/`)

| Method | Path                          | Auth | Role   | Description                     |
|--------|-------------------------------|------|--------|---------------------------------|
| GET    | `/`                           | Yes  | viewer | List members (paginated, filters) |
| GET    | `/search?q=...`               | Yes  | viewer | Trigram+unaccent full-text search |
| POST   | `/`                           | Yes  | editor | Create a member                 |
| GET    | `/{id}`                       | Yes  | viewer | Get member detail               |
| PATCH  | `/{id}`                       | Yes  | editor | Update member                   |
| DELETE | `/{id}`                       | Yes  | admin  | Soft-delete member              |
| POST   | `/{id}/restore`               | Yes  | admin  | Restore soft-deleted member     |
| GET    | `/{id}/relationships`         | Yes  | viewer | List member's relationships     |
| GET    | `/{id}/documents`             | Yes  | viewer | List member's documents         |
| GET    | `/{id}/events`                | Yes  | viewer | List member's events            |
| GET    | `/{id}/timeline`              | Yes  | viewer | Chronological life timeline     |

### Query Parameters (GET `/`)

| Param    | Type   | Description                         |
|----------|--------|-------------------------------------|
| gender   | string | Filter by gender                    |
| alive    | bool   | Filter living/deceased              |
| cursor   | string | Pagination cursor                   |
| limit    | int    | Items per page (1–100, default 20)  |

---

## Relationships (`/api/v1/relationships/`)

| Method | Path             | Auth | Role   | Description                   |
|--------|------------------|------|--------|-------------------------------|
| POST   | `/`              | Yes  | editor | Create relationship (validated) |
| GET    | `/{id}`          | Yes  | viewer | Get relationship              |
| PATCH  | `/{id}`          | Yes  | editor | Update relationship metadata  |
| DELETE | `/{id}`          | Yes  | admin  | Delete relationship           |

### Business Rules (enforced on POST)

- **Max 2 biological parents** per child
- **Parent age gap ≥ 12 years** (hard error if violated)
- **Cycle detection** — child cannot be ancestor of parent
- **No duplicate active spouse** — a person with `end_date IS NULL` spouse cannot remarry
- **Self-loop prevention** — `member_id ≠ related_id` (schema-level)

### Request Body

```json
{
  "member_id": "uuid",
  "related_id": "uuid",
  "relation_type": "parent | child | spouse",
  "relation_subtype": "biological | adoptive | step | foster | married | divorced | widowed | partner",
  "start_date": "2020-01-15",
  "end_date": null,
  "is_primary": true,
  "notes": "Optional note"
}
```

---

## Tree (`/api/v1/tree/`)

| Method | Path                        | Auth | Role   | Description                    |
|--------|-----------------------------|------|--------|--------------------------------|
| GET    | `/`                         | Yes  | viewer | Full tree from founder/root    |
| GET    | `/subtree/{member_id}`      | Yes  | viewer | Subtree rooted at member       |
| GET    | `/ancestors/{member_id}`    | Yes  | viewer | Ancestor chain up to root      |
| GET    | `/path?from_id=&to_id=`     | Yes  | viewer | Find relationship path + description |

### Query Parameters (GET `/`)

| Param           | Type | Description                          |
|-----------------|------|--------------------------------------|
| root_member_id  | uuid | Root member (default: clan founder)  |
| max_generations | int  | Max depth 1–10 (default: 10)         |

### GET `/path` Response

```json
{
  "data": {
    "path": [
      {"member_id": "uuid", "full_name": "...", "gender": "male", "edge_type": null},
      {"member_id": "uuid", "full_name": "...", "gender": "female", "edge_type": "parent"}
    ],
    "description": "Cha/Mẹ",
    "found": true
  }
}
```

---

## Documents (`/api/v1/documents/`)

| Method | Path                       | Auth | Role   | Description                    |
|--------|----------------------------|------|--------|--------------------------------|
| POST   | `/`                        | Yes  | editor | Upload file (multipart/form)   |
| GET    | `/`                        | Yes  | viewer | List documents (paginated)     |
| GET    | `/{id}`                    | Yes  | viewer | Get document with presigned URL |
| DELETE | `/{id}`                    | Yes  | admin  | Delete from storage + DB       |
| PATCH  | `/{id}/set-avatar`         | Yes  | editor | Set photo as member avatar     |

### Allowed MIME Types

`image/jpeg`, `image/png`, `image/webp`, `image/heic`, `application/pdf`, `audio/mpeg`, `audio/wav`, `video/mp4`, `video/quicktime`

### Max File Size

50 MB

### Upload (POST `/`) — multipart/form-data

| Field          | Type   | Required | Description              |
|----------------|--------|----------|--------------------------|
| file           | file   | Yes      | The file to upload       |
| title          | string | Yes      | Document title           |
| document_type  | string | Yes      | photo/id_document/certificate/audio/video/other |
| member_id      | uuid   | No       | Link to a member         |
| description    | string | No       | Description              |
| taken_date     | date   | No       | When photo was taken     |
| taken_place    | string | No       | Where photo was taken    |

---

## Events (`/api/v1/events/`)

| Method | Path              | Auth | Role   | Description                        |
|--------|-------------------|------|--------|------------------------------------|
| POST   | `/`               | Yes  | editor | Create event                       |
| GET    | `/`               | Yes  | viewer | List events (paginated, filters)   |
| GET    | `/upcoming?days=N`| Yes  | viewer | Upcoming events within N days      |
| GET    | `/{id}`           | Yes  | viewer | Get event detail                   |
| PATCH  | `/{id}`           | Yes  | editor | Update event                       |
| DELETE | `/{id}`           | Yes  | editor | Delete event                       |

### Event Types

`death_anniversary`, `birthday`, `wedding_anniversary`, `clan_ceremony`, `custom`

---

## Platform Admin (`/api/v1/platform/`)

All endpoints require the `SUPER_ADMIN_UID` match.

| Method | Path                           | Auth        | Description                    |
|--------|--------------------------------|-------------|--------------------------------|
| GET    | `/clans`                       | super_admin | List all clans (paginated)     |
| GET    | `/clans/{clan_id}`             | super_admin | Clan detail + stats            |
| POST   | `/clans/{clan_id}/suspend`     | super_admin | Suspend clan                   |
| POST   | `/clans/{clan_id}/reactivate`  | super_admin | Reactivate clan                |
| GET    | `/metrics`                     | super_admin | Platform metrics               |
| GET    | `/audit-log`                   | super_admin | Cross-clan audit log           |

---

## Pagination

Cursor-based pagination using `(created_at, id)` composite cursor.

### Request

```
GET /api/v1/members/?cursor=<opaque>&limit=20
```

### Response Envelope

```json
{
  "data": [...],
  "meta": {
    "cursor": "base64-encoded-cursor-or-null",
    "has_more": true,
    "limit": 20
  }
}
```

- `cursor` — pass this value as `?cursor=` in the next request. `null` when no more pages.
- `has_more` — `true` if there are more items beyond this page.
- `limit` — the page size used.

---

## Error Response Format

```json
{
  "error": {
    "code": "member_not_found",
    "message": "Không tìm thấy thành viên",
    "detail": {}
  }
}
```

HTTP status codes: `400` (validation), `403` (forbidden), `404` (not found), `409` (conflict), `422` (unprocessable).

---

## RBAC Roles

| Role   | Permissions                                        |
|--------|----------------------------------------------------|
| viewer | Read all data within the clan                      |
| editor | viewer + create/update members, relationships, events, documents |
| admin  | editor + manage users, delete resources, clan settings |

Roles are scoped per clan — a user can be `admin` in one clan and `viewer` in another.
