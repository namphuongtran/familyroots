import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import type { AbstractIntlMessages } from 'next-intl'
import { QueryClient } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useFamilyTree } from '@/features/tree'
import type { components } from '@/generated/api-types'
import {
  clearClanCookie,
  useClientRequestContext,
  writeClanCookie,
} from '@/shared/http/context.client'
import { createClientOrNull } from '@/shared/supabase/client'
import { envelope, server } from '@/shared/testing/msw'
import { expected, renderWithProviders } from '@/shared/testing/render'
import { fakeSupabaseClient } from '@/shared/testing/supabase'
import viMessages from '../../../../../messages/vi.json'
import { treeNodeDto } from '@/features/tree/model/tree-fixtures'
import EditMemberPage from './[id]/edit/page'
import { ProfileRelationships } from './[id]/ProfileRelationships'

/**
 * #411: the tree is fresh for 60 seconds, so a write made on the person form or from the profile
 * page's relationship editor must invalidate it. Each case mounts a `useFamilyTree` consumer
 * against `GET /tree`, unmounts it (so the query is cached, not active), makes the real write
 * through the real screen, and remounts the consumer inside the stale time. The reading is the
 * name on screen and the `GET /tree` request count.
 */
vi.mock('@/shared/supabase/client', () => ({ createClientOrNull: vi.fn() }))
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), back: vi.fn() }),
  useParams: () => ({ locale: 'vi', id: PERSON_ID }),
}))

const messages = viMessages as unknown as AbstractIntlMessages
const API = `${process.env.NEXT_PUBLIC_API_ORIGIN ?? 'http://localhost:8000'}/api/v1`
const CLAN = 'aaaaaaaa-0000-4000-8000-000000000001'
const PERSON_ID = '00000000-0000-4000-8000-000000000001'
const CHILD_ID = '00000000-0000-4000-8000-00000000000c'

