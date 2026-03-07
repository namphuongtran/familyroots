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
  └── Cannot be created via API          editor
      (bootstrap only)                     │
                                           ├── Create/edit members
                                           ├── Create/edit relationships
                                           ├── Upload documents
                                           └── Create/edit events

                                         viewer
                                           │
                                           └── Read-only access to all clan data
```

### Platform Level — `super_admin`

- Stored in `public.platform_users` table (not in any clan schema)
- Exactly **one** super admin exists, enforced by a unique database index
- Created via `scripts/bootstrap_super_admin.py` — **never via API**
- Cannot be deleted via API — only via Supabase Dashboard directly
- All actions are audit-logged with `actor_id`, `action`, `target`, `timestamp`
- JWT contains `platform_role: super_admin` in user metadata

### Clan Level — `admin`, `editor`, `viewer`

Stored in `public.user_clan_roles` table. A user can belong to at most one clan (enforced by unique index on `user_id`).

## Full Permission Matrix

| Action                         | super_admin | admin | editor | viewer |
| ------------------------------ | ----------- | ----- | ------ | ------ |
| **CLAN**                       |             |       |        |        |
| View own clan info             | ✅           | ✅     | ✅      | ✅      |
| Edit clan info                 | ✅           | ✅     | ❌      | ❌      |
| Delete clan                    | ✅           | ❌     | ❌      | ❌      |
| View all clans (platform)      | ✅           | ❌     | ❌      | ❌      |
| Suspend/reactivate clan        | ✅           | ❌     | ❌      | ❌      |
| **MEMBERS**                    |             |       |        |        |
| View members                   | ✅           | ✅     | ✅      | ✅      |
| Create member                  | ✅           | ✅     | ✅      | ❌      |
| Edit member                    | ✅           | ✅     | ✅      | ❌      |
| Soft-delete member             | ✅           | ✅     | ❌      | ❌      |
| Restore deleted member         | ✅           | ✅     | ❌      | ❌      |
| Hard-delete member             | ✅           | ❌     | ❌      | ❌      |
| **RELATIONSHIPS**              |             |       |        |        |
| View relationships             | ✅           | ✅     | ✅      | ✅      |
| Create relationship            | ✅           | ✅     | ✅      | ❌      |
| Edit relationship              | ✅           | ✅     | ✅      | ❌      |
| Delete relationship            | ✅           | ✅     | ❌      | ❌      |
| **DOCUMENTS**                  |             |       |        |        |
| View documents                 | ✅           | ✅     | ✅      | ✅      |
| Upload document                | ✅           | ✅     | ✅      | ❌      |
| Delete own upload              | ✅           | ✅     | ✅      | ❌      |
| Delete any document            | ✅           | ✅     | ❌      | ❌      |
| **EVENTS**                     |             |       |        |        |
| View events                    | ✅           | ✅     | ✅      | ✅      |
| Create/edit event              | ✅           | ✅     | ✅      | ❌      |
| Delete event                   | ✅           | ✅     | ❌      | ❌      |
| **FAMILY TREE**                |             |       |        |        |
| View family tree               | ✅           | ✅     | ✅      | ✅      |
| Export tree as PDF             | ✅           | ✅     | ✅      | ✅      |
| **USER MANAGEMENT**            |             |       |        |        |
| View pending users             | ✅           | ✅     | ❌      | ❌      |
| Approve user registration      | ✅           | ✅     | ❌      | ❌      |
| Assign editor/viewer role      | ✅           | ✅     | ❌      | ❌      |
| Promote user to admin          | ✅           | ❌     | ❌      | ❌      |
| Remove user from clan          | ✅           | ✅     | ❌      | ❌      |
| **AUDIT LOGS**                 |             |       |        |        |
| View clan audit log            | ✅           | ✅     | ❌      | ❌      |
| View platform audit log        | ✅           | ❌     | ❌      | ❌      |
| **NOTIFICATIONS**              |             |       |        |        |
| Receive push notifications     | ✅           | ✅     | ✅      | ✅      |
| Configure notification settings| ✅           | ✅     | ✅      | ✅      |

## Implementation

### Backend — FastAPI Dependency Injection

Permission checks use a dependency factory pattern in `backend/app/core/permissions.py`:

```python
from app.core.permissions import ClanRole, require_role, RequireEditor, RequireAdmin

# Option 1: inline dependency
@router.post("/members", dependencies=[Depends(require_role(ClanRole.EDITOR))])

# Option 2: convenience constants
@router.post("/members", dependencies=[RequireEditor])
@router.delete("/members/{id}", dependencies=[RequireAdmin])
```

The `require_role()` dependency:
1. Extracts `user_id` from the JWT via `get_current_user()`
2. Queries `UserClanRole` table for the user's role and approval status
3. Compares against the role hierarchy: `viewer < editor < admin`
4. Returns 403 if the user's role is insufficient

Super admin access is handled separately via `get_super_admin()` in `backend/app/core/security.py`, which checks `public.platform_users`.

### Frontend

- Route guards check role before rendering pages
- UI elements conditionally shown based on role
- Admin panel only accessible to `admin` role

## User Approval Flow

1. New user registers with a clan invitation link
2. User account created with `is_approved = false`
3. Clan admin reviews and approves/rejects via Admin Panel
4. Upon approval, user receives `viewer` role by default
5. Admin can upgrade to `editor` role as needed

## Super Admin API Endpoints

| Method | Path                                         | Description                  |
| ------ | -------------------------------------------- | ---------------------------- |
| GET    | `/api/v1/platform/clans`                     | List all clans on platform   |
| POST   | `/api/v1/platform/clans/{id}/suspend`        | Suspend a clan               |
| POST   | `/api/v1/platform/clans/{id}/reactivate`     | Reactivate a clan            |
| GET    | `/api/v1/platform/metrics`                   | Platform-wide usage metrics  |
| GET    | `/api/v1/platform/audit-log`                 | Cross-clan audit log         |
| POST   | `/api/v1/platform/clans/{id}/admin/promote`  | Promote user to clan admin   |

### Security Rules

- No API endpoint to create super admin — bootstrap script only
- No API endpoint to promote to super admin — this role cannot be granted via app
- Super admin cannot be deleted via API — only via Supabase Dashboard
- Database constraint ensures only one `super_admin` row
