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

/**
 * Seed S-084. `/{locale}/invitations/{token}` has to reach the browser with the
 * token still on it. Without a `PUBLIC_ROUTES` entry, a signed-out visitor — which
 * is the normal case for an invited relative — is redirected to
 * `/{locale}/login`, and the token is gone from the URL, so the invitation cannot
 * be opened even once.
 *
 * The token used below is a real-shaped `secrets.token_urlsafe(32)` value
 * (`docs/contracts/rest-invitations-api.md:41`): 43 URL-safe base64 characters,
 * including `-` and `_`.
 */
describe('the invitation route is public, so the token survives the first request (S-084)', () => {
  const TOKEN = 'Zx-9Qa_bC3dEfGhIjKlMnOpQrStUvWxYz0123456789'

  beforeEach(() => {
    vi.stubEnv('NEXT_PUBLIC_SUPABASE_URL', 'https://example.supabase.co')
    vi.stubEnv('NEXT_PUBLIC_SUPABASE_ANON_KEY', 'anon-key')
  })

  it('lets a signed-out visitor through, rather than redirecting to login', async () => {
    currentSession = null

    const response = await middleware(requestFor(`/vi/invitations/${TOKEN}`))

    expect(response.status).not.toBe(307)
    expect(response.headers.get('location')).toBeNull()
  })

  it('does the same on every locale, since every route is locale-prefixed', async () => {
    currentSession = null

    for (const locale of ['vi', 'en', 'zh', 'fr']) {
      const response = await middleware(requestFor(`/${locale}/invitations/${TOKEN}`))
      expect(response.headers.get('location'), locale).toBeNull()
    }
  })

  it('does not apply the clan gate either — the invitee has no clan to select', async () => {
    currentSession = { access_token: 'tok-1' }

    const response = await middleware(requestFor(`/vi/invitations/${TOKEN}`))

    expect(response.headers.get('location')).toBeNull()
  })

  /**
   * The control that keeps the case above honest. `/vi/tree` differs from
   * `/vi/invitations/...` only in being absent from `PUBLIC_ROUTES`, so if this
   * redirect ever stopped happening the tests above would pass for the wrong
   * reason — a broken session check rather than a public route.
   */
  it('and a non-public route in the same run still redirects, so the check is real', async () => {
    currentSession = null

    const response = await middleware(requestFor('/vi/tree'))

    expect(new URL(response.headers.get('location')!).pathname).toBe('/vi/login')
  })
})
