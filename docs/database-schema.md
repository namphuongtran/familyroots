# Database Schema

> TODO: implement in Prompt 2 — full schema definitions with columns, types, constraints

## Overview

FamilyRoots uses PostgreSQL 18 with a single `public` schema. Data isolation between clans is enforced by a `clan_id` column on every clan-scoped table, combined with Supabase Row Level Security (RLS) policies.

## Public Schema

### `clans`
Central registry of family clans.

| Column       | Type        | Notes                  |
|-------------|-------------|------------------------|
| id          | UUID        | PK                     |
| name        | VARCHAR     | Display name           |
| slug        | VARCHAR     | Unique, URL-safe       |
| is_active   | BOOLEAN     | Default true           |
| created_at  | TIMESTAMPTZ | Auto                   |
| updated_at  | TIMESTAMPTZ | Auto                   |

### `platform_users`
Platform super admin accounts.

| Column       | Type        | Notes                     |
|-------------|-------------|---------------------------|
| id          | UUID        | PK                        |
| email       | VARCHAR     | Unique                    |
| role        | VARCHAR     | Always 'super_admin'      |
| is_active   | BOOLEAN     | Default true              |
| last_login_at | TIMESTAMPTZ | Nullable                |
| created_at  | TIMESTAMPTZ | Auto                      |

### `user_clan_roles`
Maps users to clans with their role. Supports multi-clan membership.

| Column       | Type        | Notes                              |
|-------------|-------------|------------------------------------|
| id          | UUID        | PK                                 |
| user_id     | UUID        | FK → Supabase auth.users           |
| clan_id     | UUID        | FK → clans.id                      |
| role        | VARCHAR     | admin, editor, viewer              |
| is_approved | BOOLEAN     | Default false (pending approval)   |
| joined_at   | TIMESTAMPTZ | Auto                               |
| created_at  | TIMESTAMPTZ | Auto                               |
| updated_at  | TIMESTAMPTZ | Auto                               |

Unique constraint on `(user_id, clan_id)` — a user can only have one role per clan.

### `members`
Family members within a clan. Isolated by `clan_id` + RLS.

| Column       | Type        | Notes                  |
|-------------|-------------|------------------------|
| id          | UUID        | PK                     |
| clan_id     | UUID        | FK → clans.id, NOT NULL|
| full_name   | VARCHAR     | Vietnamese name        |
| birth_date  | DATE        | Nullable               |
| death_date  | DATE        | Nullable               |
| gender      | VARCHAR     | male, female, other    |
| generation  | INTEGER     | Generation number      |
| bio         | TEXT        | Biography              |
| avatar_url  | VARCHAR     | Profile image          |
| created_at  | TIMESTAMPTZ | Auto                   |
| updated_at  | TIMESTAMPTZ | Auto                   |

### `relationships`
Relationships between family members. Isolated by `clan_id` + RLS.

| Column        | Type        | Notes                    |
|--------------|-------------|--------------------------|
| id           | UUID        | PK                       |
| clan_id      | UUID        | FK → clans.id, NOT NULL  |
| from_member  | UUID        | FK → members.id          |
| to_member    | UUID        | FK → members.id          |
| type         | VARCHAR     | parent, spouse, sibling  |
| created_at   | TIMESTAMPTZ | Auto                     |
| updated_at   | TIMESTAMPTZ | Auto                     |

### `documents`
Uploaded documents and photos. Isolated by `clan_id` + RLS.

| Column       | Type        | Notes                  |
|-------------|-------------|------------------------|
| id          | UUID        | PK                     |
| clan_id     | UUID        | FK → clans.id, NOT NULL|
| title       | VARCHAR     |                        |
| file_url    | VARCHAR     | Storage URL            |
| file_type   | VARCHAR     | image, pdf, etc.       |
| member_id   | UUID        | FK → members.id (opt)  |
| uploaded_by | UUID        | FK → auth.users        |
| created_at  | TIMESTAMPTZ | Auto                   |
| updated_at  | TIMESTAMPTZ | Auto                   |

### `events`
Family events and milestones. Isolated by `clan_id` + RLS.

| Column       | Type        | Notes                  |
|-------------|-------------|------------------------|
| id          | UUID        | PK                     |
| clan_id     | UUID        | FK → clans.id, NOT NULL|
| title       | VARCHAR     |                        |
| description | TEXT        |                        |
| event_date  | DATE        |                        |
| event_type  | VARCHAR     | ceremony, memorial, etc|
| created_at  | TIMESTAMPTZ | Auto                   |
| updated_at  | TIMESTAMPTZ | Auto                   |

## Storage

Single shared Supabase Storage bucket with path-based clan isolation:

```
family-roots-files/
├── clans/{clan_id}/members/{member_id}/avatar.jpg
├── clans/{clan_id}/members/{member_id}/photos/
├── clans/{clan_id}/documents/
└── clans/{clan_id}/events/
```

RLS policy on `storage.objects` ensures users can only access files under their clan's path.

## Indexes

> TODO: implement in Prompt 2 — define indexes for common query patterns

## Migrations

Managed via Alembic. Migrations live in `backend/migrations/versions/` and operate on the single `public` schema. No multi-schema complexity.
