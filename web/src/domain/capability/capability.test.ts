import { describe, expect, it } from 'vitest'
import {
  CLAN_ROLES,
  getCapabilities,
  hasCapability,
  type CapabilitySet,
  type ClanRole,
} from './capability'

// Written independently of `ROLE_CAPABILITIES` in capability.ts, straight from the matrix
// rows cited in that file's comments, so this test cannot pass by echoing the
// implementation's own table back at itself.

const ADMIN: CapabilitySet = {
  editClanInfo: true,
  createPerson: true,
  editPerson: true,
  softDeletePerson: true,
  restorePerson: true,
  viewChangeRequestQueue: true,
  approveChangeRequest: true,
  rejectChangeRequest: true,
  createRelationship: true,
  editRelationship: true,
  deleteRelationship: true,
  uploadDocument: true,
  deleteDocument: true,
  createOrEditEvent: true,
  deleteEvent: true,
  designateFounder: true,
  viewPendingUsers: true,
  approveUserRegistration: true,
  assignMemberRole: true,
  promoteToAdmin: true,
  removeMemberFromClan: true,
  viewClanAuditLog: true,
  createInvitation: true,
  revokeInvitation: true,
  viewPendingInvitations: true,
  editClanSettings: true,
}

const EDITOR: CapabilitySet = {
  editClanInfo: false,
  createPerson: true,
  editPerson: true,
  softDeletePerson: false,
  restorePerson: false,
  viewChangeRequestQueue: true,
  approveChangeRequest: true,
  rejectChangeRequest: true,
  createRelationship: true,
  editRelationship: true,
  deleteRelationship: false,
  uploadDocument: true,
  deleteDocument: false,
  createOrEditEvent: true,
  // rbac.md:78 — event deletion is admin-and-editor, unlike person/relationship/document
  // deletion, which are admin-only. This is the one row where editor does not follow the
  // "editor creates and edits, admin also deletes" pattern the other four resources share.
  deleteEvent: true,
  designateFounder: false,
  viewPendingUsers: false,
  approveUserRegistration: false,
  assignMemberRole: false,
  promoteToAdmin: false,
  removeMemberFromClan: false,
  viewClanAuditLog: false,
  createInvitation: false,
  revokeInvitation: false,
  viewPendingInvitations: false,
  editClanSettings: false,
}

// The least privileged role in the hierarchy (rbac.md:5-27, "viewer" sits under "editor"
// under "admin"). Every gated action in the matrix denies viewer, so this is the all-false
// set — and it is asserted explicitly, not assumed, because an all-false expectation is the
// easiest one to get "accidentally right" by returning `{}` or throwing.
const VIEWER: CapabilitySet = {
  editClanInfo: false,
  createPerson: false,
  editPerson: false,
  softDeletePerson: false,
  restorePerson: false,
  viewChangeRequestQueue: false,
  approveChangeRequest: false,
  rejectChangeRequest: false,
  createRelationship: false,
  editRelationship: false,
  deleteRelationship: false,
  uploadDocument: false,
  deleteDocument: false,
  createOrEditEvent: false,
  deleteEvent: false,
  designateFounder: false,
  viewPendingUsers: false,
  approveUserRegistration: false,
  assignMemberRole: false,
  promoteToAdmin: false,
  removeMemberFromClan: false,
  viewClanAuditLog: false,
  createInvitation: false,
  revokeInvitation: false,
  viewPendingInvitations: false,
  editClanSettings: false,
}

const EXPECTED: Record<ClanRole, CapabilitySet> = { admin: ADMIN, editor: EDITOR, viewer: VIEWER }

describe('getCapabilities', () => {
  it('covers every role in the hierarchy — none is skipped', () => {
    expect(CLAN_ROLES).toEqual(['admin', 'editor', 'viewer'])
  })

  for (const role of CLAN_ROLES) {
    it(`derives the exact capability set rbac.md's matrix assigns to "${role}"`, () => {
      expect(getCapabilities(role)).toEqual(EXPECTED[role])
    })
  }

  it('gives the least privileged role, viewer, no capability at all', () => {
    const capabilities = getCapabilities('viewer')
    expect(Object.values(capabilities).every((granted) => granted === false)).toBe(true)
  })

  it('nests admin over editor over viewer, as rbac.md draws the hierarchy', () => {
    const admin = getCapabilities('admin')
    const editor = getCapabilities('editor')
    const viewer = getCapabilities('viewer')
    for (const capability of Object.keys(admin) as Array<keyof CapabilitySet>) {
      if (viewer[capability]) expect(editor[capability]).toBe(true)
      if (editor[capability]) expect(admin[capability]).toBe(true)
    }
  })
})

describe('hasCapability', () => {
  it('agrees with getCapabilities for every role and capability', () => {
    for (const role of CLAN_ROLES) {
      const set = getCapabilities(role)
      for (const capability of Object.keys(set) as Array<keyof CapabilitySet>) {
        expect(hasCapability(role, capability)).toBe(set[capability])
      }
    }
  })
})
