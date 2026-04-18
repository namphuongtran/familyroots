import test from 'node:test'
import assert from 'node:assert/strict'

import {
  deriveCapabilities,
} from '../../src/application/auth/use-cases/capabilities.ts'
import {
  hydrateAuthContext,
  mapSessionUserToProfile,
  selectActiveClan,
} from '../../src/application/auth/use-cases/auth-context.ts'
import {
  documentDeleteInvalidationKeys,
  documentUploadInvalidationKeys,
  eventMutationInvalidationKeys,
  personCreateInvalidationKeys,
  personDeleteInvalidationKeys,
  personUpdateInvalidationKeys,
} from '../../src/lib/hooks/query-invalidation.ts'

test('mapSessionUserToProfile keeps session fallback identity-only', () => {
  const profile = mapSessionUserToProfile({
    id: 'user-1',
    email: 'user@example.com',
    metadata: {
      full_name: 'Example User',
      preferred_locale: 'en',
      role: 'admin',
      clan_id: 'clan-1',
      platform_role: 'super_admin',
    },
  })

  assert.deepEqual(profile, {
    id: 'user-1',
    email: 'user@example.com',
    full_name: 'Example User',
    clan_id: undefined,
    clan_name: undefined,
    role: undefined,
    is_approved: false,
    has_pending_membership: false,
    person_id: undefined,
    preferred_locale: 'en',
    platform_role: undefined,
  })
})

test('hydrateAuthContext merges backend profile and memberships and resolves preferred clan', async () => {
  const sessionPort = {
    async getSessionUser() {
      return {
        id: 'user-1',
        email: 'user@example.com',
        metadata: { full_name: 'Fallback Name', preferred_locale: 'vi' },
      }
    },
  }

  const profileRepository = {
    async getMe() {
      return {
        id: 'user-1',
        email: 'user@example.com',
        full_name: 'Backend Name',
        clan_id: 'clan-2',
        clan_name: 'Clan Two',
        role: 'viewer',
        is_approved: true,
        has_pending_membership: false,
        person_id: 'person-1',
        preferred_locale: 'fr',
        platform_role: null,
      }
    },
    async listMyClans() {
      return {
        count: 2,
        clans: [
          { clan_id: 'clan-1', clan_name: 'Clan One', clan_slug: 'one', role: 'editor', joined_at: null },
          { clan_id: 'clan-2', clan_name: 'Clan Two', clan_slug: 'two', role: 'viewer', joined_at: null },
        ],
      }
    },
    async selectClan() {
      throw new Error('not used')
    },
    async onboard() {
      throw new Error('not used')
    },
    async register() {
      throw new Error('not used')
    },
    async updateMe() {
      throw new Error('not used')
    },
  }

  const result = await hydrateAuthContext(sessionPort as never, profileRepository as never, 'clan-1')

  assert.equal(result.user?.full_name, 'Backend Name')
  assert.equal(result.user?.preferred_locale, 'fr')
  assert.equal(result.currentClanId, 'clan-1')
  assert.equal(result.activeMembership?.role, 'editor')
  assert.equal(result.user?.role, 'editor')
  assert.equal(result.isPendingApproval, false)
  assert.equal(result.needsOnboarding, false)
  assert.equal(result.needsClanSelection, false)
})

test('hydrateAuthContext marks pending approval when backend returns no clan memberships', async () => {
  const sessionPort = {
    async getSessionUser() {
      return {
        id: 'user-2',
        email: 'pending@example.com',
        metadata: {},
      }
    },
  }

  const profileRepository = {
    async getMe() {
      return {
        id: 'user-2',
        email: 'pending@example.com',
        full_name: 'Pending User',
        is_approved: false,
        has_pending_membership: true,
        preferred_locale: 'vi',
      }
    },
    async listMyClans() {
      return { count: 0, clans: [] }
    },
  }

  const result = await hydrateAuthContext(sessionPort as never, profileRepository as never)

  assert.equal(result.isPendingApproval, true)
  assert.equal(result.needsOnboarding, false)
  assert.equal(result.needsClanSelection, false)
  assert.equal(result.currentClanId, undefined)
})

