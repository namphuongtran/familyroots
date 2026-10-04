import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'
import type { AbstractIntlMessages } from 'next-intl'
import { envelope, server as mswServer } from '@/shared/testing/msw'
import { renderWithProviders } from '@/shared/testing/render'
import { CLAN_COOKIE } from '@/shared/http/request-context'
import viMessages from '../../../messages/vi.json'
import { MemberSidebar } from './MemberSidebar'

/**
 * The sidebar builds its own `RequestContext` through persons'
 * `usePersonsRequestContext`, so this drives it through the real inputs, the
 * clan cookie and an absent Supabase session, as `PersonsList.test.tsx` does.
 */
vi.mock('@/lib/supabase/client', () => ({
  createClientOrNull: vi.fn(() => null),
}))

const API = `${process.env.NEXT_PUBLIC_API_ORIGIN ?? 'http://localhost:8000'}/api/v1`
const CLAN_ID = '4bf92f35-77b3-4da6-a3ce-929d0e0e4736'
const PERSON_ID = '11111111-1111-1111-1111-111111111111'
const messages = viMessages as unknown as AbstractIntlMessages

/** `PersonResponse`, every field present, the way `GET /persons/{id}` sends it. */
function personResponse(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: PERSON_ID,
    created_by_clan_id: CLAN_ID,
    full_name: 'Nguyễn Văn An',
    birth_name: null,
    courtesy_name: null,
    posthumous_name: null,
    alias_name: null,
    gender: 'male',
    birth_date: { date: '1900-01-01', precision: 'year', display: 'Năm 1900', lunar: null },
    death_date: { date: '1975-06-15', precision: 'exact', display: null, lunar: null },
    birth_place: 'Hà Tĩnh',
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
    notes: 'Trưởng chi thứ hai.',
    is_deleted: false,
    created_by: '33333333-3333-3333-3333-333333333333',
    updated_by: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    version: 1,
    ...overrides,
  }
}

function servePerson(body: Record<string, unknown>): void {
  mswServer.use(http.get(`${API}/persons/${PERSON_ID}`, () => HttpResponse.json(envelope(body))))
}

beforeEach(() => {
  document.cookie = `${CLAN_COOKIE}=${CLAN_ID}; path=/`
})

afterEach(() => {
  document.cookie = `${CLAN_COOKIE}=; path=/; max-age=0`
})

describe('MemberSidebar', () => {
  it('renders the person from the HistoricalDate envelope GET /persons/{id} returns', async () => {
    servePerson(personResponse())

    renderWithProviders(<MemberSidebar personId={PERSON_ID} onClose={() => {}} />, { messages })

    expect(await screen.findByText('Nguyễn Văn An')).toBeInTheDocument()
    // The year-precision birth renders its `display`, the exact death its `date`.
    expect(screen.getByText('Năm 1900 – 15/06/1975')).toBeInTheDocument()
    expect(screen.getByText('Hà Tĩnh')).toBeInTheDocument()
    expect(screen.getByText('Trưởng chi thứ hai.')).toBeInTheDocument()
  })

  it('leaves the death side empty for a person with no known death date', async () => {
    servePerson(
      personResponse({
        death_date: { date: null, precision: 'unknown', display: null, lunar: null },
      }),
    )

    renderWithProviders(<MemberSidebar personId={PERSON_ID} onClose={() => {}} />, { messages })

    expect(await screen.findByText('Năm 1900 –')).toBeInTheDocument()
  })

  it('prints no lifespan when neither date is known', async () => {
    const unknown = { date: null, precision: 'unknown', display: null, lunar: null }
    servePerson(personResponse({ birth_date: unknown, death_date: unknown }))

    renderWithProviders(<MemberSidebar personId={PERSON_ID} onClose={() => {}} />, { messages })

    expect(await screen.findByText('Nguyễn Văn An')).toBeInTheDocument()
    expect(screen.queryByText(/–/)).not.toBeInTheDocument()
  })
})
