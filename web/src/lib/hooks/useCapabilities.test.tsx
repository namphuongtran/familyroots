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
import { describe, expect, it, vi } from 'vitest'
import { useCapabilities } from './useCapabilities'
import { accessStateOf, useSession } from '@/features/auth'
import type { Membership, Session } from '@/features/auth'
import { renderWithProviders } from '@/shared/testing/render'

/**
 * #183: the hook reads the role from the session's access state, so each case builds a session
 * and a cookie and lets the real `accessStateOf` decide, rather than setting a role on a store.
 */
vi.mock('@/features/auth', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/auth')>()),
  useSession: vi.fn(),
}))

const CLAN_A = '4bf92f35-77b3-4da6-a3ce-929d0e0e4736'
const CLAN_B = 'bbbbbbbb-0000-4000-8000-000000000002'

function membership(clanId: string, role: string): Membership {
  return { clanId, clanName: 'Dòng họ', clanSlug: clanId, role }
}

function setSession(
  memberships: Membership[],
  options: { cookieClanId?: string | null; pending?: boolean } = {},
) {
  const session: Session = {
    profile: {
      userId: 'user-1',
      email: 'user@example.com',
      fullName: 'Test User',
      preferredLocale: 'vi',
      platformRole: 'user',
      hasPendingMembership: options.pending ?? false,
    },
    memberships,
  }
  vi.mocked(useSession).mockReturnValue({
    session,
    access: accessStateOf(session, options.cookieClanId ?? null),
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  })
}

function CapabilitiesProbe() {
  const capabilities = useCapabilities()
  return <div data-testid="capabilities">{JSON.stringify(capabilities)}</div>
}

function readCapabilities() {
  renderWithProviders(<CapabilitiesProbe />)
  return JSON.parse(screen.getByTestId('capabilities').textContent ?? '{}')
}

describe('useCapabilities, rewired onto domain/capability', () => {
  it('grants an admin every one of the four capabilities a component reads', () => {
    setSession([membership(CLAN_A, 'admin')], { cookieClanId: CLAN_A })

    expect(readCapabilities()).toEqual({
      canEditPersons: true,
      canUploadDocuments: true,
      canDeleteDocuments: true,
      canEditRelationships: true,
    })
  })

  it("matches rbac.md's editor row: create/edit and upload, never delete a document", () => {
    setSession([membership(CLAN_A, 'editor')], { cookieClanId: CLAN_A })

    expect(readCapabilities()).toEqual({
      canEditPersons: true,
      canUploadDocuments: true,
      canDeleteDocuments: false,
      canEditRelationships: true,
    })
  })

  it('denies a viewer all four', () => {
    setSession([membership(CLAN_A, 'viewer')], { cookieClanId: CLAN_A })

    expect(readCapabilities()).toEqual({
      canEditPersons: false,
      canUploadDocuments: false,
      canDeleteDocuments: false,
      canEditRelationships: false,
    })
  })

  it('denies an admin of two clans who has selected neither — an active clan is a precondition, not just a role check', () => {
    setSession([membership(CLAN_A, 'admin'), membership(CLAN_B, 'admin')])

    expect(readCapabilities()).toEqual({
      canEditPersons: false,
      canUploadDocuments: false,
      canDeleteDocuments: false,
      canEditRelationships: false,
    })
  })

  it('denies a user still pending approval, even with a clan cookie already set', () => {
    setSession([], { cookieClanId: CLAN_A, pending: true })

    expect(readCapabilities()).toEqual({
      canEditPersons: false,
      canUploadDocuments: false,
      canDeleteDocuments: false,
      canEditRelationships: false,
    })
  })
})