/** The shared test client collects an unobserved query at once (`gcTime: 0`); this one keeps it. */
function cachingClient(): QueryClient {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

function TreeName() {
  const { context, ready, refreshAuth } = useClientRequestContext()
  const { data } = useFamilyTree({}, { context, refreshAuth, enabled: ready })
  return <p data-testid="tree-name">{data?.root.fullName ?? 'loading'}</p>
}

function serveSession() {
  const profile: components['schemas']['UserProfile'] = {
    id: '11111111-1111-4111-8111-111111111111',
    email: 'lan@example.com',
    full_name: 'Lan',
    clan_id: CLAN,
    clan_name: 'Nguyễn Phúc',
    role: null,
    is_approved: true,
    has_pending_membership: false,
    person_id: null,
    preferred_locale: 'vi',
    platform_role: 'user',
  }
  server.use(
    http.get(`${API}/auth/me`, () => HttpResponse.json(envelope(profile))),
    http.get(`${API}/me/clans`, () =>
      HttpResponse.json(
        envelope<components['schemas']['UserClanMembership'][]>([
          { clan_id: CLAN, clan_name: 'Nguyễn Phúc', clan_slug: 'nguyen-phuc', role: 'editor' },
        ]),
      ),
    ),
  )
}

/** `GET /tree` answering with whatever `name.current` holds, and counting the requests. */
function serveTree(name: { current: string }) {
  const requests = { count: 0 }
  server.use(
    http.get(`${API}/tree`, () => {
      requests.count += 1
      return HttpResponse.json(
        envelope({
          tree: treeNodeDto({ id: PERSON_ID, full_name: name.current, generation: 1, depth: 0 }),
          total_persons: 1,
          total_generations: 1,
        }),
      )
    }),
  )
  return requests
}

function wirePerson(fullName: string, version: number): Record<string, unknown> {
  return {
    id: PERSON_ID,
    created_by_clan_id: CLAN,
    full_name: fullName,
    birth_name: null,
    courtesy_name: null,
    posthumous_name: null,
    alias_name: null,
    gender: 'male',
    birth_date: { date: '1900-01-01', precision: 'year', display: '1900', lunar: null },
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
    created_by: 'u-1',
    updated_by: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    version,
  }
}

beforeEach(() => {
  vi.mocked(createClientOrNull).mockReturnValue(
    fakeSupabaseClient({ accessToken: 'tok-1' }).client as never,
  )
  writeClanCookie(CLAN)
  serveSession()
})

afterEach(() => {
  clearClanCookie()
})

describe('the tree rereads after a write made away from the tree page', () => {
  it('a person update from the form', async () => {
    const name = { current: 'A' }
    const requests = serveTree(name)
    server.use(
      http.get(`${API}/persons/${PERSON_ID}`, () =>
        HttpResponse.json(envelope(wirePerson('Nguyễn Văn A', 1))),
      ),
      http.patch(`${API}/persons/${PERSON_ID}`, () => {
        name.current = 'B'
        return HttpResponse.json(envelope(wirePerson('Nguyễn Văn B', 2)))
      }),
    )

    const client = cachingClient()
    const first = renderWithProviders(<TreeName />, { messages, client })
    await waitFor(() => expect(screen.getByTestId('tree-name')).toHaveTextContent('A'))
    first.unmount()

    const { rerender } = renderWithProviders(<EditMemberPage />, { messages, client })
    await userEvent.type(await screen.findByLabelText('Ghi chú'), 'x')
    await userEvent.click(screen.getByRole('button', { name: 'Lưu' }))
    await screen.findByText('Đã lưu thay đổi.')
    rerender(<TreeName />)

    await waitFor(() => expect(screen.getByTestId('tree-name')).toHaveTextContent('B'))
    expect(requests.count).toBe(2)
  })

  it('a parent-child create from the profile page editor', async () => {
    const name = { current: 'A' }
    const requests = serveTree(name)
    server.use(
      http.get(`${API}/persons/${PERSON_ID}/marriages`, () => HttpResponse.json(envelope([]))),
      http.get(`${API}/persons/${PERSON_ID}/parent-child`, () => HttpResponse.json(envelope([]))),
      http.get(`${API}/persons/search`, () =>
        HttpResponse.json(
          envelope([
            {
              id: CHILD_ID,
              full_name: 'Nguyễn Minh Tuấn',
              gender: 'male',
              birth_date: { date: '1930-01-01', precision: 'year', display: '1930', lunar: null },
              avatar_url: null,
              version: 1,
              generation: null,
              membership_role: null,
              is_founder: false,
            },
          ]),
        ),
      ),
      http.post(`${API}/relationships/parent-child`, () => {
        name.current = 'B'
        return HttpResponse.json(
          envelope({
            id: 'pc-1',
            parent_id: PERSON_ID,
            child_id: CHILD_ID,
            created_by_clan_id: CLAN,
            relationship_type: 'biological',
            birth_order: 1,
            notes: null,
            created_by: 'u',
            updated_by: null,
            is_deleted: false,
            deleted_at: null,
            deleted_by: null,
            created_at: '2026-01-01T00:00:00Z',
            updated_at: '2026-01-01T00:00:00Z',
            version: 1,
          }),
          { status: 201 },
        )
      }),
    )

    const client = cachingClient()
    const first = renderWithProviders(<TreeName />, { messages, client })
    await waitFor(() => expect(screen.getByTestId('tree-name')).toHaveTextContent('A'))
    first.unmount()

    const { rerender } = renderWithProviders(<ProfileRelationships personId={PERSON_ID} />, {
      messages,
      client,
    })
    const ed = viMessages.relationship_editor
    await userEvent.click(await screen.findByRole('button', { name: expected(ed.open_editor) }))
    await userEvent.click(await screen.findByRole('button', { name: expected(ed.tab_add_child) }))
    await userEvent.type(await screen.findByRole('searchbox'), 'Ngu')
    await userEvent.click(await screen.findByRole('button', { name: 'Nguyễn Minh Tuấn' }))
    await userEvent.click(screen.getByRole('button', { name: expected(ed.save) }))
    await screen.findByRole('status')
    rerender(<TreeName />)

    await waitFor(() => expect(screen.getByTestId('tree-name')).toHaveTextContent('B'))
    expect(requests.count).toBe(2)
  })
})
