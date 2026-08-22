import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import type { ReactNode } from 'react'
import { envelope, pageEnvelope, server } from '@/shared/testing/msw'
import type { RequestContext } from '@/shared/http/request-context'
import { usePerson, usePersonSearch, usePersonsList } from './use-persons-queries'

const API = `${process.env.NEXT_PUBLIC_API_ORIGIN ?? 'http://localhost:8000'}/api/v1`

const context: RequestContext = { locale: 'vi', clanId: 'clan-1', accessToken: 'tok-1' }

function personFixture(overrides: Partial<Record<string, unknown>> = {}): Record<string, unknown> {
  return {
    id: '11111111-1111-1111-1111-111111111111',
    created_by_clan_id: null,
    full_name: 'Nguyễn Văn An',
    birth_name: null,
    courtesy_name: null,
    posthumous_name: null,
    alias_name: null,
    gender: 'male',
    birth_date: { date: '1750-01-01', precision: 'circa', display: null, lunar: null },
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
    ...overrides,
  }
}

function withQueryClient() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  function wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  }
  return { queryClient, wrapper }
}

describe('usePerson', () => {
  it('resolves the mapped domain Person, scoped by clan id in the query key', async () => {
    server.use(http.get(`${API}/persons/id-1`, () => HttpResponse.json(envelope(personFixture()))))
    const { wrapper } = withQueryClient()

    const { result } = renderHook(() => usePerson('id-1', {}, { context }), { wrapper })

    expect(result.current.isPending).toBe(true)
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.fullName).toBe('Nguyễn Văn An')
  })

  it('surfaces the error code on a 404, not a hand-invented message', async () => {
    server.use(
      http.get(`${API}/persons/missing`, () =>
        HttpResponse.json(
          { error: { code: 'person_not_found', message: 'Không tìm thấy', detail: {} } },
          { status: 404 },
        ),
      ),
    )
    const { wrapper } = withQueryClient()

    const { result } = renderHook(() => usePerson('missing', {}, { context }), { wrapper })

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect((result.current.error as { code?: string })?.code).toBe('person_not_found')
  })

  it('stays disabled for a blank id', () => {
    const { wrapper } = withQueryClient()
    const { result } = renderHook(() => usePerson('', {}, { context }), { wrapper })
    expect(result.current.fetchStatus).toBe('idle')
    expect(result.current.isPending).toBe(true)
  })
})

describe('usePersonsList', () => {
  it('paginates through the opaque cursor without ever parsing it', async () => {
    server.use(
      http.get(`${API}/persons`, ({ request }) => {
        const cursor = new URL(request.url).searchParams.get('cursor')
        if (cursor === null) {
          return HttpResponse.json(
            pageEnvelope([personFixture({ id: 'p-1' })], { cursor: 'page-2', has_more: true }),
          )
        }
        expect(cursor).toBe('page-2')
        return HttpResponse.json(pageEnvelope([personFixture({ id: 'p-2' })], { has_more: false }))
      }),
    )
    const { wrapper } = withQueryClient()

    const { result } = renderHook(() => usePersonsList({ limit: 20 }, { context }), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.pages).toHaveLength(1)
    expect(result.current.data?.pages[0].items[0].id).toBe('p-1')
    expect(result.current.hasNextPage).toBe(true)

    await result.current.fetchNextPage()

    await waitFor(() => expect(result.current.data?.pages).toHaveLength(2))
    expect(result.current.data?.pages[1].items[0].id).toBe('p-2')
    expect(result.current.hasNextPage).toBe(false)
  })
})

describe('usePersonSearch', () => {
  it('does not fire for a blank query', () => {
    const { wrapper } = withQueryClient()
    const { result } = renderHook(() => usePersonSearch({ q: '  ' }, { context }), { wrapper })
    expect(result.current.fetchStatus).toBe('idle')
  })

  it('fires for a real query and maps the results', async () => {
    server.use(
      http.get(`${API}/persons/search`, () =>
        HttpResponse.json(
          envelope([
            {
              id: '11111111-1111-1111-1111-111111111111',
              full_name: 'Nguyễn Văn An',
              gender: 'male',
              birth_date: { date: '1750-01-01', precision: 'circa', display: null, lunar: null },
              avatar_url: null,
              version: 1,
              generation: null,
              membership_role: null,
              is_founder: true,
            },
          ]),
        ),
      ),
    )
    const { wrapper } = withQueryClient()

    const { result } = renderHook(() => usePersonSearch({ q: 'An' }, { context }), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.[0]?.fullName).toBe('Nguyễn Văn An')
  })
})
