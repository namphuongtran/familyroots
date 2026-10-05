import { http, HttpResponse } from 'msw'
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { getCapabilities } from '@/domain/capability/capability'
import type { components } from '@/generated/api-types'
import { CLAN_COOKIE } from '@/shared/http/request-context'
import { envelope, errorEnvelope, server } from '@/shared/testing/msw'
import { guardClanRoute, guardPlatformRoute } from './guard'

/**
 * #186, the server guard end to end on one request: the Supabase session and the
 * `current_clan_id` cookie in, the real repository and the real decision table in between, a
 * redirect or an admitted route out. `model/route-guard.test.ts` holds the full table; this file
 * holds what only the request can show: which requests the guard sends, with which headers, and
 * what it does when the backend fails.
 *
 * Faked: Next's request APIs and the Supabase server client, neither of which exists outside a
 * Next request. MSW answers the backend with real envelopes and records every request, which is
 * how "no `/platform/metrics` probe" is read: as a request that was or was not sent.
 */

vi.mock('server-only', () => ({}))

let cookieJar: Map<string, { name: string; value: string }>
vi.mock('next/headers', () => ({
  cookies: vi.fn(async () => ({ get: (name: string) => cookieJar.get(name) })),
}))

let accessToken: string | null
vi.mock('@/shared/supabase/server', () => ({
  createClient: vi.fn(async () => ({
    auth: {
      getSession: async () => ({
        data: { session: accessToken === null ? null : { access_token: accessToken } },
      }),
    },
  })),
}))

/** `redirect()` throws in Next, so a redirected guard never returns. The fake keeps that. */
class Redirected extends Error {
  constructor(readonly to: string) {
    super(`redirect to ${to}`)
  }
}
vi.mock('next/navigation', () => ({
  redirect: vi.fn((to: string) => {
    throw new Redirected(to)
  }),
}))

async function redirectedTo(guard: Promise<unknown>): Promise<string> {
  const outcome = await guard.then(
    () => null,
    (error: unknown) => error,
  )
  if (outcome instanceof Redirected) return outcome.to
  throw new Error(`expected a redirect, got ${outcome === null ? 'an admitted route' : outcome}`)
}

const API = `${process.env.NEXT_PUBLIC_API_ORIGIN ?? 'http://localhost:8000'}/api/v1`
const CLAN_A = 'aaaaaaaa-0000-4000-8000-000000000001'

function profile(
  platformRole: components['schemas']['UserProfile']['platform_role'],
): components['schemas']['UserProfile'] {
  return {
    id: '11111111-1111-4111-8111-111111111111',
    email: 'lan@example.com',
    full_name: 'Nguyễn Thị Lan',
    clan_id: null,
    clan_name: null,
    role: null,
    is_approved: true,
    has_pending_membership: false,
    person_id: null,
    preferred_locale: 'vi',
    platform_role: platformRole,
  }
}

function membership(role: string): components['schemas']['UserClanMembership'] {
  return { clan_id: CLAN_A, clan_name: 'Nguyễn Phúc', clan_slug: 'nguyen-phuc', role }
}

/** The backend as one user sees it. */
function backendFor(
  platformRole: components['schemas']['UserProfile']['platform_role'],
  memberships: components['schemas']['UserClanMembership'][],
) {
  server.use(
    http.get(`${API}/auth/me`, () => HttpResponse.json(envelope(profile(platformRole)))),
    http.get(`${API}/me/clans`, () => HttpResponse.json(envelope(memberships))),
  )
}

let sent: Request[]
const onRequest = ({ request }: { request: Request }) => {
  sent.push(request.clone())
}
const paths = () => sent.map((r) => `${r.method} ${new URL(r.url).pathname}`).sort()

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
beforeEach(() => {
  sent = []
  server.events.on('request:start', onRequest)
  cookieJar = new Map()
  accessToken = 'tok-1'
})
afterEach(() => {
  server.events.removeAllListeners()
  server.resetHandlers()
})
afterAll(() => server.close())

function setClanCookie(value: string) {
  cookieJar.set(CLAN_COOKIE, { name: CLAN_COOKIE, value })
}

describe('the requests the guard sends', () => {
  it('a super_admin entering platform/ costs GET /auth/me and GET /me/clans, and no probe', async () => {
    backendFor('super_admin', [])

    const route = await guardPlatformRoute('vi')

    expect(route.session.profile.platformRole).toBe('super_admin')
    expect(paths()).toEqual(['GET /api/v1/auth/me', 'GET /api/v1/me/clans'])
  })

  it('an admin entering a capability-guarded clan route costs the same two, and no probe', async () => {
    backendFor('user', [membership('admin')])
    setClanCookie(CLAN_A)

    await guardClanRoute('vi', 'viewPendingUsers')

    expect(paths()).toEqual(['GET /api/v1/auth/me', 'GET /api/v1/me/clans'])
  })

  it('reads the session with the token and without the clan, since no auth route is clan-scoped', async () => {
    backendFor('user', [membership('admin')])
    setClanCookie(CLAN_A)

    await guardClanRoute('vi')

    expect(sent).toHaveLength(2)
    for (const request of sent) {
      expect(request.headers.get('authorization')).toBe('Bearer tok-1')
      expect(request.headers.has('x-current-clan-id')).toBe(false)
    }
  })

  it('sends nothing for a visitor with no Supabase session, and routes them to sign in', async () => {
    accessToken = null

    expect(await redirectedTo(guardClanRoute('vi'))).toBe('/vi/login')
    expect(sent).toEqual([])
  })
})

describe('what a clan route returns or where it redirects', () => {
  it('admits an admin with the domain capabilities and a context naming the active clan', async () => {
    backendFor('user', [membership('admin')])
    setClanCookie(CLAN_A)

    const route = await guardClanRoute('vi', 'viewPendingUsers')

    expect(route.activeClan.clanName).toBe('Nguyễn Phúc')
    expect(route.capabilities).toEqual(getCapabilities('admin'))
    expect(route.context).toMatchObject({ clanId: CLAN_A, accessToken: 'tok-1' })
  })

  it('sends a viewer asking for viewPendingUsers to the dashboard', async () => {
    backendFor('user', [membership('viewer')])
    setClanCookie(CLAN_A)

    expect(await redirectedTo(guardClanRoute('vi', 'viewPendingUsers'))).toBe('/vi/dashboard')
  })

  it('sends a super_admin with no clan from a clan route to platform/', async () => {
    backendFor('super_admin', [])

    expect(await redirectedTo(guardClanRoute('vi'))).toBe('/vi/platform/clans')
  })

  it('sends a member who is not a super_admin from platform/ to the dashboard', async () => {
    backendFor('user', [membership('admin')])
    setClanCookie(CLAN_A)

    expect(await redirectedTo(guardPlatformRoute('vi'))).toBe('/vi/dashboard')
  })
})

describe('when the backend fails', () => {
  it('throws for the error boundary rather than routing on a session it could not read', async () => {
    // The legacy guard read a failed `GET /me/clans` as "no memberships" and sent an approved
    // admin to /pending-approval. A failure is not an access state.
    server.use(
      http.get(`${API}/auth/me`, () =>
        HttpResponse.json(errorEnvelope('internal_error', 'Lỗi máy chủ'), { status: 500 }),
      ),
      http.get(`${API}/me/clans`, () => HttpResponse.json(envelope([membership('admin')]))),
    )
    setClanCookie(CLAN_A)

    await expect(guardClanRoute('vi')).rejects.toMatchObject({ status: 500 })
  })
})
