# Database Schema

> TODO: implement in Prompt 2 — full schema definitions with columns, types, constraints

## Overview

FamilyRoots uses PostgreSQL 16 with schema-per-tenant isolation. The `public` schema holds shared data; each clan gets a `clan_{slug}` schema.

## Public Schema

### `clans`
Central registry of family clans.

| Column       | Type        | Notes                  |
|-------------|-------------|------------------------|
| id          | UUID        | PK                     |
| name        | VARCHAR     | Display name           |
| slug        | VARCHAR     | Unique, URL-safe       |
| created_at  | TIMESTAMPTZ | Auto                   |
| updated_at  | TIMESTAMPTZ | Auto                   |

### `users`
Platform user accounts (can belong to one or more clans).

| Column       | Type        | Notes                  |
|-------------|-------------|------------------------|
| id          | UUID        | PK                     |
| email       | VARCHAR     | Unique                 |
| password_hash | VARCHAR   | bcrypt                 |
| role        | VARCHAR     | admin, editor, viewer  |
| clan_id     | UUID        | FK → clans.id          |
| created_at  | TIMESTAMPTZ | Auto                   |

## Tenant Schema (`clan_{slug}`)

### `members`
Family members within a clan.

| Column       | Type        | Notes                  |
|-------------|-------------|------------------------|
| id          | UUID        | PK                     |
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
Relationships between family members.

| Column        | Type        | Notes                    |
|--------------|-------------|--------------------------|
| id           | UUID        | PK                       |
| from_member  | UUID        | FK → members.id          |
| to_member    | UUID        | FK → members.id          |
| type         | VARCHAR     | parent, spouse, sibling  |
| created_at   | TIMESTAMPTZ | Auto                     |

### `documents`
Uploaded documents and photos.

| Column       | Type        | Notes                  |
|-------------|-------------|------------------------|
| id          | UUID        | PK                     |
| title       | VARCHAR     |                        |
| file_url    | VARCHAR     | Storage URL            |
| file_type   | VARCHAR     | image, pdf, etc.       |
| member_id   | UUID        | FK → members.id (opt)  |
| uploaded_by | UUID        | FK → users.id          |
| created_at  | TIMESTAMPTZ | Auto                   |

### `events`
Family events and milestones.

| Column       | Type        | Notes                  |
|-------------|-------------|------------------------|
| id          | UUID        | PK                     |
| title       | VARCHAR     |                        |
| description | TEXT        |                        |
| event_date  | DATE        |                        |
| event_type  | VARCHAR     | ceremony, memorial, etc|
| created_at  | TIMESTAMPTZ | Auto                   |

## Indexes

> TODO: implement in Prompt 2 — define indexes for common query patterns

## Migrations

Managed via Alembic. Migrations live in `backend/migrations/versions/` and must be tenant-aware (applied to all `clan_*` schemas).
