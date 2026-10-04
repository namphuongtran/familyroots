import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, screen } from '@testing-library/react'
import { usePerson, type PersonResponseDto } from '@/features/persons'
import { envelope, errorEnvelope, server as mswServer } from '@/shared/testing/msw'
import { renderWithProviders } from '@/shared/testing/render'
import { fakeSupabaseClient } from '@/shared/testing/supabase'
import { useClientRequestContext } from './context.client'
import { CLAN_COOKIE } from './request-context'

/**
 * The browser request context, read through the caller it exists for: persons queries, each in
 * its own component, each calling `useClientRequestContext()` itself. Two components and two
 * person ids, on purpose. One component would share one hook call, and one id would share one
 * TanStack Query entry, and either would collapse two requests into one before `refreshAuth` is
 * ever asked to.
 *
 * The backend is MSW and Supabase is `fakeSupabaseClient`, so a request's `Authorization` header
 * is read off the wire, never off the context object.
 */

const { createClientOrNull } = vi.hoisted(() => ({ createClientOrNull: vi.fn() }))
vi.mock('@/shared/supabase/client', () => ({ createClientOrNull }))

const API = `${process.env.NEXT_PUBLIC_API_ORIGIN ?? 'http://localhost:8000'}/api/v1`
const CLAN_ID = '4bf92f35-77b3-4da6-a3ce-929d0e0e4736'
const AN = '11111111-1111-1111-1111-111111111111'
const BINH = '22222222-2222-2222-2222-222222222222'
const NAMES: Record<string, string> = { [AN]: 'Nguyễn Văn An', [BINH]: 'Trần Thị Bình' }

