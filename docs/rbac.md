# Role-Based Access Control (RBAC)

## Two-Level Role Hierarchy

FamilyRoots uses a **two-level** role system:

```
PLATFORM LEVEL (public schema)          CLAN LEVEL (clan-scoped via RLS)
─────────────────────────────           ──────────────────────────
super_admin                             admin
  │                                       │
  ├── Manage all clans                   ├── Manage clan members
  ├── Provision / suspend clans          ├── Approve new user registrations
  ├── View platform-wide metrics         ├── Assign editor/viewer roles
  ├── Promote/demote clan admins         └── Manage clan settings
  ├── Access all clan data (audit)
  └── Cannot be created via API
      (bootstrap only)
```

### Platform Level — `super_admin`

- Stored in `public.platform_users` table (not in any clan schema)
- Exactly **one** super admin exists, enforced by a unique database index
- Created via `scripts/bootstrap_super_admin.py` — **never via API**
- Cannot be deleted via API — only via Supabase Dashboard directly
- All actions are audit-logged with `actor_id`, `action`, `target`, `timestamp`
- JWT contains `platform_role: super_admin` in user metadata

#### Platform Users Table

```sql
-- public.platform_users
CREATE TABLE public.platform_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'super_admin',
    is_active BOOLEAN NOT NULL DEFAULT true,
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT only_super_admin CHECK (role = 'super_admin')
);

-- Only one super_admin allowed at platform level
CREATE UNIQUE INDEX idx_single_super_admin
    ON public.platform_users (role)
    WHERE role = 'super_admin';
```

#### Super Admin API Endpoints

| Method | Path                                   | Description                  |
|--------|----------------------------------------|------------------------------|
| GET    | `/api/v1/platform/clans`               | List all clans on platform   |
| POST   | `/api/v1/platform/clans/{id}/suspend`  | Suspend a clan             |
| POST   | `/api/v1/platform/clans/{id}/reactivate` | Reactivate a clan          |
| GET    | `/api/v1/platform/metrics`             | Platform-wide usage metrics  |
| GET    | `/api/v1/platform/audit-log`           | Cross-clan audit log       |
| POST   | `/api/v1/platform/clans/{id}/admin/promote` | Promote user to clan admin |

#### Security Rules

- No API endpoint to create super admin — bootstrap script only
- No API endpoint to promote to super admin — this role cannot be granted via app
- Super admin cannot be deleted via API — only via Supabase Dashboard
- Database constraint ensures only one `super_admin` row

### Clan Level — `admin`, `editor`, `viewer`

## Roles

| Role    | Description                                    |
|---------|------------------------------------------------|
| admin   | Full access — manage clan settings, users, data|
| editor  | Create and edit members, documents, events     |
| viewer  | Read-only access to clan data                  |

## Permission Matrix

| Resource        | admin | editor | viewer |
|-----------------|-------|--------|--------|
| Clan settings   | CRUD  | R      | R      |
| Members         | CRUD  | CRU    | R      |
| Relationships   | CRUD  | CRU    | R      |
| Documents       | CRUD  | CRU    | R      |
| Events          | CRUD  | CRU    | R      |
| User management | CRUD  | —      | —      |
| Audit logs      | R     | —      | —      |
| Family tree     | R     | R      | R      |

## Implementation

> TODO: implement in Prompt 2

### Backend

- JWT claims include `role` and `clan_id`
- FastAPI dependency injection checks permissions per endpoint
- Decorator pattern: `@require_role("admin")`

### Frontend

- Route guards check role before rendering pages
- UI elements conditionally shown based on role
- Admin panel only accessible to `admin` role

## User Approval Flow

1. New user registers with a clan invitation link
2. User account created with `pending` status
3. Clan admin reviews and approves/rejects via Admin Panel
4. Upon approval, user receives `viewer` role by default
5. Admin can upgrade to `editor` role as needed
