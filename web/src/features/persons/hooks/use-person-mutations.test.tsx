import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'
import { envelope, server } from '@/shared/testing/msw'
import type { RequestContext } from '@/shared/http/request-context'
import { usePersonsList } from './use-persons-queries'
import { useCreatePerson, useDeletePerson, useUpdatePerson } from './use-person-mutations'
import { personsKeys } from '../server/query-keys'

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

describe('useCreatePerson — invalidates the persons lists for this clan', () => {
  it('a successful create makes an already-fetched list go stale and refetch', async () => {
    let listCallCount = 0
    server.use(
      http.get(`${API}/persons`, () => {
        listCallCount += 1
        return HttpResponse.json({
          data: [personFixture({ id: `existing-${listCallCount}` })],
          meta: { cursor: null, has_more: false, limit: 20 },
        })
      }),
      http.post(`${API}/persons`, () =>
        HttpResponse.json({ data: personFixture({ id: 'new-person' }) }, { status: 201 }),
      ),
    )
    const { wrapper } = withQueryClient()

    const list = renderHook(() => usePersonsList({ limit: 20 }, { context }), { wrapper })
    await waitFor(() => expect(list.result.current.isSuccess).toBe(true))
    expect(listCallCount).toBe(1)

    const create = renderHook(() => useCreatePerson({ context }), { wrapper })
    create.result.current.mutate({
      full_name: 'Người mới',
      gender: 'unknown',
      birth_date_precision: 'exact',
      death_date_precision: 'exact',
      nationality: 'VN',
    })
    await waitFor(() => expect(create.result.current.isSuccess).toBe(true))

    // The mutation's own invalidateQueries call is what makes the already-
    // mounted list hook refetch — nobody re-renders it or calls refetch().
    await waitFor(() => expect(listCallCount).toBe(2))

    /**
     * Negative control (run by hand, reverted): delete the
     * `queryClient.invalidateQueries({ queryKey: personsKeys.lists(...) })`
     * call from `useCreatePerson` in `use-person-mutations.ts`. `listCallCount`
     * then stays `1` forever and the `waitFor` above times out — proving this
     * test is pinned on the invalidation actually firing, not merely on the
     * mutation succeeding.
     */
  })
})

describe('useUpdatePerson / useDeletePerson — invalidate the one detail plus every list', () => {
  it('update invalidates both personsKeys.detail and personsKeys.lists for the clan', async () => {
    server.use(
      http.patch(`${API}/persons/id-1`, () =>
        HttpResponse.json(envelope(personFixture({ version: 2 }))),
      ),
    )
    const { wrapper, queryClient } = withQueryClient()
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')

    const { result } = renderHook(() => useUpdatePerson({ context }), { wrapper })
    result.current.mutate({ id: 'id-1', body: { expected_version: 1 } })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    const invalidatedKeys = invalidateSpy.mock.calls.map(([filters]) => filters?.queryKey)
    expect(invalidatedKeys).toContainEqual(personsKeys.detail(context.clanId, 'id-1'))
    expect(invalidatedKeys).toContainEqual(personsKeys.lists(context.clanId))
  })

  it('delete invalidates the same two keys', async () => {
    server.use(
      http.delete(`${API}/persons/id-1`, () =>
        HttpResponse.json({ data: { message: 'Đã xóa', id: 'id-1' } }),
      ),
    )
    const { wrapper, queryClient } = withQueryClient()
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')

    const { result } = renderHook(() => useDeletePerson({ context }), { wrapper })
    result.current.mutate('id-1')

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    const invalidatedKeys = invalidateSpy.mock.calls.map(([filters]) => filters?.queryKey)
    expect(invalidatedKeys).toContainEqual(personsKeys.detail(context.clanId, 'id-1'))
    expect(invalidatedKeys).toContainEqual(personsKeys.lists(context.clanId))
  })
})