function personResponse(id: string): PersonResponseDto {
  return {
    id,
    created_by_clan_id: CLAN_ID,
    full_name: NAMES[id],
    birth_name: null,
    courtesy_name: null,
    posthumous_name: null,
    alias_name: null,
    gender: 'male',
    birth_date: { date: null, precision: 'unknown', display: null, lunar: null },
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

function PersonName({ id }: { id: string }) {
  const { context, ready, refreshAuth } = useClientRequestContext()
  const { data } = usePerson(id, {}, { context, refreshAuth, enabled: ready })
  return <p>{data?.fullName ?? 'loading'}</p>
}

beforeEach(() => {
  createClientOrNull.mockReset()
  document.cookie = `${CLAN_COOKIE}=${CLAN_ID}; path=/`
})

afterEach(() => {
  document.cookie = `${CLAN_COOKIE}=; path=/; max-age=0`
})

describe('useClientRequestContext', () => {
  it('two concurrent 401s cause one refresh, and both requests retry with the new token', async () => {
    const supabase = fakeSupabaseClient({
      accessToken: 'old-token',
      refreshedAccessToken: 'new-token',
      refreshDelayMs: 50,
    })
    createClientOrNull.mockReturnValue(supabase.client)

    /**
     * Neither 401 is sent until both requests carrying the old token have arrived, so the two
     * failures land together and the refresh is still in flight when the second one asks for it.
     * Without this, a slow second request could find the refresh already settled and start a
     * second one, and the count would be 2 for a reason that has nothing to do with the code.
     */
    let releaseUnauthorized!: () => void
    const bothUnauthorizedArrived = new Promise<void>((resolve) => {
      releaseUnauthorized = resolve
    })
    let unauthorized = 0
    const authorizationById: Record<string, string[]> = {}

    mswServer.use(
      http.get(`${API}/persons/:id`, async ({ request, params }) => {
        const id = String(params.id)
        const authorization = request.headers.get('authorization') ?? '(none)'
        ;(authorizationById[id] ??= []).push(authorization)
        if (authorization !== 'Bearer new-token') {
          unauthorized += 1
          if (unauthorized === 2) releaseUnauthorized()
          await bothUnauthorizedArrived
          return HttpResponse.json(errorEnvelope('invalid_token', 'Token expired'), { status: 401 })
        }
        return HttpResponse.json(envelope(personResponse(id)))
      }),
    )

    renderWithProviders(
      <>
        <PersonName id={AN} />
        <PersonName id={BINH} />
      </>,
    )

    expect(await screen.findByText('Nguyễn Văn An')).toBeInTheDocument()
    expect(await screen.findByText('Trần Thị Bình')).toBeInTheDocument()
    expect(supabase.auth.refreshSession).toHaveBeenCalledTimes(1)
    expect(authorizationById).toEqual({
      [AN]: ['Bearer old-token', 'Bearer new-token'],
      [BINH]: ['Bearer old-token', 'Bearer new-token'],
    })
  })

  it('a token Supabase rotates reaches the next request, with no remount', async () => {
    const supabase = fakeSupabaseClient({ accessToken: 'first-token' })
    createClientOrNull.mockReturnValue(supabase.client)
    const authorizations: string[] = []
    mswServer.use(
      http.get(`${API}/persons/:id`, ({ request, params }) => {
        authorizations.push(request.headers.get('authorization') ?? '(none)')
        return HttpResponse.json(envelope(personResponse(String(params.id))))
      }),
    )

    const { queryClient } = renderWithProviders(<PersonName id={AN} />)
    expect(await screen.findByText('Nguyễn Văn An')).toBeInTheDocument()

    // What Supabase's own refresh timer does: store the new session, then tell every listener.
    act(() => {
      supabase.setAccessToken('rotated-token')
      supabase.emit('TOKEN_REFRESHED')
    })
    await act(() => queryClient.refetchQueries())

    expect(authorizations).toEqual(['Bearer first-token', 'Bearer rotated-token'])
  })

  it('an auth event that lands before the first session read wins over that read', async () => {
    const supabase = fakeSupabaseClient({ accessToken: 'rotated-token' })
    createClientOrNull.mockReturnValue(supabase.client)
    /**
     * Real supabase-js sends `INITIAL_SESSION` to a new listener once it has loaded the session,
     * which can be before `getSession()` resolves. Here the first read is held back and answers
     * with a token older than the one the event carried, the order a refresh in between produces.
     */
    let answerFirstRead!: () => void
    supabase.auth.getSession.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          answerFirstRead = () =>
            resolve({
              data: { session: { access_token: 'stale-token', user: { id: 'u', email: 'e' } } },
              error: null,
            })
        }),
    )
    const authorizations: string[] = []
    mswServer.use(
      http.get(`${API}/persons/:id`, ({ request, params }) => {
        authorizations.push(request.headers.get('authorization') ?? '(none)')
        return HttpResponse.json(envelope(personResponse(String(params.id))))
      }),
    )

    const { queryClient } = renderWithProviders(<PersonName id={AN} />)
    act(() => supabase.emit('INITIAL_SESSION'))
    expect(await screen.findByText('Nguyễn Văn An')).toBeInTheDocument()
    await act(async () => answerFirstRead())
    await act(() => queryClient.refetchQueries())

    expect(authorizations).toEqual(['Bearer rotated-token', 'Bearer rotated-token'])
  })

  it('a Supabase client that cannot be built reads as signed out, and the request still goes', async () => {
    createClientOrNull.mockImplementation(() => {
      throw new Error('Invalid supabaseUrl: Must be a valid HTTP or HTTPS URL.')
    })
    const authorizations: string[] = []
    mswServer.use(
      http.get(`${API}/persons/:id`, ({ request, params }) => {
        authorizations.push(request.headers.get('authorization') ?? '(none)')
        return HttpResponse.json(envelope(personResponse(String(params.id))))
      }),
    )

    renderWithProviders(<PersonName id={AN} />)

    expect(await screen.findByText('Nguyễn Văn An')).toBeInTheDocument()
    expect(authorizations).toEqual(['(none)'])
  })
})
