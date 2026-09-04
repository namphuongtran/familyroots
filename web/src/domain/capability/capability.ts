/**
 * Clan-scoped capabilities, derived from a role — never sent by the backend and never
 * invented here. The backend enforces the real permission check on every request
 * (`backend/app/core/permissions.py`, `require_role()`); this module only decides what the
 * client *offers* to render, from the same rule the backend uses.
 *
 * Every capability below is one row of the "Full Permission Matrix" in
 * `docs/architecture/rbac.md` (lines 43-101), restricted to the three clan-scoped roles.
 * `super_admin` is platform-level, not clan-scoped (rbac.md lines 29-36), and is out of
 * scope for this module. A row where
 * `super_admin` is the only ✅ (delete clan, view all clans, suspend/reactivate clan,
 * hard-delete person, view platform audit log — rbac.md lines 50-52, 59, 91) is therefore
 * not modelled here at all: it is always false for every clan role, so it gates nothing a
 * clan-scoped screen could show anyway.
 *
 * A row where admin, editor *and* viewer are all ✅ (view persons/relationships/documents/
 * events/tree, export tree, submit or view a change request, notifications) is likewise not
 * modelled: every role already gets it, so it is not something a screen conditionally
 * renders on role.
 *
 * Kept pure per `web/CLAUDE.md`, "Dependency rules": no React, no store, no `apiFetch`.
 * `domain-is-pure` and `domain-imports-only-domain` (`web/.dependency-cruiser.cjs`) fail the
 * build if this file reaches for either.
 */

/** The three clan-scoped roles (rbac.md line 37). Platform's `super_admin` is not one of them. */
export type ClanRole = 'admin' | 'editor' | 'viewer'

export const CLAN_ROLES: readonly ClanRole[] = ['admin', 'editor', 'viewer']

/**
 * One entry per rbac.md matrix row where at least one clan role is denied. The comment on
 * each names the exact row it comes from.
 */
export type Capability =
  /** rbac.md:49 "Edit clan info" — admin ✅, editor ❌, viewer ❌ */
  | 'editClanInfo'
  /** rbac.md:55 "Create person" — admin ✅, editor ✅, viewer ❌ */
  | 'createPerson'
  /** rbac.md:56 "Edit person" — admin ✅, editor ✅, viewer ❌ */
  | 'editPerson'
  /** rbac.md:57 "Soft-delete person" — admin ✅, editor ❌, viewer ❌ */
  | 'softDeletePerson'
  /** rbac.md:58 "Restore deleted person" — admin ✅, editor ❌, viewer ❌ */
  | 'restorePerson'
  /** rbac.md:63 "View the clan's change-request queue" — admin ✅, editor ✅, viewer ❌ */
  | 'viewChangeRequestQueue'
  /** rbac.md:64 "Approve a change request" — admin ✅, editor ✅, viewer ❌ */
  | 'approveChangeRequest'
  /** rbac.md:65 "Reject a change request" — admin ✅, editor ✅, viewer ❌ */
  | 'rejectChangeRequest'
  /** rbac.md:68 "Create marriage/parent-child" — admin ✅, editor ✅, viewer ❌ */
  | 'createRelationship'
  /** rbac.md:69 "Edit marriage/parent-child" — admin ✅, editor ✅, viewer ❌ */
  | 'editRelationship'
  /** rbac.md:70 "Delete marriage/parent-child" — admin ✅, editor ❌, viewer ❌ */
  | 'deleteRelationship'
  /** rbac.md:73 "Upload document" — admin ✅, editor ✅, viewer ❌ */
  | 'uploadDocument'
  /** rbac.md:74 "Delete document" — admin ✅, editor ❌, viewer ❌ */
  | 'deleteDocument'
  /** rbac.md:77 "Create/edit event" — admin ✅, editor ✅, viewer ❌ */
  | 'createOrEditEvent'
  /**
   * rbac.md:78 "Delete event" — admin ✅, editor ✅, viewer ❌. Unlike persons, relationships
   * and documents, event deletion is *not* admin-only: rbac.md draws this line differently
   * for events than for the other four resource families. Read the row, do not assume the
   * pattern from the other four.
   */
  | 'deleteEvent'
  /** rbac.md:82 "Designate/correct clan founder (thủy tổ)" — admin ✅, editor ❌, viewer ❌ */
  | 'designateFounder'
  /** rbac.md:84 "View pending users" — admin ✅, editor ❌, viewer ❌ */
  | 'viewPendingUsers'
  /** rbac.md:85 "Approve user registration" — admin ✅, editor ❌, viewer ❌ */
  | 'approveUserRegistration'
  /** rbac.md:86 "Assign editor/viewer role" — admin ✅, editor ❌, viewer ❌ */
  | 'assignMemberRole'
  /** rbac.md:87 "Promote user to admin" — admin ✅, editor ❌, viewer ❌ */
  | 'promoteToAdmin'
  /** rbac.md:88 "Remove user from clan" — admin ✅, editor ❌, viewer ❌ */
  | 'removeMemberFromClan'
  /** rbac.md:90 "View clan audit log" — admin ✅, editor ❌, viewer ❌ */
  | 'viewClanAuditLog'
  /** rbac.md:93 "Create clan invitation" — admin ✅, editor ❌, viewer ❌ */
  | 'createInvitation'
  /** rbac.md:94 "Revoke clan invitation" — admin ✅, editor ❌, viewer ❌ */
  | 'revokeInvitation'
  /** rbac.md:95 "View pending invitations" — admin ✅, editor ❌, viewer ❌ */
  | 'viewPendingInvitations'
  /** rbac.md:98 "Edit clan settings" — admin ✅, editor ❌, viewer ❌ */
  | 'editClanSettings'

