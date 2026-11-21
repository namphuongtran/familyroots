import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import { envelope, server as mswServer } from '@/shared/testing/msw'
import { renderWithProviders } from '@/shared/testing/render'
import { CLAN_COOKIE } from '@/shared/http/request-context'
import viMessages from '../../../../messages/vi.json'
import { RelationshipsAside } from './RelationshipsAside'

/**
 * The aside builds its own `RequestContext` via `useClientRequestContext`,
 * same pattern as `PersonsList.test.tsx`. The Supabase client is mocked to
 * null so the first "no session" read completes and `ready` flips true —
 * the test then measures the real MSW-backed slice.
 */
const { createClientOrNull } = vi.hoisted(() => ({ createClientOrNull: vi.fn() }))
vi.mock('@/shared/supabase/client', () => ({ createClientOrNull }))

const API = `${process.env.NEXT_PUBLIC_API_ORIGIN ?? 'http://localhost:8000'}/api/v1`
const CLAN_ID = '4bf92f35-77b3-4da6-a3ce-929d0e0e4736'
const TARGET_ID = '00000000-0000-0000-0000-000000000001'
const WIFE_A_ID = '00000000-0000-0000-0000-00000000000a'
const WIFE_B_ID = '00000000-0000-0000-0000-00000000000b'
const CHILD_ID = '00000000-0000-0000-0000-00000000000c'

function setClanCookie(): void {
  document.cookie = `${CLAN_COOKIE}=${CLAN_ID}; path=/`
}

function clearClanCookie(): void {
  document.cookie = `${CLAN_COOKIE}=; path=/; max-age=0`
}

function personFixture(overrides: Record<string, unknown>): Record<string, unknown> {
  // Shape is `PersonResponse` (not `PersonSearchResult`), because
  // `batchGetPersons` parses with `personResponseDtoSchema` — the aside
  // calls the persons slice's batch, not search.
  return {
    id: overrides.id,
    created_by_clan_id: CLAN_ID,
    full_name: overrides.full_name,
    birth_name: null,
    courtesy_name: null,
    posthumous_name: null,
    alias_name: null,
    gender: 'female',
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
    created_by: 'dddddddd-dddd-dddd-dddd-dddddddddddd',
    updated_by: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    version: 1,
    ...overrides,
  }
}

function marriageFixture(spouseId: string, spouseOrder: number | null): Record<string, unknown> {
  return {
    id: `marriage-${spouseId}`,
    person1_id: TARGET_ID,
    person2_id: spouseId,
    created_by_clan_id: CLAN_ID,
    marriage_date: { date: '1970-05-15', precision: 'exact', display: null, lunar: null },
    divorce_date: { date: null, precision: 'unknown', display: null, lunar: null },
    marriage_place: null,
    status: 'married',
    spouse_order: spouseOrder,
    notes: null,
    created_by: 'user',
    updated_by: null,
    is_deleted: false,
    deleted_at: null,
    deleted_by: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    version: 1,
  }
}

function parentChildFixture(childId: string): Record<string, unknown> {
  return {
    id: `parent-child-${childId}`,
    parent_id: TARGET_ID,
    child_id: childId,
    created_by_clan_id: CLAN_ID,
    relationship_type: 'biological',
    birth_order: 1,
    notes: null,
    created_by: 'user',
    updated_by: null,
    is_deleted: false,
    deleted_at: null,
    deleted_by: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    version: 1,
  }
}

beforeEach(() => {
  setClanCookie()
  createClientOrNull.mockReturnValue(null)
})

afterEach(() => {
  clearClanCookie()
})

describe('RelationshipsAside', () => {
  it('renders two wives in spouse_order ascending and one child row (§3.3, spec §7.6 aside)', async () => {
    mswServer.use(
      http.get(`${API}/persons/${TARGET_ID}/marriages`, () =>
        HttpResponse.json(envelope([marriageFixture(WIFE_B_ID, 2), marriageFixture(WIFE_A_ID, 1)])),
      ),
      http.get(`${API}/persons/${TARGET_ID}/parent-child`, () =>
        HttpResponse.json(envelope([parentChildFixture(CHILD_ID)])),
      ),
      http.post(`${API}/persons/batch`, () =>
        HttpResponse.json({
          data: [
            personFixture({ id: WIFE_A_ID, full_name: 'Vũ Thị Hoa' }),
            personFixture({ id: WIFE_B_ID, full_name: 'Lê Thị Mai' }),
            personFixture({
              id: CHILD_ID,
              full_name: 'Nguyễn Minh Tuấn',
              gender: 'male',
            }),
          ],
          meta: { errors: [] },
        }),
      ),
    )

    renderWithProviders(<RelationshipsAside personId={TARGET_ID} />, {
      locale: 'vi',
      messages: viMessages,
    })

    // Wait for every related-person batch lookup to resolve so each row has
    // its real name before the order assertion reads them off the DOM.
    await waitFor(() => expect(screen.getByText('Vũ Thị Hoa')).toBeInTheDocument())
    await waitFor(() => expect(screen.getByText('Lê Thị Mai')).toBeInTheDocument())
    await waitFor(() => expect(screen.getByText('Nguyễn Minh Tuấn')).toBeInTheDocument())

    // The three rows: two wives and one child. A failure here would mean a
    // section is missing from the aside — the issue's own verification asks
    // the test to assert "all three rows".
    const rows = screen.getAllByTestId('relationship-row')
    expect(rows).toHaveLength(3)

    // Order inside the Vợ/Chồng section: spouse_order 1 before 2 per §3.3,
    // regardless of the fixture's arrival order (which is 2 first above).
    const spousesSection = screen.getByRole('region', { name: /vợ\/chồng/i })
    const spouseRows = within(spousesSection).getAllByTestId('relationship-row')
    expect(spouseRows).toHaveLength(2)
    expect(within(spouseRows[0]).getByText('Vũ Thị Hoa')).toBeInTheDocument()
    expect(within(spouseRows[0]).getByText('Vợ cả')).toBeInTheDocument()
    expect(within(spouseRows[1]).getByText('Lê Thị Mai')).toBeInTheDocument()
    expect(within(spouseRows[1]).getByText('Vợ hai')).toBeInTheDocument()

    // One child under the "Con cái" group, with the `Con đẻ` type chip for
    // the `biological` relationship_type.
    const childrenSection = screen.getByRole('region', { name: /con cái/i })
    const childRows = within(childrenSection).getAllByTestId('relationship-row')
    expect(childRows).toHaveLength(1)
    expect(within(childRows[0]).getByText('Nguyễn Minh Tuấn')).toBeInTheDocument()
    expect(within(childRows[0]).getByText('Con đẻ')).toBeInTheDocument()
  })
})
