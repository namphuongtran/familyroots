import { act, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { CLAN_ROLES, getCapabilities, type CapabilitySet } from '@/domain/capability/capability'
import type { components } from '@/generated/api-types'
import { clearClanCookie, writeClanCookie } from '@/shared/http/context.client'
import { createClientOrNull } from '@/shared/supabase/client'
import { envelope, server } from '@/shared/testing/msw'
import { renderWithProviders } from '@/shared/testing/render'
import { fakeSupabaseClient } from '@/shared/testing/supabase'
import { useCapabilities } from './use-capabilities'
import { useSession } from './use-session'

/**
 * #185, ADR-061 § 4: the hook returns the domain `CapabilitySet` for the active clan's role, and
 * every capability false otherwise. It replaces the legacy hook's test in `lib/hooks/`, which
 * mocked `useSession` and read four renamed booleans.
 *
 * The real session hook runs here: the real repository sends `GET /auth/me` and `GET /me/clans`,
 * and MSW answers with real envelopes. Only the Supabase browser client is a fake. Each case reads
 * the access state from the same render as the capabilities, and waits for it to settle before
 * reading them, because every capability is also false while the session is still loading. A
 * case that read "nothing granted" before the session arrived would pass whatever the hook did
 * with the session.
 */

vi.mock('@/shared/supabase/client', () => ({ createClientOrNull: vi.fn() }))

const API = `${process.env.NEXT_PUBLIC_API_ORIGIN ?? 'http://localhost:8000'}/api/v1`
const CLAN_A = 'aaaaaaaa-0000-4000-8000-000000000001'
const CLAN_B = 'bbbbbbbb-0000-4000-8000-000000000002'

function profile(pending = false): components['schemas']['UserProfile'] {
  return {
    id: '11111111-1111-4111-8111-111111111111',
    email: 'lan@example.com',
    full_name: 'Nguyễn Thị Lan',
    clan_id: null,
    clan_name: null,
    role: null,
    is_approved: !pending,
    has_pending_membership: pending,
    person_id: null,
    preferred_locale: 'vi',
    platform_role: 'user',
  }
}

function membership(clanId: string, role: string): components['schemas']['UserClanMembership'] {
  return { clan_id: clanId, clan_name: `Dòng họ ${clanId[0]}`, clan_slug: clanId, role }
}

function serveSession(
  memberships: components['schemas']['UserClanMembership'][],
  options: { pending?: boolean } = {},
) {
  const count = { me: 0, clans: 0 }
  server.use(
    http.get(`${API}/auth/me`, () => {
      count.me += 1
      return HttpResponse.json(envelope(profile(options.pending)))
    }),
    http.get(`${API}/me/clans`, () => {
      count.clans += 1
      return HttpResponse.json(envelope(memberships))
    }),
  )
  return count
}

function Probe() {
  const { access } = useSession()
  const capabilities = useCapabilities()
  return (
    <>
      <p data-testid="access">{access === null ? 'loading' : access.kind}</p>
      <p data-testid="capabilities">{JSON.stringify(capabilities)}</p>
    </>
  )
}

function readCapabilities(): CapabilitySet {
  return JSON.parse(screen.getByTestId('capabilities').textContent ?? '{}') as CapabilitySet
}

function granted(capabilities: CapabilitySet): string[] {
  return Object.entries(capabilities)
    .filter(([, isGranted]) => isGranted)
    .map(([capability]) => capability)
}

const EVERY_KEY = Object.keys(getCapabilities('admin')).sort()

async function settledOn(kind: string): Promise<CapabilitySet> {
  await waitFor(() => expect(screen.getByTestId('access')).toHaveTextContent(kind))
  const capabilities = readCapabilities()
  // A full set, whatever it grants: a caller may read any key.
  expect(Object.keys(capabilities).sort()).toEqual(EVERY_KEY)
  return capabilities
}

beforeEach(() => {
  vi.mocked(createClientOrNull).mockReturnValue(
    fakeSupabaseClient({ accessToken: 'tok-1' }).client as never,
  )
})

afterEach(() => {
  clearClanCookie()
})

describe('useCapabilities: the domain CapabilitySet of the active clan', () => {
  for (const role of CLAN_ROLES) {
    it(`a ${role} of the active clan holds getCapabilities('${role}')`, async () => {
      serveSession([membership(CLAN_A, role)])
      writeClanCookie(CLAN_A)

      renderWithProviders(<Probe />)

      expect(await settledOn('ready')).toEqual(getCapabilities(role))
    })
  }

  it("draws rbac.md's document line for an editor: upload, never delete", async () => {
    serveSession([membership(CLAN_A, 'editor')])
    writeClanCookie(CLAN_A)

    renderWithProviders(<Probe />)
    const capabilities = await settledOn('ready')

    expect(capabilities.editPerson).toBe(true)
    expect(capabilities.uploadDocument).toBe(true)
    expect(capabilities.deleteDocument).toBe(false)
  })

  it('follows a clan switch to the role held there, with no second session read', async () => {
    const count = serveSession([membership(CLAN_A, 'admin'), membership(CLAN_B, 'editor')])
    writeClanCookie(CLAN_A)

    renderWithProviders(<Probe />)
    expect(await settledOn('ready')).toEqual(getCapabilities('admin'))

    act(() => writeClanCookie(CLAN_B))

    // Editor, not viewer, in clan B: a viewer's set is all false, which is also what a switch
    // that lost the active clan would read.
    await waitFor(() => expect(readCapabilities()).toEqual(getCapabilities('editor')))
    expect(screen.getByTestId('access')).toHaveTextContent('ready')
    expect(count).toEqual({ me: 1, clans: 1 })
  })
})

describe('useCapabilities: every capability false without a clan role', () => {
  it('while the session is still loading', () => {
    serveSession([membership(CLAN_A, 'admin')])
    writeClanCookie(CLAN_A)

    renderWithProviders(<Probe />)

    expect(screen.getByTestId('access')).toHaveTextContent('loading')
    expect(granted(readCapabilities())).toEqual([])
  })

  it('signed out, with no session read at all', async () => {
    vi.mocked(createClientOrNull).mockReturnValue(
      fakeSupabaseClient({ accessToken: null }).client as never,
    )
    const count = serveSession([membership(CLAN_A, 'admin')])
    writeClanCookie(CLAN_A)

    renderWithProviders(<Probe />)

    expect(granted(await settledOn('signed-out'))).toEqual([])
    expect(count).toEqual({ me: 0, clans: 0 })
  })

  it('an admin of two clans who has selected neither', async () => {
    serveSession([membership(CLAN_A, 'admin'), membership(CLAN_B, 'admin')])

    renderWithProviders(<Probe />)

    expect(granted(await settledOn('needs-clan-selection'))).toEqual([])
  })

  it('a user still pending approval, even with a clan cookie already set', async () => {
    serveSession([], { pending: true })
    writeClanCookie(CLAN_A)

    renderWithProviders(<Probe />)

    expect(granted(await settledOn('pending-approval'))).toEqual([])
  })

  it('a membership whose role is not one of the three clan roles', async () => {
    serveSession([membership(CLAN_A, 'owner')])
    writeClanCookie(CLAN_A)

    renderWithProviders(<Probe />)

    expect(granted(await settledOn('ready'))).toEqual([])
  })
})
