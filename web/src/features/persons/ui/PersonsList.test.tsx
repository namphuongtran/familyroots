import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { envelope, pageEnvelope, server as mswServer } from '@/shared/testing/msw'
import { renderWithProviders } from '@/shared/testing/render'
import { CLAN_COOKIE } from '@/shared/http/request-context'
import { PersonsList } from './PersonsList'

/**
 * `PersonsList` builds its own `RequestContext` via
 * `usePersonsRequestContext` (`use-persons-request-context.ts`) rather than
 * taking one as a prop, so this test drives that hook through its real
 * inputs — the clan cookie and the (mocked, absent) Supabase session — the
 * same way `persons-repository.two-runtimes.test.tsx` does for the
 * repository layer, rather than stubbing the hook itself.
 */
vi.mock('@/lib/supabase/client', () => ({
  createClientOrNull: vi.fn(() => null),
}))

const API = `${process.env.NEXT_PUBLIC_API_ORIGIN ?? 'http://localhost:8000'}/api/v1`
const CLAN_ID = '4bf92f35-77b3-4da6-a3ce-929d0e0e4736'

function setClanCookie(): void {
  document.cookie = `${CLAN_COOKIE}=${CLAN_ID}; path=/`
}

function clearClanCookie(): void {
  document.cookie = `${CLAN_COOKIE}=; path=/; max-age=0`
}

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
    created_by: '33333333-3333-3333-3333-333333333333',
    updated_by: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    version: 1,
    ...overrides,
  }
}

const messages = {
  members: {
    no_members: 'Chưa có thành viên nào',
    error_title: 'Không thể tải danh sách thành viên',
    load_more: 'Tải thêm',
    loading_more: 'Đang tải thêm...',
    load_more_error: 'Không tải được thêm thành viên.',
    all_shown: 'Đã hiển thị hết {count} thành viên.',
  },
  member: {
    unknown_date: 'Không rõ',
    born_on: 'Sinh {date}',
    deceased: 'Đã mất',
    retry: 'Thử lại',
  },
}

beforeEach(() => {
  setClanCookie()
})

afterEach(() => {
  clearClanCookie()
})

describe('PersonsList', () => {
  it('renders the empty state when the clan has no persons', async () => {
    mswServer.use(http.get(`${API}/persons`, () => HttpResponse.json(pageEnvelope([]))))
    renderWithProviders(<PersonsList />, { messages })

    await waitFor(() => expect(screen.getByText('Chưa có thành viên nào')).toBeInTheDocument())
  })

  it('renders a person row with its lifespan, keyed off the render rule rather than a hardcoded shape', async () => {
    mswServer.use(
      http.get(`${API}/persons`, () => HttpResponse.json(pageEnvelope([personFixture()]))),
    )
    renderWithProviders(<PersonsList />, { messages })

    await waitFor(() => expect(screen.getByText('Nguyễn Văn An')).toBeInTheDocument())
    // birth_date's `display` ("1900") wins over the raw ISO per the render
    // rule's precedence for a non-exact precision — a regression that
    // printed the ISO string instead would fail this line.
    expect(screen.getByText('Sinh 1900')).toBeInTheDocument()
  })

  it('shows the error state on the first page and lets the user retry', async () => {
    let calls = 0
    mswServer.use(
      http.get(`${API}/persons`, () => {
        calls += 1
        if (calls === 1) {
          return HttpResponse.json(
            { error: { code: 'unknown_error', message: 'Đã xảy ra lỗi', detail: {} } },
            { status: 500 },
          )
        }
        return HttpResponse.json(pageEnvelope([personFixture()]))
      }),
    )
    renderWithProviders(<PersonsList />, { messages })

    await waitFor(() =>
      expect(screen.getByText('Không thể tải danh sách thành viên')).toBeInTheDocument(),
    )

    await userEvent.click(screen.getByRole('button', { name: 'Thử lại' }))

    await waitFor(() => expect(screen.getByText('Nguyễn Văn An')).toBeInTheDocument())
    expect(calls).toBe(2)
  })

  it('loads the next page on "Tải thêm" without re-fetching the first, and shows the end marker once has_more is false', async () => {
    const first = personFixture({ id: 'person-1', full_name: 'Người Một' })
    const second = personFixture({ id: 'person-2', full_name: 'Người Hai' })
    let calls = 0
    mswServer.use(
      http.get(`${API}/persons`, ({ request }) => {
        calls += 1
        const cursor = new URL(request.url).searchParams.get('cursor')
        if (cursor === null) {
          return HttpResponse.json(pageEnvelope([first], { cursor: 'page-2', has_more: true }))
        }
        expect(cursor).toBe('page-2')
        return HttpResponse.json(pageEnvelope([second], { has_more: false }))
      }),
    )
    renderWithProviders(<PersonsList />, { messages })

    await waitFor(() => expect(screen.getByText('Người Một')).toBeInTheDocument())
    expect(screen.queryByText('Người Hai')).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Tải thêm' }))

    await waitFor(() => expect(screen.getByText('Người Hai')).toBeInTheDocument())
    // The first page's row is still there — pagination appends, it does not replace.
    expect(screen.getByText('Người Một')).toBeInTheDocument()
    expect(screen.getByText('Đã hiển thị hết 2 thành viên.')).toBeInTheDocument()
    expect(calls).toBe(2)
  })

  it('keeps the already-loaded rows visible when loading the next page fails', async () => {
    const first = personFixture({ id: 'person-1', full_name: 'Người Một' })
    mswServer.use(
      http.get(`${API}/persons`, ({ request }) => {
        const cursor = new URL(request.url).searchParams.get('cursor')
        if (cursor === null) {
          return HttpResponse.json(pageEnvelope([first], { cursor: 'page-2', has_more: true }))
        }
        return HttpResponse.json(
          { error: { code: 'unknown_error', message: 'Đã xảy ra lỗi', detail: {} } },
          { status: 500 },
        )
      }),
    )
    renderWithProviders(<PersonsList />, { messages })

    await waitFor(() => expect(screen.getByText('Người Một')).toBeInTheDocument())
    await userEvent.click(screen.getByRole('button', { name: 'Tải thêm' }))

    await waitFor(() =>
      expect(screen.getByText('Không tải được thêm thành viên.')).toBeInTheDocument(),
    )
    // Negative control for this test: a component that blanks the list on a
    // `fetchNextPage` failure (e.g. by reading `isError` instead of
    // `isFetchNextPageError`) would fail this next line, since the first
    // page's row would have been removed along with the error state.
    expect(screen.getByText('Người Một')).toBeInTheDocument()
  })
})
