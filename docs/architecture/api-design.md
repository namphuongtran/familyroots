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
| GET    | `/health` | No   | Liveness + readiness |

Returns `{"status": "ok", "database": "connected", "migrations": "current"}`; degrades
to 503 when the DB is unreachable **or** migrations are behind head. Exempt from the
response envelope.

---

## Auth (`/api/v1/auth/`)

| Method | Path               | Auth | Role | Description                     |
|--------|--------------------|------|------|---------------------------------|
| POST   | `/register`        | No   | —    | Register + join/create clan (email starts unverified); non-enumerating — uniform 201 `{"message": ...}` whether or not the email already has an account (ADR-021) |
| POST   | `/onboard`         | Yes  | —    | Create clan + first admin for an authenticated user (201) |
| POST   | `/login`           | No   | —    | Login via Supabase, get profile |
| POST   | `/logout`          | Yes  | —    | Sign out (revokes Supabase session) |
| POST   | `/refresh`         | No   | —    | Refresh access token            |
| POST   | `/forgot-password` | No   | —    | Send recovery email — always 200, non-enumerating |
| POST   | `/resend-verification` | No | —   | Resend verification email — always 200, non-enumerating |
| GET    | `/me`              | Yes  | —    | Get current user profile        |
| PATCH  | `/me`              | Yes  | —    | Update `full_name` + `preferred_locale` |
| POST   | `/me/fcm-token`    | Yes  | —    | Upsert FCM device token         |
| DELETE | `/me/fcm-token`    | Yes  | —    | Remove FCM device token         |

Login with correct credentials but an unverified email fails with **403
`email_not_verified`** (distinct from 401 bad-credentials). All `/api/v1/auth`
and `/api/v1/invitations` routes are rate-limited (in-memory sliding window,
20 req/min/IP, same bucket — the only rate-limited scope; ADR-021).

### POST `/register`

Non-enumerating (ADR-021): the response body below is returned identically
whether or not `email` already has an account. No `user_id`/`clan_id` is
returned — see [rest-auth-api.md](../contracts/rest-auth-api.md).

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

```json
201 { "data": { "message": "..." } }
```

---

## Me (`/api/v1/me/`)

| Method | Path               | Auth | Description                        |
|--------|--------------------|------|------------------------------------|
| GET    | `/clans`                    | Yes  | List clans the user belongs to     |
| POST   | `/clans/{clan_id}/select`   | Yes  | Select active clan (validates membership) |

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
| PUT    | `/me/founder`                  | Yes  | admin  | Designate/correct clan founder (thủy tổ, ADR-026) |

---

## Persons (`/api/v1/persons/`)

| Method | Path                          | Auth | Role   | Description                     |
|--------|-------------------------------|------|--------|---------------------------------|
| GET    | `/`                           | Yes  | viewer | List persons (paginated, filters) |
| GET    | `/search?q=...`               | Yes  | viewer | Trigram+unaccent full-text search |
| POST   | `/`                           | Yes  | editor | Create a person                 |
| POST   | `/batch`                      | Yes  | viewer | Batch-get up to 100 persons (per-item includes; partial failures in `meta.errors`) |
| POST   | `/{id}/claim`                 | Yes  | viewer | Claim a person profile as one's own (201, identity-claims workflow) |
| GET    | `/{id}`                       | Yes  | viewer | Get person detail               |
| PATCH  | `/{id}`                       | Yes  | editor | Update person                   |
| DELETE | `/{id}`                       | Yes  | admin  | Soft-delete person              |
| POST   | `/{id}/restore`               | Yes  | admin  | Restore soft-deleted person     |
| GET    | `/{id}/marriages`             | Yes  | viewer | List person's marriages         |
| GET    | `/{id}/parent-child`          | Yes  | viewer | List person's parent/child links|
| GET    | `/{id}/documents`             | Yes  | viewer | List person's documents         |
| GET    | `/{id}/events`                | Yes  | viewer | List person's events            |
| GET    | `/{id}/timeline`              | Yes  | viewer | Chronological life timeline     |

### Query Parameters (GET `/`)

| Param      | Type   | Description                         |
|------------|--------|-------------------------------------|
| gender     | string | Filter by gender                    |
| generation | int    | Filter by đời                       |
| profile    | string | summary \| detail \| full           |
| include    | string | Comma-separated embeds: stats,marriages,parent_child,timeline,documents |
| fields     | string | Sparse fieldsets (comma-separated)  |
| cursor     | string | Pagination cursor                   |
| limit      | int    | Items per page (1–100, default 20)  |

