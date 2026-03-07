# Role-Based Access Control (RBAC)

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
