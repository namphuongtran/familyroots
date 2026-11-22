import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { NextIntlClientProvider, type AbstractIntlMessages } from 'next-intl'
import type { ReactNode } from 'react'
import { envelope, server as mswServer } from '@/shared/testing/msw'
import { expected } from '@/shared/testing/render'
import { CLAN_COOKIE, type RequestContext } from '@/shared/http/request-context'
import { useClientRequestContext } from '@/shared/http/context.client'
import type { Person } from '@/domain/person/person'
import type { components } from '@/generated/api-types'
import { PersonForm } from '@/features/persons'
import { RelationshipsAside } from '@/features/relationships'
import { fakeSupabaseClient } from '@/shared/testing/supabase'
import viMessages from '../../../../messages/vi.json'
import { treeNodeDto } from '../model/tree-fixtures'
import { useFamilyTree } from './use-tree-queries'
import { useInvalidateTree } from './use-invalidate-tree'

/**
 * #411. A person write, and an edge written from the profile's editor, must make the tree reread
 * inside its 60 s stale time. The shared client keeps the default `gcTime`, because the harness's
 * `gcTime: 0` would drop the unmounted tree's cache and the staleness could not be seen.
 */
const { createClientOrNull } = vi.hoisted(() => ({ createClientOrNull: vi.fn() }))
vi.mock('@/shared/supabase/client', () => ({ createClientOrNull }))

const API = `${process.env.NEXT_PUBLIC_API_ORIGIN ?? 'http://localhost:8000'}/api/v1`
const CLAN_ID = '4bf92f35-77b3-4da6-a3ce-929d0e0e4736'
const PERSON_ID = '00000000-0000-4000-8000-000000000001'
const CHILD_ID = '00000000-0000-4000-8000-00000000000c'
const messages = viMessages as unknown as AbstractIntlMessages
const context: RequestContext = { locale: 'vi', clanId: CLAN_ID, accessToken: 'tok-1' }
const ed = viMessages.relationship_editor

let queryClient: QueryClient
let treeName: string
let treeRequests: number

beforeEach(() => {
  document.cookie = `${CLAN_COOKIE}=${CLAN_ID}; path=/`
  createClientOrNull.mockReturnValue(fakeSupabaseClient({ accessToken: 'tok-1' }).client)
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  treeName = 'A'
  treeRequests = 0
  mswServer.use(
    http.get(`${API}/tree`, () => {
      treeRequests += 1
      return HttpResponse.json(
        envelope({
          tree: treeNodeDto({ id: PERSON_ID, full_name: treeName, depth: 0 }),
          total_persons: 1,
          total_generations: 1,
        }),
      )
    }),
  )
})

afterEach(() => {
  document.cookie = `${CLAN_COOKIE}=; path=/; max-age=0`
})

function Providers({ children }: { children: ReactNode }) {
  return (
    <NextIntlClientProvider locale="vi" messages={messages}>
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </NextIntlClientProvider>
  )
}

function TreeConsumer() {
  const { data } = useFamilyTree({}, { context })
  return <p data-testid="tree-name">{data?.root.fullName ?? 'loading'}</p>
}

/** Mounts the tree, lets it load, unmounts it: what leaving `/tree` does. */
async function visitTreeAndLeave() {
  const view = render(<TreeConsumer />, { wrapper: Providers })
  await waitFor(() => expect(screen.getByTestId('tree-name')).toHaveTextContent('A'))
  view.unmount()
  expect(treeRequests).toBe(1)
}

async function revisitTree() {
  render(<TreeConsumer />, { wrapper: Providers })
  await waitFor(() => expect(screen.getByTestId('tree-name')).not.toHaveTextContent('loading'))
}

function personProp(): Person {
  return {
    id: PERSON_ID,
    createdByClanId: null,
    fullName: 'A',
    birthName: null,
    courtesyName: null,
    posthumousName: null,
    aliasName: null,
    gender: 'male',
    birthDate: { date: '1900-01-01', precision: 'exact', display: null, lunar: null },
    deathDate: null,
    birthPlace: null,
    deathPlace: null,
    burialPlace: null,
    tombLocation: null,
    residencePlace: null,
    religion: null,
    nationality: 'VN',
    occupation: null,
    educationLevel: null,
    titleRank: null,
    phone: null,
    email: null,
    biography: null,
    avatarUrl: null,
    notes: null,
    isDeleted: false,
    createdBy: 'u-1',
    updatedBy: null,
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
    version: 1,
  }
}

