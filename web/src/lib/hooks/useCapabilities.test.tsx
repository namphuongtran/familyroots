/**
 * the legacy-transport deletion rewired `useCapabilities` off the deleted
 * `src/application/auth/use-cases/capabilities.ts` and onto
 * `src/domain/capability/capability.ts` — see that hook's own doc comment. This file
 * replaces the coverage `tests/behavior/auth-and-invalidation.test.ts` used to carry for the
 * deleted module's `deriveCapabilities`, for the four capability names a real component still
 * reads (`grep -rn "useCapabilities()" src`).
 *
 * Each case renders the hook through a host component — the same shape
 * `src/shared/http/clan-switch.test.tsx` uses for `useCurrentClanId` — rather than asserting
 * on a store field or a role string, per `.claude/rules/testing.md`'s "a test pins an outcome,
 * not a setting": the outcome here is which of the four booleans a real render produces.
 */
import { screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { useCapabilities } from './useCapabilities'
import { CLAN_COOKIE } from '@/shared/http/request-context'
import { renderWithProviders } from '@/shared/testing/render'
import { useAuthStore } from '@/store/auth.store'
import type { UserProfile } from '@/lib/types'

function setClanCookie(clanId: string | null) {
  // jsdom keeps a cookie around between assignments (same trap
  // `clan-switch.test.tsx` documents), so clear the slot before writing.
  document.cookie = `${CLAN_COOKIE}=; path=/; max-age=0`
  if (clanId !== null) {
    document.cookie = `${CLAN_COOKIE}=${encodeURIComponent(clanId)}; path=/`
  }
}

function setSession(role: UserProfile['role'], options?: { isPendingApproval?: boolean }) {
  useAuthStore.getState().setUser({
    id: 'user-1',
    email: 'user@example.com',
    full_name: 'Test User',
    clan_id: 'clan-1',
    role,
    is_approved: true,
    preferred_locale: 'vi',
  })
  useAuthStore.getState().setAccessState({
    isPendingApproval: options?.isPendingApproval ?? false,
    needsOnboarding: false,
    needsClanSelection: false,
  })
}

function CapabilitiesProbe() {
  const capabilities = useCapabilities()
  return <div data-testid="capabilities">{JSON.stringify(capabilities)}</div>
}

async function readCapabilities() {
  renderWithProviders(<CapabilitiesProbe />)
  return JSON.parse(screen.getByTestId('capabilities').textContent ?? '{}')
}

const CLAN_A = '4bf92f35-77b3-4da6-a3ce-929d0e0e4736'

describe('useCapabilities, rewired onto domain/capability', () => {
  afterEach(() => {
    setClanCookie(null)
    useAuthStore.getState().clear()
  })

  it('grants an admin every one of the four capabilities a component reads', async () => {
    setClanCookie(CLAN_A)
    setSession('admin')

    expect(await readCapabilities()).toEqual({
      canEditPersons: true,
      canUploadDocuments: true,
      canDeleteDocuments: true,
      canEditRelationships: true,
    })
  })

  it("matches rbac.md's editor row: create/edit and upload, never delete a document", async () => {
    setClanCookie(CLAN_A)
    setSession('editor')

    expect(await readCapabilities()).toEqual({
      canEditPersons: true,
      canUploadDocuments: true,
      canDeleteDocuments: false,
      canEditRelationships: true,
    })
  })

  it('denies a viewer all four', async () => {
    setClanCookie(CLAN_A)
    setSession('viewer')

    expect(await readCapabilities()).toEqual({
      canEditPersons: false,
      canUploadDocuments: false,
      canDeleteDocuments: false,
      canEditRelationships: false,
    })
  })

  it('denies an admin with no active clan selected — hasActiveClan is a precondition, not just a role check', async () => {
    setClanCookie(null)
    setSession('admin')

    expect(await readCapabilities()).toEqual({
      canEditPersons: false,
      canUploadDocuments: false,
      canDeleteDocuments: false,
      canEditRelationships: false,
    })
  })

  it('denies an admin still pending approval, even with a clan cookie already set', async () => {
    setClanCookie(CLAN_A)
    setSession('admin', { isPendingApproval: true })

    expect(await readCapabilities()).toEqual({
      canEditPersons: false,
      canUploadDocuments: false,
      canDeleteDocuments: false,
      canEditRelationships: false,
    })
  })
})