/** Every capability, in the order declared above. Used to build a full `CapabilitySet`. */
const ALL_CAPABILITIES: readonly Capability[] = [
  'editClanInfo',
  'createPerson',
  'editPerson',
  'softDeletePerson',
  'restorePerson',
  'viewChangeRequestQueue',
  'approveChangeRequest',
  'rejectChangeRequest',
  'createRelationship',
  'editRelationship',
  'deleteRelationship',
  'uploadDocument',
  'deleteDocument',
  'createOrEditEvent',
  'deleteEvent',
  'designateFounder',
  'viewPendingUsers',
  'approveUserRegistration',
  'assignMemberRole',
  'promoteToAdmin',
  'removeMemberFromClan',
  'viewClanAuditLog',
  'createInvitation',
  'revokeInvitation',
  'viewPendingInvitations',
  'editClanSettings',
]

export type CapabilitySet = Readonly<Record<Capability, boolean>>

/**
 * Capabilities held by each clan role, taken directly from rbac.md's matrix rather than
 * computed from a hierarchy. Every row the matrix publishes happens to nest — admin holds
 * everything editor holds, and editor holds everything viewer holds — but this table states
 * that outcome per role rather than assuming it, so a role missing here is a bug this table
 * cannot silently paper over the way a `minRole` comparison would.
 */
const ROLE_CAPABILITIES: Record<ClanRole, readonly Capability[]> = {
  admin: ALL_CAPABILITIES,
  editor: [
    'createPerson',
    'editPerson',
    'viewChangeRequestQueue',
    'approveChangeRequest',
    'rejectChangeRequest',
    'createRelationship',
    'editRelationship',
    'uploadDocument',
    'createOrEditEvent',
    'deleteEvent',
  ],
  viewer: [],
}

/** The full capability set for a role: every `Capability` key, `true` where the role holds it. */
export function getCapabilities(role: ClanRole): CapabilitySet {
  const granted = new Set<Capability>(ROLE_CAPABILITIES[role])
  const set = {} as Record<Capability, boolean>
  for (const capability of ALL_CAPABILITIES) {
    set[capability] = granted.has(capability)
  }
  return set
}

export function hasCapability(role: ClanRole, capability: Capability): boolean {
  return ROLE_CAPABILITIES[role].includes(capability)
}
