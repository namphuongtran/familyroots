# Role-Based Access Control (RBAC)

## Two-Level Role Hierarchy

FamilyRoots uses a **two-level** role system:

```
PLATFORM LEVEL (public schema)          CLAN LEVEL (clan-scoped, app-layer)
─────────────────────────────           ──────────────────────────
super_admin                             admin
  │                                       │
  ├── Manage all clans                   ├── Manage clan persons
  ├── Provision / suspend clans          ├── Approve new user registrations
  ├── View platform-wide metrics         ├── Assign editor/viewer roles
  ├── Promote/demote clan admins         └── Manage clan settings
  ├── Access all clan data (audit)
  └── Cannot be created via API          editor
      (bootstrap only)                     │
                                           ├── Create/edit persons
                                           ├── Create/edit marriages & parent-child
                                           ├── Upload documents
                                           └── Create/edit events

                                         viewer
                                           │
                                           └── Read-only access to all clan data
```

### Platform Level — `super_admin`

- Stored in `public.user_profiles` table with `platform_role = 'super_admin'`
- Exactly **one** super admin exists, created via `scripts/bootstrap_super_admin.py` — **never via API**
- Cannot be deleted via API — only via Supabase Dashboard directly
- All actions are audit-logged with `actor_id`, `action`, `target`, `timestamp`
- Checked via `user_profiles.platform_role` column (not JWT metadata)

### Clan Level — `admin`, `editor`, `viewer`

Stored in `public.user_clan_roles` table. A user may belong to **multiple clans** simultaneously — each with an independent role. The constraint `UNIQUE(user_id, clan_id)` ensures one role per user per clan.

The **active clan** is selected at runtime via the `X-Current-Clan-Id` request header (Slack-style workspace switcher). If a user belongs to exactly one clan and omits the header, that clan is auto-selected for zero-friction UX.

> **What the database enforces on this table, added 2026-08-22 by
> [ADR-050](../decisions/050-user-clan-roles-clan-keyed-mutations.md), migration `036`.**
> `user_clan_roles` is inside RLS layer 2 for **`UPDATE` and `DELETE` only**. Those two
> commands are keyed on the `app.clan_id` GUC, so the request role cannot approve, reject,
> re-role or remove a membership in a clan other than its active one, and cannot rewrite a
> row's `clan_id`. **`SELECT` and `INSERT` are permissive by decision**, because
> `get_current_clan_id` reads this table to decide which clan is active — before any clan is
> known — and `POST /auth/onboard` inserts the caller's own membership with no clan selected.
> So reads of this table have one layer of isolation (the application filters below) and the
> authority-changing writes have two. Two consequences for anyone changing roles code. **A
> mutating statement that reaches the table with no clan GUC set now matches zero rows rather
> than mutating**, which is fail-closed and silent, so check that your route carries
> `Depends(get_current_clan_id)`. And **a role check reads this table AFTER the GUC is set**
> (`backend/app/core/security.py:290`), which is why `require_role` still resolves correctly
> for a user holding different roles in two clans — pinned by
> `backend/tests/integration/test_rls_login_two_clans.py`.

## Full Permission Matrix

| Action                         | super_admin | admin | editor | viewer |
| ------------------------------ | ----------- | ----- | ------ | ------ |
| **CLAN**                       |             |       |        |        |
| View own clan info             | ✅           | ✅     | ✅      | ✅      |
| Edit clan info                 | ✅           | ✅     | ❌      | ❌      |
| Delete clan                    | ✅           | ❌     | ❌      | ❌      |
| View all clans (platform)      | ✅           | ❌     | ❌      | ❌      |
| Suspend/reactivate clan        | ✅           | ❌     | ❌      | ❌      |
| **PERSONS**                    |             |       |        |        |
| View persons                   | ✅           | ✅     | ✅      | ✅      |
| Create person                  | ✅           | ✅     | ✅      | ❌      |
| Edit person                    | ✅           | ✅     | ✅      | ❌      |
| Soft-delete person             | ✅           | ✅     | ❌      | ❌      |
| Restore deleted person         | ✅           | ✅     | ❌      | ❌      |
| Hard-delete person             | ✅           | ❌     | ❌      | ❌      |
| **CHANGE REQUESTS** (ADR-037)  |             |       |        |        |
| Submit a change request (`POST /change-requests`) | ✅ | ✅ | ✅ | ✅ |
| View own change requests        | ✅           | ✅     | ✅      | ✅      |
| View the clan's change-request queue | ✅      | ✅     | ✅      | ❌      |
| Approve a change request (applies the edit) | ✅ | ✅ | ✅  | ❌      |
| Reject a change request         | ✅           | ✅     | ✅      | ❌      |
| **MARRIAGES & PARENT-CHILD**   |             |       |        |        |
| View relationships             | ✅           | ✅     | ✅      | ✅      |
| Create marriage/parent-child   | ✅           | ✅     | ✅      | ❌      |
| Edit marriage/parent-child     | ✅           | ✅     | ✅      | ❌      |
| Delete marriage/parent-child   | ✅           | ✅     | ❌      | ❌      |
| **DOCUMENTS**                  |             |       |        |        |
| View documents                 | ✅           | ✅     | ✅      | ✅      |
| Upload document                | ✅           | ✅     | ✅      | ❌      |
| Delete document                | ✅           | ✅     | ❌      | ❌      |
| **EVENTS**                     |             |       |        |        |
| View events                    | ✅           | ✅     | ✅      | ✅      |
| Create/edit event              | ✅           | ✅     | ✅      | ❌      |
| Delete event                   | ✅           | ✅     | ✅      | ❌      |
| **FAMILY TREE**                |             |       |        |        |
| View family tree               | ✅           | ✅     | ✅      | ✅      |
| Export tree as PDF             | ✅           | ✅     | ✅      | ✅      |
| Designate/correct clan founder (thủy tổ, `PUT /clans/me/founder`, ADR-026) | ✅ | ✅ | ❌ | ❌ |
| **USER MANAGEMENT**            |             |       |        |        |
| View pending users             | ✅           | ✅     | ❌      | ❌      |
| Approve user registration      | ✅           | ✅     | ❌      | ❌      |
| Assign editor/viewer role      | ✅           | ✅     | ❌      | ❌      |
| Promote user to admin (`PATCH /me/users/{id}/role`) | ✅ | ✅ | ❌ | ❌ |
| Remove user from clan          | ✅           | ✅     | ❌      | ❌      |
| **AUDIT LOGS**                 |             |       |        |        |
| View clan audit log            | ✅           | ✅     | ❌      | ❌      |
| View platform audit log        | ✅           | ❌     | ❌      | ❌      |
| **INVITATIONS**                |             |       |        |        |
| Create clan invitation         | ✅           | ✅     | ❌      | ❌      |
| Revoke clan invitation         | ✅           | ✅     | ❌      | ❌      |
| View pending invitations       | ✅           | ✅     | ❌      | ❌      |
| **CLAN SETTINGS**              |             |       |        |        |
| View clan settings             | ✅           | ✅     | ✅      | ✅      |
| Edit clan settings             | ✅           | ✅     | ❌      | ❌      |
| **NOTIFICATIONS**              |             |       |        |        |
| Receive push notifications     | ✅           | ✅     | ✅      | ✅      |
| Configure notification settings| ✅           | ✅     | ✅      | ✅      |