function wirePerson(fullName: string): Record<string, unknown> {
  return {
    id: PERSON_ID,
    created_by_clan_id: null,
    full_name: fullName,
    birth_name: null,
    courtesy_name: null,
    posthumous_name: null,
    alias_name: null,
    gender: 'male',
    birth_date: { date: '1900-01-01', precision: 'exact', display: null, lunar: null },
    death_date: { date: null, precision: 'unknown', display: null, lunar: null },
    nationality: 'VN',
    is_deleted: false,
    created_by: 'u-1',
    updated_by: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    version: 2,
  }
}

function FormPage() {
  const invalidateTree = useInvalidateTree(CLAN_ID)
  return (
    <PersonForm
      mode="edit"
      person={personProp()}
      context={context}
      refreshAuth={async () => null}
      onSuccess={() => {}}
      onSaved={invalidateTree}
      onCancel={() => {}}
    />
  )
}

function ProfileAside() {
  const { context: ctx } = useClientRequestContext()
  const invalidateTree = useInvalidateTree(ctx.clanId)
  return <RelationshipsAside personId={PERSON_ID} onChanged={invalidateTree} />
}

describe('the tree rereads after a write made outside it (#411)', () => {
  it('a person update through the form: the remounted tree shows B, after a second GET /tree', async () => {
    await visitTreeAndLeave()
    treeName = 'B'
    mswServer.use(
      http.patch(`${API}/persons/${PERSON_ID}`, () => HttpResponse.json(envelope(wirePerson('B')))),
    )
    render(<FormPage />, { wrapper: Providers })
    await userEvent.type(screen.getByLabelText('Ghi chú'), 'x')
    await userEvent.click(screen.getByRole('button', { name: 'Lưu' }))
    await screen.findByText('Đã lưu thay đổi.')

    await revisitTree()
    await waitFor(() => expect(screen.getByTestId('tree-name')).toHaveTextContent('B'))
    expect(treeRequests).toBe(2)
  })

  it('a parent-child create from the profile aside: the remounted tree shows B, after a second GET /tree', async () => {
    const profile: components['schemas']['UserProfile'] = {
      id: '11111111-1111-4111-8111-111111111111',
      email: 'lan@example.com',
      full_name: 'Nguyễn Thị Lan',
      clan_id: CLAN_ID,
      clan_name: 'Nguyễn Phúc',
      role: null,
      is_approved: true,
      has_pending_membership: false,
      person_id: null,
      preferred_locale: 'vi',
      platform_role: 'user',
    }
    mswServer.use(
      http.get(`${API}/auth/me`, () => HttpResponse.json(envelope(profile))),
      http.get(`${API}/me/clans`, () =>
        HttpResponse.json(
          envelope([
            {
              clan_id: CLAN_ID,
              clan_name: 'Nguyễn Phúc',
              clan_slug: 'nguyen-phuc',
              role: 'editor',
            },
          ]),
        ),
      ),
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
      http.post(`${API}/relationships/parent-child`, () =>
        HttpResponse.json(
          envelope({
            id: 'pc-1',
            parent_id: PERSON_ID,
            child_id: CHILD_ID,
            created_by_clan_id: CLAN_ID,
            relationship_type: 'biological',
            birth_order: null,
            notes: null,
            created_by: 'u-1',
            updated_by: null,
            is_deleted: false,
            deleted_at: null,
            deleted_by: null,
            created_at: '2026-01-01T00:00:00Z',
            updated_at: '2026-01-01T00:00:00Z',
            version: 1,
          }),
          { status: 201 },
        ),
      ),
    )
    await visitTreeAndLeave()
    treeName = 'B'

    const user = userEvent.setup()
    render(<ProfileAside />, { wrapper: Providers })
    await user.click(await screen.findByRole('button', { name: expected(ed.open_editor) }))
    await user.click(await screen.findByRole('button', { name: 'Thêm con' }))
    await user.type(await screen.findByRole('searchbox'), 'Ngu')
    await user.click(await screen.findByRole('button', { name: 'Nguyễn Minh Tuấn' }))
    await user.click(screen.getByRole('button', { name: expected(ed.save) }))
    await screen.findByText(expected(ed.saved))

    await revisitTree()
    await waitFor(() => expect(screen.getByTestId('tree-name')).toHaveTextContent('B'))
    expect(treeRequests).toBe(2)
  })
})
