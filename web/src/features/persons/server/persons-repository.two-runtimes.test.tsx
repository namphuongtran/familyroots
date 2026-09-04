/**
 * "The same repository function runs, and is tested, in an RSC and in the
 * browser" (`web/CLAUDE.md`, "The spine"). `src/shared/http/context.test.tsx`
 * proved this at the `apiFetch` layer for the cookie change, before any repository
 * existed to write the real test against — this file is that real test,
 * for `getPerson`.
 *
 * `.tsx` (not `.ts`) on purpose, same reason as `context.test.tsx`:
 * `getClientRequestContext` reads `document.cookie`, which only exists
 * under the `component` project's jsdom environment. A `node`-environment
 * `.test.ts` would make `context.client.ts`'s `typeof document === 'undefined'`
 * guard resolve every browser-side read to null, which would make "both
 * runtimes agree" trivially true for the wrong reason — exactly the "a test
 * pins an outcome, not a setting" trap `.claude/rules/testing.md` names.
 */
import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { envelope, server as mswServer } from '@/shared/testing/msw'
import { CLAN_COOKIE } from '@/shared/http/request-context'
import { getPerson } from './persons-repository'

vi.mock('server-only', () => ({}))
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
const CLAN_ID = '4bf92f35-77b3-4da6-a3ce-929d0e0e4736'
const PERSON_ID = '11111111-1111-1111-1111-111111111111'

function setBrowserCookie(value: string | null) {
  document.cookie = `${CLAN_COOKIE}=; path=/; max-age=0`
  if (value !== null) {
    document.cookie = `${CLAN_COOKIE}=${encodeURIComponent(value)}; path=/`
  }
}

function personFixture(): Record<string, unknown> {
  return {
    id: PERSON_ID,
    created_by_clan_id: null,
    full_name: 'Nguyễn Văn An',
    birth_name: null,
    courtesy_name: null,
    posthumous_name: null,
    alias_name: null,
    gender: 'male',
    birth_date: { date: '1750-01-01', precision: 'circa', display: 'khoảng 1750', lunar: null },
    death_date: { date: null, precision: 'unknown', display: null, lunar: null },
    birth_place: null,
    death_place: null,
    burial_place: null,
    tomb_location: null,
    residence_place: null,
    religion: null,
    nationality: 'VN',
    occupation: null,
    education_level: null,
    title_rank: null,
    phone: null,
    email: null,
    biography: null,
    avatar_url: null,
    notes: null,
    is_deleted: false,
    created_by: '33333333-3333-3333-3333-333333333333',
    updated_by: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    version: 1,
  }
}

describe('the persons repository in both runtimes', () => {
  const seenHeaders: Array<string | null> = []

  beforeEach(() => {
    serverCookieJar = new Map([[CLAN_COOKIE, { name: CLAN_COOKIE, value: CLAN_ID }]])
    setBrowserCookie(CLAN_ID)
    seenHeaders.length = 0
    mswServer.use(
      http.get(`${API}/persons/${PERSON_ID}`, ({ request }) => {
        seenHeaders.push(request.headers.get('x-current-clan-id'))
        return HttpResponse.json(envelope(personFixture()))
      }),
    )
  })

  afterEach(() => {
    setBrowserCookie(null)
  })

  it('getPerson maps the identical domain Person from an RSC context and a client context', async () => {
    const { getServerRequestContext } = await import('@/shared/http/context.server')
    const { getClientRequestContext } = await import('@/shared/http/context.client')

    const serverPerson = await getPerson(
      PERSON_ID,
      {},
      {
        context: await getServerRequestContext(),
      },
    )
    const clientPerson = await getPerson(
      PERSON_ID,
      {},
      {
        context: await getClientRequestContext(),
      },
    )

    expect(serverPerson).toEqual(clientPerson)
    expect(serverPerson.fullName).toBe('Nguyễn Văn An')
    // Proves both calls actually carried the clan id through to the wire,
    // rather than two contexts that happen to map the same fixture.
    expect(seenHeaders).toEqual([CLAN_ID, CLAN_ID])
  })
})