All person date fields (`birth_date`, `death_date`) are **HistoricalDate objects**
`{date, precision, display, lunar}` — see `docs/contracts/README.md#historicaldate-canonical-date-shape`.

---

## Relationships (`/api/v1/relationships/`)

### Marriages

| Method | Path                    | Auth | Role   | Description                   |
|--------|-------------------------|------|--------|-------------------------------|
| POST   | `/marriages`            | Yes  | editor | Create marriage (validated)    |
| GET    | `/marriages/{id}`       | Yes  | viewer | Get marriage                  |
| PATCH  | `/marriages/{id}`       | Yes  | editor | Update marriage metadata      |
| DELETE | `/marriages/{id}`       | Yes  | admin  | Delete marriage               |

### Parent-Child

| Method | Path                    | Auth | Role   | Description                   |
|--------|-------------------------|------|--------|-------------------------------|
| POST   | `/parent-child`         | Yes  | editor | Create parent-child link (validated) |
| GET    | `/parent-child/{id}`    | Yes  | viewer | Get parent-child link         |
| PATCH  | `/parent-child/{id}`    | Yes  | editor | Update parent-child metadata  |
| DELETE | `/parent-child/{id}`    | Yes  | admin  | Delete parent-child link      |

### Business Rules (enforced on POST)

- **Max 2 biological parents** per child
- **Parent age gap ≥ 12 years** (hard error if violated)
- **Cycle detection** — child cannot be ancestor of parent
- **Duplicate marriage prevention** — active marriage between same persons blocked
- **Self-loop prevention** — `parent_id ≠ child_id`, `person1_id ≠ person2_id` (schema-level)

### Marriage Request Body

```json
{
  "person1_id": "uuid",
  "person2_id": "uuid",
  "status": "married | divorced | widowed | separated",
  "marriage_date": "1945-02-10",
  "divorce_date": null,
  "marriage_place": "Huế",
  "spouse_order": 1,
  "notes": "Optional note"
}
```

### Parent-Child Request Body

```json
{
  "parent_id": "uuid",
  "child_id": "uuid",
  "relationship_type": "biological | adopted | step | foster",
  "notes": "Optional note"
}
```

---

## Tree (`/api/v1/tree/`)

| Method | Path                        | Auth | Role   | Description                    |
|--------|-----------------------------|------|--------|--------------------------------|
| GET    | `/`                         | Yes  | viewer | Full tree from founder/root    |
| GET    | `/subtree/{person_id}`      | Yes  | viewer | Subtree rooted at person (max_generations default 5) |
| GET    | `/ancestors/{person_id}`    | Yes  | viewer | Ancestor chain up to root      |
| GET    | `/focus/{person_id}`        | Yes  | viewer | Focus view: breadcrumb ancestors + bounded subtree (see `docs/contracts/tree-focus.md`) |
| GET    | `/path?from_id=&to_id=`     | Yes  | viewer | Find relationship path + description |

### Query Parameters (GET `/`)

| Param           | Type | Description                          |
|-----------------|------|--------------------------------------|
| root_person_id  | uuid | Root person (default: clan founder)  |
| max_generations | int  | Max depth 1–50 (default: 10)         |

Tree nodes carry graph-computed `generation` (đời, thủy tổ = 1) and derived
`mother_id`/`mother_spouse_order` for đa thê grouping; node dates are HistoricalDate
objects. See `docs/architecture/tree-read-model.md` and `docs/contracts/rest-tree-api.md`.

### GET `/path` Response

```json
{
  "data": {
    "path": [
      {"person_id": "uuid", "full_name": "...", "gender": "male", "edge_type": null},
      {"person_id": "uuid", "full_name": "...", "gender": "female", "edge_type": "parent"}
    ],
    "description": "Cha/Mẹ",
    "found": true
  }
}
```

---

## Branches (`/api/v1/branches/`)

| Method | Path        | Auth | Role   | Description                       |
|--------|-------------|------|--------|-----------------------------------|
| GET    | `/`         | Yes  | viewer | List branches (chi/phái), non-paginated |
| POST   | `/`         | Yes  | editor | Create branch (201)               |
| GET    | `/{id}`     | Yes  | viewer | Get branch                        |
| PATCH  | `/{id}`     | Yes  | editor | Update branch                     |
| DELETE | `/{id}`     | Yes  | admin  | Delete branch                     |

## Claims (`/api/v1/claims` + `/api/v1/clans/{clan_id}/claims`)

Identity-claims workflow (ADR-007): users claim a person profile; admins of the
person's **origin clan** (`created_by_clan_id`) review. Full contract:
`docs/contracts/rest-claims-api.md`.

