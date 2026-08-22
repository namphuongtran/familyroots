import { NextRequest, NextResponse } from 'next/server'
import { beforeEach, describe, expect, it, vi } from 'vitest'

// `createServerClient` normally talks to Supabase over HTTP. Mocked to a
// double whose session is controlled per test, since this file is testing
// the clan-cookie gate added by S-023, not Supabase auth itself.
let currentSession: { access_token: string } | null = { access_token: 'tok-1' }

vi.mock('@supabase/ssr', () => ({
  createServerClient: vi.fn(() => ({
    auth: {
      getSession: vi.fn(async () => ({ data: { session: currentSession } })),
    },
  })),
}))

// The real `next-intl/middleware` re-exports from `next/server` in a way that
// Vitest's Node-native module resolution for externalized deps cannot follow
// (`next`'s package.json has no `exports` map, so a subpath import needs an
// explicit `.js`, which next-intl's compiled output does not add — a
// resolver quirk between Node ESM and Vite, unrelated to anything this seed
// changed). Mocked to `NextResponse.next`, which is what it would return for
// a request that already carries its locale prefix, the only shape every
// case below constructs.
vi.mock('next-intl/middleware', () => ({
  default: () => (request: Request) => NextResponse.next({ request }),
}))

const { middleware } = await import('./middleware')

const CLAN_ID = '4bf92f35-77b3-4da6-a3ce-929d0e0e4736'

function requestFor(path: string, cookie?: string): NextRequest {
  const headers = new Headers()
  if (cookie) headers.set('cookie', cookie)
  return new NextRequest(`http://localhost:3000${path}`, { headers })
}

describe('middleware clan gate (S-023)', () => {
  beforeEach(() => {
    currentSession = { access_token: 'tok-1' }
    vi.stubEnv('NEXT_PUBLIC_SUPABASE_URL', 'https://example.supabase.co')
    vi.stubEnv('NEXT_PUBLIC_SUPABASE_ANON_KEY', 'anon-key')
  })

  it('redirects a clan-scoped route to select-clan when the cookie is missing', async () => {
    const response = await middleware(requestFor('/vi/tree'))
    expect(response.status).toBe(307)
    expect(new URL(response.headers.get('location')!).pathname).toBe('/vi/select-clan')
  })

  it('redirects a clan-scoped route to select-clan when the cookie is unparseable', async () => {
    const response = await middleware(requestFor('/vi/tree', 'current_clan_id=not-a-uuid'))
    expect(response.status).toBe(307)
    expect(new URL(response.headers.get('location')!).pathname).toBe('/vi/select-clan')
  })

  it('lets a clan-scoped route through when the cookie carries a well-formed clan id', async () => {
    const response = await middleware(requestFor('/vi/tree', `current_clan_id=${CLAN_ID}`))
    expect(response.status).not.toBe(307)
    expect(response.headers.get('location')).toBeNull()
  })

  it('does not gate select-clan itself, or the request loops forever', async () => {
    const response = await middleware(requestFor('/vi/select-clan'))
    expect(response.headers.get('location')).toBeNull()
  })

  it('does not gate platform, which is cross-clan and not clan-scoped', async () => {
    const response = await middleware(requestFor('/vi/platform/clans'))
    expect(response.headers.get('location')).toBeNull()
  })

  it('does not gate backoffice, which is cross-clan and not clan-scoped', async () => {
    const response = await middleware(requestFor('/vi/backoffice/dashboard'))
    expect(response.headers.get('location')).toBeNull()
  })

  it('still redirects to login before it ever checks the clan cookie', async () => {
    currentSession = null
    const response = await middleware(requestFor('/vi/tree', `current_clan_id=${CLAN_ID}`))
    expect(response.status).toBe(307)
    expect(new URL(response.headers.get('location')!).pathname).toBe('/vi/login')
  })

  it('skips both the session and the clan check when Supabase env vars are absent (local dev)', async () => {
    vi.stubEnv('NEXT_PUBLIC_SUPABASE_URL', '')
    vi.stubEnv('NEXT_PUBLIC_SUPABASE_ANON_KEY', '')
    const response = await middleware(requestFor('/vi/tree'))
    expect(response.headers.get('location')).toBeNull()
  })
})