### Why change-request review is editor-and-admin, not admin-only

An `editor` can already make the identical person edit unilaterally via
`PATCH /persons/{id}`. Routing the same edit through an admin because it arrived as a
proposal would protect nothing — it only adds latency, and a clan with one busy admin
would stall the whole correction queue. So approve/reject use the hierarchical
`RequireEditor` (editor **or** admin) rather than an explicit admin set.

For the same reason there is no self-approval ban: an editor who submits and then
approves their own proposal has done exactly what they could have done in one PATCH,
and both the submission and the approval are separately audit-logged. See ADR-037.

Submitting is open to every approved member (`RequireViewer`), but in practice
viewers are the users — everybody else can just make the edit. A viewer's list and
detail responses are scoped to their own proposals; another member's proposal returns
404, not 403 (ADR-021).

## Implementation

### Backend — FastAPI Dependency Injection

Permission checks use a dependency factory pattern in `backend/app/core/permissions.py`:

```python
from app.core.permissions import ClanRole, require_role, RequireEditor, RequireAdmin

# Option 1: inline dependency
@router.post("/persons", dependencies=[Depends(require_role(ClanRole.EDITOR))])

# Option 2: convenience constants
@router.post("/persons", dependencies=[RequireEditor])
@router.delete("/persons/{id}", dependencies=[RequireAdmin])
```

The `require_role()` dependency:
1. Extracts `user_id` from the JWT via `get_current_user()`
2. Queries `UserClanRole` table for the user's role and approval status
3. Compares against the role hierarchy: `viewer < editor < admin`
4. Returns 403 if the user's role is insufficient

Super admin access is handled separately via `get_super_admin()` in `backend/app/core/security.py`, which queries `user_profiles.platform_role`.

### Frontend

- Route guards check role before rendering pages
- UI elements conditionally shown based on role
- Admin panel only accessible to `admin` role

## User Approval Flow

1. Clan admin creates an invitation via `clan_invitations` (email + role + expiry token)
2. User receives invitation link, signs up via Supabase Auth
3. On first login, `ensure_user_profile()` lazily creates a `user_profiles` row from JWT claims
4. User accepts invitation → `user_clan_roles` row created with `is_approved = false`
5. Clan admin reviews and approves/rejects via Admin Panel
6. Upon approval, user can access clan data with the assigned role
7. Admin can upgrade role (viewer → editor) or remove user from clan

## Super Admin API Endpoints

| Method | Path                                         | Description                  |
| ------ | -------------------------------------------- | ---------------------------- |
| GET    | `/api/v1/platform/clans`                     | List all clans on platform   |
| POST   | `/api/v1/platform/clans/{id}/suspend`        | Suspend a clan               |
| POST   | `/api/v1/platform/clans/{id}/reactivate`     | Reactivate a clan            |
| GET    | `/api/v1/platform/metrics`                   | Platform-wide usage metrics  |
| GET    | `/api/v1/platform/audit-log`                 | Cross-clan audit log         |

(There is **no** platform endpoint to promote clan admins — clan-role changes happen
inside the clan via `PATCH /api/v1/clans/me/users/{user_id}/role`, admin-only, with
last-admin-cannot-demote protection.)

### Security Rules

- No API endpoint to create super admin — bootstrap script only
- No API endpoint to promote to super admin — this role cannot be granted via app
- Super admin cannot be deleted via API — only via Supabase Dashboard
- Super admin status stored in `user_profiles.platform_role` (queried from DB, not JWT metadata)
- User profiles created lazily on first login via `ensure_user_profile()` (no Supabase webhook needed)

### Additional authorization gates (before role checks)

- **Deactivated account** — `user_profiles.is_active = false` → 403 `account_deactivated`
  on any authenticated route.
- **Suspended clan** — clan status suspended → 403 `clan_suspended` on clan-scoped routes.
- **Unverified email** — login itself fails 403 `email_not_verified` until the Supabase
  email is confirmed.
- Roles only apply after membership `is_approved = true`; pending members cannot act.
