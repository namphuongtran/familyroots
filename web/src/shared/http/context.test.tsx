import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { apiFetch } from './api-client'
import { CLAN_COOKIE, type RequestContext } from './request-context'
import { envelope, server as mswServer } from '@/shared/testing/msw'

/**
 * `context.server.ts` carries a bare `import 'server-only'`, which throws
 * unconditionally under Node's default export condition (see
 * `node_modules/server-only/index.js`) — the package relies on a bundler
 * swapping it for `empty.js` in a server context, which Vitest does not do.
 * Mocking it to an empty module is what lets this file import the real
 * `getServerRequestContext` at all.
 */
vi.mock('server-only', () => ({}))

// Neither runtime's Supabase session matters to this test — only clanId
// resolution does — so both are mocked to "no session" rather than left to
// depend on whether NEXT_PUBLIC_SUPABASE_URL happens to be set wherever this
// runs. `context.server.ts` and `context.client.ts` both catch a throwing
// client and fall back to `accessToken: null`.
vi.mock('@/lib/supabase/server', () => ({
  createClient: vi.fn(async () => {
    throw new Error('no Supabase session in this test')
  }),
}))
vi.mock('@/lib/supabase/client', () => ({
  createClientOrNull: vi.fn(() => null),
}))

let serverCookieJar: Map<string, { name: string; value: string }>

vi.mock('next/headers', () => ({
  cookies: vi.fn(async () => ({
    get: (name: string) => serverCookieJar.get(name),
  })),
}))

const API = `${process.env.NEXT_PUBLIC_API_ORIGIN ?? 'http://localhost:8000'}/api/v1`

function setBrowserCookie(value: string | null) {
  // jsdom keeps existing cookies around between assignments, so clear the
  // slot before writing a new value rather than only ever appending.
  document.cookie = `${CLAN_COOKIE}=; path=/; max-age=0`
  if (value !== null) {
    document.cookie = `${CLAN_COOKIE}=${encodeURIComponent(value)}; path=/`
  }
}

/**
 * Stands in for a `features/<slice>/server` repository function, which does
 * not exist yet — `src/features/` lands with the first slice PR (S-024 onward).
 * A repository does nothing but call `apiFetch` with the context it is
 * handed, so this is the part of "the same repository call returns the same
 * result in both runtimes" (web/CLAUDE.md, "The spine") that is already
 * testable: proof that `apiFetch`, called with whichever context a
 * repository would have been given, sends the identical resolved clan id.
 */
async function pingRepository(context: RequestContext) {
  return apiFetch('/ping', { context })
}

describe('one session, two runtimes (S-023)', () => {
  const clanId = '4bf92f35-77b3-4da6-a3ce-929d0e0e4736'

  beforeEach(() => {
    serverCookieJar = new Map([[CLAN_COOKIE, { name: CLAN_COOKIE, value: clanId }]])
    setBrowserCookie(clanId)
  })

  afterEach(() => {
    setBrowserCookie(null)
  })

  it('getServerRequestContext and getClientRequestContext resolve the same clanId for one cookie', async () => {
    const { getServerRequestContext } = await import('./context.server')
    const { getClientRequestContext } = await import('./context.client')

    const serverContext = await getServerRequestContext()
    const clientContext = await getClientRequestContext()

    expect(serverContext.clanId).toBe(clanId)
    expect(clientContext.clanId).toBe(clanId)
  })

  it('a repository call sends the identical X-Current-Clan-Id from an RSC context and a client context', async () => {
    const seenHeaders: Array<string | null> = []
    mswServer.use(
      http.get(`${API}/ping`, ({ request }) => {
        seenHeaders.push(request.headers.get('x-current-clan-id'))
        return HttpResponse.json(envelope({ ok: true }))
      }),
    )

    const { getServerRequestContext } = await import('./context.server')
    const { getClientRequestContext } = await import('./context.client')

    await pingRepository(await getServerRequestContext())
    await pingRepository(await getClientRequestContext())

    expect(seenHeaders).toEqual([clanId, clanId])
  })

  it('a missing cookie resolves to no clan selected in both runtimes', async () => {
    serverCookieJar = new Map()
    setBrowserCookie(null)

    const { getServerRequestContext } = await import('./context.server')
    const { getClientRequestContext } = await import('./context.client')

    expect((await getServerRequestContext()).clanId).toBeNull()
    expect((await getClientRequestContext()).clanId).toBeNull()
  })

  it('an unparseable cookie resolves to no clan selected in both runtimes, not to garbage forwarded as the header', async () => {
    serverCookieJar = new Map([[CLAN_COOKIE, { name: CLAN_COOKIE, value: 'not-a-uuid' }]])
    setBrowserCookie('not-a-uuid')

    const { getServerRequestContext } = await import('./context.server')
    const { getClientRequestContext } = await import('./context.client')

    expect((await getServerRequestContext()).clanId).toBeNull()
    expect((await getClientRequestContext()).clanId).toBeNull()
  })
})