test('hydrateAuthContext marks onboarding required when user has no clan memberships or pending requests', async () => {
  const sessionPort = {
    async getSessionUser() {
      return {
        id: 'user-3',
        email: 'oauth@example.com',
        metadata: { full_name: 'OAuth User' },
      }
    },
  }

  const profileRepository = {
    async getMe() {
      return {
        id: 'user-3',
        email: 'oauth@example.com',
        full_name: 'OAuth User',
        is_approved: false,
        has_pending_membership: false,
        preferred_locale: 'en',
      }
    },
    async listMyClans() {
      return { count: 0, clans: [] }
    },
  }

  const result = await hydrateAuthContext(sessionPort as never, profileRepository as never)

  assert.equal(result.isPendingApproval, false)
  assert.equal(result.needsOnboarding, true)
  assert.equal(result.needsClanSelection, false)
})

test('selectActiveClan delegates to repository and returns backend clan id', async () => {
  const calls: string[] = []
  const repository = {
    async selectClan(clanId: string) {
      calls.push(clanId)
      return {
        clan_id: clanId,
        clan_name: 'Selected Clan',
        clan_slug: 'selected',
        role: 'admin',
        message: 'ok',
      }
    },
  }

  const result = await selectActiveClan(repository as never, 'clan-9')

  assert.equal(result, 'clan-9')
  assert.deepEqual(calls, ['clan-9'])
})

test('deriveCapabilities respects clan context, approval state, and role hierarchy', () => {
  const viewer = deriveCapabilities(
    { id: '1', email: 'v@example.com', full_name: 'Viewer', role: 'viewer', is_approved: true, preferred_locale: 'vi' },
    { hasActiveClan: true, isPendingApproval: false },
  )
  const editor = deriveCapabilities(
    { id: '2', email: 'e@example.com', full_name: 'Editor', role: 'editor', is_approved: true, preferred_locale: 'vi' },
    { hasActiveClan: true, isPendingApproval: false },
  )
  const admin = deriveCapabilities(
    { id: '3', email: 'a@example.com', full_name: 'Admin', role: 'admin', is_approved: true, preferred_locale: 'vi' },
    { hasActiveClan: true, isPendingApproval: false },
  )
  const superAdmin = deriveCapabilities(
    { id: '4', email: 's@example.com', full_name: 'Super', role: 'viewer', platform_role: 'super_admin', is_approved: true, preferred_locale: 'vi' },
    { hasActiveClan: true, isPendingApproval: false },
  )

  assert.equal(viewer.canEditPersons, false)
  assert.equal(editor.canEditPersons, true)
  assert.equal(editor.canDeleteDocuments, false)
  assert.equal(admin.canDeleteDocuments, true)
  assert.equal(superAdmin.canAccessPlatform, true)
  assert.equal(
    deriveCapabilities(
      { id: '5', email: 'p@example.com', full_name: 'Pending', role: 'admin', is_approved: false, preferred_locale: 'vi' },
      { hasActiveClan: true, isPendingApproval: true },
    ).canManageClan,
    false,
  )
})

test('person invalidation helpers cover list, detail, and tree refreshes', () => {
  assert.deepEqual(personCreateInvalidationKeys(), [['persons', 'list'], ['tree']])
  assert.deepEqual(personUpdateInvalidationKeys('p-1'), [['persons', 'detail', 'p-1'], ['persons', 'list'], ['tree']])
  assert.deepEqual(personDeleteInvalidationKeys('p-2'), [['persons', 'detail', 'p-2'], ['persons', 'list'], ['tree']])
})

test('document invalidation helpers cover person document/detail refreshes when linked', () => {
  assert.deepEqual(documentDeleteInvalidationKeys(), [['documents']])
  assert.deepEqual(documentUploadInvalidationKeys(), [['documents']])
  assert.deepEqual(documentUploadInvalidationKeys('person-1'), [
    ['documents'],
    ['persons', 'detail', 'person-1', 'documents'],
    ['persons', 'detail', 'person-1'],
  ])
})

test('event invalidation helpers cover list, upcoming, detail, and person timeline refreshes', () => {
  assert.deepEqual(eventMutationInvalidationKeys(), [['events', 'list'], ['events', 'upcoming', 30]])
  assert.deepEqual(eventMutationInvalidationKeys({ detailId: 'e-1', personId: 'p-1' }), [
    ['events', 'list'],
    ['events', 'upcoming', 30],
    ['events', 'detail', 'e-1'],
    ['persons', 'detail', 'p-1', 'timeline'],
  ])
})