| Method | Path                                              | Role          |
|--------|---------------------------------------------------|---------------|
| GET    | `/claims`                                         | any active user (list my claims) |
| DELETE | `/claims/{id}`                                    | owner (cancel, 204) |
| GET    | `/clans/{clan_id}/claims`                         | admin\|editor |
| POST   | `/clans/{clan_id}/claims/{id}/approve` / `reject` | admin         |
| DELETE | `/clans/{clan_id}/members/{user_id}/unlink`       | admin (204)   |
| POST   | `/clans/{clan_id}/members/{user_id}/prelink`      | admin (201)   |

## Invitations (`/api/v1/clans/{clan_id}/invitations` + `/api/v1/invitations`)

Full contract: `docs/contracts/rest-invitations-api.md`.

| Method | Path                                | Role  |
|--------|-------------------------------------|-------|
| POST   | `/clans/{clan_id}/invitations`      | admin (201) |
| GET    | `/clans/{clan_id}/invitations`      | admin |
| DELETE | `/clans/{clan_id}/invitations/{id}` | admin (204) |
| POST   | `/invitations/{token}/accept`       | any authenticated user |

`/api/v1/invitations` (the token-bearing accept surface) is rate-limited
alongside `/api/v1/auth` (20 req/min/IP, same bucket — ADR-021). Admin CRUD
under `/clans/{clan_id}/invitations` is **not** rate-limited — it's an
authenticated admin surface, not the abuse-prone unauthenticated-adjacent one.

---

## Documents (`/api/v1/documents/`)

| Method | Path                       | Auth | Role   | Description                    |
|--------|----------------------------|------|--------|--------------------------------|
| POST   | `/`                        | Yes  | editor | Upload file (multipart/form)   |
| GET    | `/`                        | Yes  | viewer | List documents (paginated)     |
| GET    | `/{id}`                    | Yes  | viewer | Get document with presigned URL |
| DELETE | `/{id}`                    | Yes  | admin  | Soft-delete (blob kept; see ADR-019) |
| POST   | `/{id}/restore`            | Yes  | admin  | Restore a soft-deleted document |
| PATCH  | `/{id}/set-avatar`         | Yes  | editor | Set photo as person avatar     |

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
| person_id      | uuid   | No       | Link to a person         |
| description    | string | No       | Description              |
| taken_date     | date   | No       | When photo was taken     |
| taken_place    | string | No       | Where photo was taken    |

---

## Exports (`/api/v1/exports/`)

| Method | Path                | Auth | Role  | Description                              |
|--------|---------------------|------|-------|-------------------------------------------|
| GET    | `/clan?format=json\|gedcom` | Yes | admin | Download the full clan archive — **envelope-exempt** (returns the raw file, `Content-Disposition: attachment`) |

- `format` defaults to `json`; an unrecognized value is a 422 (Pydantic query
  pattern), not a handler-level error.
- `format=json` — lossless archive (`familyroots-clan-export`,
  `format_version: 1`): every business column, soft-deleted persons/marriages/
  parent-child edges included and flagged, graph-computed đời, a
  `documents_manifest` with presigned download URLs (no blob zipping).
- `format=gedcom` — GEDCOM 5.5.1 interop view: soft-deleted records excluded;
  Vietnamese-only concepts (tên húy, tên thụy, đời, chi, lunar dates) carried
  in structured `NOTE` lines.
- Filename: `{clan_slug}-gia-pha-{YYYY-MM-DD}.{json|ged}`.
- See [rest-exports-api.md](../contracts/rest-exports-api.md) for the full
  schema/mapping table and [ADR-020](../decisions/020-clan-export-formats.md)
  for the format/delivery rationale.

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

`event_date` in responses is a HistoricalDate object; `/upcoming`'s `next_occurrence`
stays a scalar date (derived recurrence).

---

## Platform Admin (`/api/v1/platform/`)

All endpoints require `user_profiles.platform_role = 'super_admin'` (checked by the
`get_super_admin` dependency — not a `SUPER_ADMIN_UID` env match) **and** an active
profile (`is_active = true`, enforced upstream by the `get_current_user` chokepoint
on every authenticated request).

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
GET /api/v1/persons/?cursor=<opaque>&limit=20
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
    "code": "person_not_found",
    "message": "Không tìm thấy người",
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
| editor | viewer + create/update persons, marriages, parent-child, events, documents |
| admin  | editor + manage users, delete resources, clan settings |

Roles are scoped per clan — a user can be `admin` in one clan and `viewer` in another.
