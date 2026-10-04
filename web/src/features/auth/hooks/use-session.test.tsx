import { act, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { components } from '@/generated/api-types'
import { createClientOrNull } from '@/lib/supabase/client'
import { clearClanCookie, writeClanCookie } from '@/shared/http/context.client'
import { envelope, server } from '@/shared/testing/msw'
import { renderWithProviders } from '@/shared/testing/render'
import { fakeSupabaseClient } from '@/shared/testing/supabase'
import { useSession } from './use-session'

/**
 * The session is one query, and these cases read what that buys: how many requests a set of
 * consumers sends, what an auth event does to the value on screen, and that nothing of the old
 * persisted store survives. The real hook runs, the real repository sends the requests, and MSW
 * answers with real envelopes. Only the Supabase browser client is a fake, because jsdom has no
 * Supabase to sign in to.
 *
 * `e2e/auth/dashboard.auth.spec.ts` reads the same outcome in a browser, on the real dashboard.
 */

vi.mock('@/lib/supabase/client', () => ({ createClientOrNull: vi.fn() }))

const API = `${process.env.NEXT_PUBLIC_API_ORIGIN ?? 'http://localhost:8000'}/api/v1`
const CLAN_A = 'aaaaaaaa-0000-4000-8000-000000000001'
const CLAN_B = 'bbbbbbbb-0000-4000-8000-000000000002'

function profile(): components['schemas']['UserProfile'] {
  return {
    id: '11111111-1111-4111-8111-111111111111',
    email: 'lan@example.com',
    full_name: 'Nguyễn Thị Lan',
    clan_id: CLAN_A,
    clan_name: 'Nguyễn Phúc',
    role: 'admin',
    is_approved: true,
    has_pending_membership: false,
    person_id: null,
    preferred_locale: 'vi',
    platform_role: 'user',
  }
}

function membership(clanId: string): components['schemas']['UserClanMembership'] {
  return { clan_id: clanId, clan_name: `Dòng họ ${clanId[0]}`, clan_slug: clanId, role: 'editor' }
}

/** Serves both reads and counts each one. */
function serveSession(memberships = [membership(CLAN_A)]) {
  const count = { me: 0, clans: 0 }
  server.use(
    http.get(`${API}/auth/me`, () => {
      count.me += 1
      return HttpResponse.json(envelope(profile()))
    }),
    http.get(`${API}/me/clans`, () => {
      count.clans += 1
      return HttpResponse.json(envelope(memberships))
    }),
  )
  return count
}

function Probe({ name }: { name: string }) {
  const { access } = useSession()
  const reading =
    access === null
      ? 'loading'
      : access.kind === 'ready'
        ? `ready:${access.activeClan.clanId}`
        : access.kind
  return <p data-testid={name}>{reading}</p>
}

/** The shape of a `(dashboard)` page: a layout, a header and a page body, each reading it. */
function ThreeConsumers() {
  return (
    <>
      <Probe name="layout" />
      <Probe name="header" />
      <Probe name="page" />
    </>
  )
}

let fake: ReturnType<typeof fakeSupabaseClient>

beforeEach(() => {
  fake = fakeSupabaseClient({ accessToken: 'tok-1' })
  vi.mocked(createClientOrNull).mockReturnValue(fake.client as never)
})

afterEach(() => {
  clearClanCookie()
  window.localStorage.clear()
})

describe('useSession: one query however many consumers', () => {
  it('three consumers send one GET /auth/me and one GET /me/clans between them', async () => {
    const count = serveSession()

    renderWithProviders(<ThreeConsumers />)

    for (const name of ['layout', 'header', 'page']) {
      await waitFor(() => expect(screen.getByTestId(name)).toHaveTextContent(`ready:${CLAN_A}`))
    }
    expect(count).toEqual({ me: 1, clans: 1 })
  })

  it('subscribes to Supabase once for all three, and lets go when the last one unmounts', async () => {
    serveSession()

    const { unmount } = renderWithProviders(<ThreeConsumers />)
    await waitFor(() => expect(screen.getByTestId('page')).toHaveTextContent('ready'))

    expect(fake.listenerCount()).toBe(1)
    unmount()
    expect(fake.listenerCount()).toBe(0)
  })

  it('with no Supabase session, reads signed out and sends nothing', async () => {
    fake.setAccessToken(null)
    // No handler is registered: `vitest.setup.ts` fails the test on any request MSW cannot answer.

    renderWithProviders(<Probe name="page" />)

    await waitFor(() => expect(screen.getByTestId('page')).toHaveTextContent('signed-out'))
  })
})

describe('useSession: the access state', () => {
  it('follows the clan cookie without refetching the session', async () => {
    const count = serveSession([membership(CLAN_A), membership(CLAN_B)])

    renderWithProviders(<Probe name="page" />)
    await waitFor(() =>
      expect(screen.getByTestId('page')).toHaveTextContent('needs-clan-selection'),
    )

    act(() => writeClanCookie(CLAN_B))

    expect(screen.getByTestId('page')).toHaveTextContent(`ready:${CLAN_B}`)
    expect(count).toEqual({ me: 1, clans: 1 })
  })
})

describe("useSession: Supabase's auth events", () => {
  it('SIGNED_OUT resets the session to signed out, with no request', async () => {
    const count = serveSession()
    renderWithProviders(<ThreeConsumers />)
    await waitFor(() => expect(screen.getByTestId('header')).toHaveTextContent('ready'))

    fake.setAccessToken(null)
    act(() => fake.emit('SIGNED_OUT'))

    // `waitFor`, not a bare read: TanStack Query notifies its observers on a timer, which
    // `act` does not flush.
    for (const name of ['layout', 'header', 'page']) {
      await waitFor(() => expect(screen.getByTestId(name)).toHaveTextContent('signed-out'))
    }
    expect(count).toEqual({ me: 1, clans: 1 })
  })

  it('SIGNED_IN refetches once, however many consumers are listening', async () => {
    const count = serveSession()
    renderWithProviders(<ThreeConsumers />)
    await waitFor(() => expect(screen.getByTestId('header')).toHaveTextContent('ready'))

    act(() => fake.emit('SIGNED_IN'))

    await waitFor(() => expect(count).toEqual({ me: 2, clans: 2 }))
  })

  it('INITIAL_SESSION and TOKEN_REFRESHED change nothing and send nothing', async () => {
    const count = serveSession()
    renderWithProviders(<Probe name="page" />)
    await waitFor(() => expect(screen.getByTestId('page')).toHaveTextContent('ready'))

    act(() => {
      fake.emit('INITIAL_SESSION')
      fake.emit('TOKEN_REFRESHED')
    })

    expect(count).toEqual({ me: 1, clans: 1 })
  })
})

describe('useSession: nothing of the old store survives', () => {
  it("removes the localStorage['auth-store'] entry the old app persisted", async () => {
    window.localStorage.setItem(
      'auth-store',
      JSON.stringify({ state: { user: { role: 'admin' } }, version: 0 }),
    )
    serveSession()

    renderWithProviders(<Probe name="page" />)
    await waitFor(() => expect(screen.getByTestId('page')).toHaveTextContent('ready'))

    expect(window.localStorage.getItem('auth-store')).toBeNull()
  })

  it('writes nothing to localStorage', async () => {
    serveSession()

    renderWithProviders(<ThreeConsumers />)
    await waitFor(() => expect(screen.getByTestId('page')).toHaveTextContent('ready'))

    expect(window.localStorage.length).toBe(0)
  })
})
