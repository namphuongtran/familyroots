import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { envelope, errorEnvelope, server as mswServer } from '@/shared/testing/msw'
import { expected, renderWithProviders } from '@/shared/testing/render'
import { CLAN_COOKIE } from '@/shared/http/request-context'
import viMessages from '../../../../messages/vi.json'
import { RelationshipEditorSheet } from './RelationshipEditorSheet'

/**
 * #328's readings, over MSW serving the real envelopes: a second wife is sent with
 * `spouse_order: 2`; reordering two wives sends PATCHes that each carry a version; a
 * `422 relationship.parent_too_young` renders inline on the field; a `meta.warning` shows after
 * the save; a `409 stale_write` opens the persons form's conflict dialog.
 */
const { createClientOrNull } = vi.hoisted(() => ({ createClientOrNull: vi.fn() }))
vi.mock('@/shared/supabase/client', () => ({ createClientOrNull }))

const API = `${process.env.NEXT_PUBLIC_API_ORIGIN ?? 'http://localhost:8000'}/api/v1`
const CLAN_ID = '4bf92f35-77b3-4da6-a3ce-929d0e0e4736'
const HUSBAND = '00000000-0000-4000-8000-000000000001'
const WIFE_A = '00000000-0000-4000-8000-00000000000a'
const WIFE_B = '00000000-0000-4000-8000-00000000000b'
const CHILD = '00000000-0000-4000-8000-00000000000c'
const ed = viMessages.relationship_editor

function personFixture(id: string, fullName: string, gender = 'female'): Record<string, unknown> {
  return {
    id,
    created_by_clan_id: CLAN_ID,
    full_name: fullName,
    birth_name: null,
    courtesy_name: null,
    posthumous_name: null,
    alias_name: null,
    gender,
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
  }
}

function searchHit(id: string, fullName: string): Record<string, unknown> {
  return {
    id,
    full_name: fullName,
    gender: 'female',
    birth_date: { date: '1900-01-01', precision: 'year', display: '1900', lunar: null },
    avatar_url: null,
    version: 1,
    generation: null,
    membership_role: null,
    is_founder: false,
  }
}

function marriageFixture(
  id: string,
  spouseId: string,
  spouseOrder: number | null,
  version: number,
  status = 'married',
): Record<string, unknown> {
  return {
    id,
    person1_id: HUSBAND,
    person2_id: spouseId,
    created_by_clan_id: CLAN_ID,
    marriage_date: { date: null, precision: 'unknown', display: null, lunar: null },
    divorce_date: { date: null, precision: 'unknown', display: null, lunar: null },
    marriage_place: null,
    status,
    spouse_order: spouseOrder,
    notes: null,
    created_by: 'dddddddd-dddd-dddd-dddd-dddddddddddd',
    updated_by: null,
    is_deleted: false,
    deleted_at: null,
    deleted_by: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    version,
  }
}

function parentChildFixture(): Record<string, unknown> {
  return {
    id: 'pc-1',
    parent_id: HUSBAND,
    child_id: CHILD,
    created_by_clan_id: CLAN_ID,
    relationship_type: 'biological',
    birth_order: null,
    notes: null,
    created_by: 'dddddddd-dddd-dddd-dddd-dddddddddddd',
    updated_by: null,
    is_deleted: false,
    deleted_at: null,
    deleted_by: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    version: 1,
  }
}

const PEOPLE: Record<string, string> = {
  [WIFE_A]: 'Vũ Thị Hoa',
  [WIFE_B]: 'Lê Thị Mai',
  [CHILD]: 'Nguyễn Minh Tuấn',
}

/** `GET` marriages and the batch name lookup, the reads the sheet makes on open. */
function serveReads(marriages: Record<string, unknown>[]) {
  mswServer.use(
    http.get(`${API}/persons/${HUSBAND}/marriages`, () => HttpResponse.json(envelope(marriages))),
    http.post(`${API}/persons/batch`, async ({ request }) => {
      const body = (await request.json()) as { ids: string[] }
      return HttpResponse.json({
        data: body.ids.filter((id) => PEOPLE[id]).map((id) => personFixture(id, PEOPLE[id])),
        meta: { errors: [] },
      })
    }),
  )
}

function serveSearch(hits: Record<string, unknown>[]) {
  mswServer.use(http.get(`${API}/persons/search`, () => HttpResponse.json(envelope(hits))))
}

function renderSheet(initialSection?: 'spouses' | 'add_spouse' | 'parents' | 'add_child') {
  return renderWithProviders(
    <RelationshipEditorSheet
      personId={HUSBAND}
      open
      onOpenChange={() => {}}
      initialSection={initialSection}
    />,
    { locale: 'vi', messages: viMessages },
  )
}

async function pickFromSearch(user: ReturnType<typeof userEvent.setup>, name: string) {
  await user.type(await screen.findByRole('searchbox'), name.slice(0, 3))
  await user.click(await screen.findByRole('button', { name }))
}

beforeEach(() => {
  document.cookie = `${CLAN_COOKIE}=${CLAN_ID}; path=/`
  createClientOrNull.mockReturnValue(null)
})

afterEach(() => {
  document.cookie = `${CLAN_COOKIE}=; path=/; max-age=0`
})

describe('RelationshipEditorSheet', () => {
  it('adds a second wife with spouse_order prefilled to 2', async () => {
    serveReads([marriageFixture('m-a', WIFE_A, 1, 1)])
    serveSearch([searchHit(WIFE_B, 'Lê Thị Mai')])
    const posted: unknown[] = []
    mswServer.use(
      http.post(`${API}/relationships/marriages`, async ({ request }) => {
        posted.push(await request.json())
        return HttpResponse.json(envelope(marriageFixture('m-b', WIFE_B, 2, 1)), { status: 201 })
      }),
    )
    const user = userEvent.setup()
    renderSheet('add_spouse')

    const order = await screen.findByLabelText(expected(ed.spouse_order_label))
    expect(order).toHaveValue(2)

    await pickFromSearch(user, 'Lê Thị Mai')
    await user.click(screen.getByRole('button', { name: expected(ed.save) }))

    await waitFor(() => expect(posted).toHaveLength(1))
    expect(posted[0]).toMatchObject({
      person1_id: HUSBAND,
      person2_id: WIFE_B,
      spouse_order: 2,
      status: 'married',
    })
    expect(await screen.findByRole('status')).toHaveTextContent(expected(ed.saved))
  })

  it('reorders two wives with PATCHes that each carry the version', async () => {
    const state: Record<string, { spouseId: string; order: number | null; version: number }> = {
      'm-a': { spouseId: WIFE_A, order: 1, version: 4 },
      'm-b': { spouseId: WIFE_B, order: 2, version: 7 },
    }
    const list = () =>
      Object.entries(state).map(([id, s]) => marriageFixture(id, s.spouseId, s.order, s.version))
    serveReads(list())
    // Re-serve the list from the live state, after `serveReads` registered its snapshot.
    mswServer.use(
      http.get(`${API}/persons/${HUSBAND}/marriages`, () => HttpResponse.json(envelope(list()))),
    )
    const patches: Array<{ id: string; body: Record<string, unknown> }> = []
    mswServer.use(
      http.patch(`${API}/relationships/marriages/:id`, async ({ params, request }) => {
        const id = params.id as string
        const body = (await request.json()) as Record<string, unknown>
        patches.push({ id, body })
        const row = state[id]
        // The backend's ADR-017 check: the version is required and must match.
        if (typeof body.expected_version !== 'number') {
          return HttpResponse.json(errorEnvelope('validation_error', 'expected_version'), {
            status: 422,
          })
        }
        if (body.expected_version !== row.version) {
          return HttpResponse.json(
            errorEnvelope('stale_write', 'stale', { current_version: row.version }),
            { status: 409 },
          )
        }
        row.order = body.spouse_order as number | null
        row.version += 1
        return HttpResponse.json(
          envelope(marriageFixture(id, row.spouseId, row.order, row.version)),
        )
      }),
    )
    const user = userEvent.setup()
    renderSheet('spouses')

    await screen.findByText('Lê Thị Mai')
    await user.click(screen.getByRole('button', { name: 'Đưa Lê Thị Mai lên trước' }))

    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent(expected(ed.saved)))
    expect(patches).toEqual([
      { id: 'm-a', body: { spouse_order: null, expected_version: 4 } },
      { id: 'm-b', body: { spouse_order: 1, expected_version: 7 } },
      { id: 'm-a', body: { spouse_order: 2, expected_version: 5 } },
    ])
    expect(state['m-a'].order).toBe(2)
    expect(state['m-b'].order).toBe(1)

    // The list rereads in the new order: Mai first.
    await waitFor(() => {
      const items = screen.getAllByTestId('spouse-item')
      expect(within(items[0]).getByText('Lê Thị Mai')).toBeInTheDocument()
    })
  })

  it('renders a 422 parent_too_young inline on the child field, in Vietnamese', async () => {
    serveReads([])
    serveSearch([searchHit(CHILD, 'Nguyễn Minh Tuấn')])
    mswServer.use(
      http.post(`${API}/relationships/parent-child`, () =>
        HttpResponse.json(
          errorEnvelope('relationship.parent_too_young', 'Parent must be older', {
            min_age_gap: 12,
            actual: 9.5,
          }),
          { status: 422 },
        ),
      ),
    )
    const user = userEvent.setup()
    renderSheet('add_child')

    await pickFromSearch(user, 'Nguyễn Minh Tuấn')
    await user.click(screen.getByRole('button', { name: expected(ed.save) }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(
      'Cha/mẹ phải lớn hơn con ít nhất 12 tuổi, nhưng theo ngày sinh đã ghi thì chỉ hơn 9.5 tuổi.',
    )
    // Tied to the field it belongs to, not a banner.
    expect(screen.getByText('Đã chọn: Nguyễn Minh Tuấn')).toHaveAttribute(
      'aria-describedby',
      alert.id,
    )
    expect(screen.queryByText(expected(ed.saved))).not.toBeInTheDocument()
  })

  it('shows a meta.warning after a successful parent-child write', async () => {
    serveReads([])
    serveSearch([searchHit(CHILD, 'Nguyễn Minh Tuấn')])
    mswServer.use(
      http.post(`${API}/relationships/parent-child`, () =>
        HttpResponse.json(
          { data: parentChildFixture(), meta: { warning: 'Chênh lệch tuổi là 85 năm.' } },
          { status: 201 },
        ),
      ),
    )
    const user = userEvent.setup()
    renderSheet('add_child')

    await pickFromSearch(user, 'Nguyễn Minh Tuấn')
    await user.click(screen.getByRole('button', { name: expected(ed.save) }))

    expect(await screen.findByRole('status')).toHaveTextContent(
      'Đã lưu. Lưu ý: Chênh lệch tuổi là 85 năm.',
    )
  })

  it('a 409 stale_write on ending a marriage opens the persons conflict dialog', async () => {
    serveReads([marriageFixture('m-a', WIFE_A, 1, 1)])
    mswServer.use(
      http.patch(`${API}/relationships/marriages/:id`, () =>
        HttpResponse.json(errorEnvelope('stale_write', 'stale', { current_version: 2 }), {
          status: 409,
        }),
      ),
      http.get(`${API}/relationships/marriages/m-a`, () =>
        HttpResponse.json(envelope(marriageFixture('m-a', WIFE_A, 1, 2, 'widowed'))),
      ),
    )
    const user = userEvent.setup()
    renderSheet('spouses')

    await user.click(
      await screen.findByRole('button', { name: 'Kết thúc hôn nhân với Vũ Thị Hoa' }),
    )
    await user.click(screen.getByRole('button', { name: expected(ed.end_marriage_save) }))

    const dialog = await screen.findByRole('dialog', {
      name: expected(viMessages.member_form.stale_write_title),
    })
    // One row, the status, mine "Đã ly hôn" against the latest "Đã góa".
    expect(within(dialog).getByText(expected(ed.status_label))).toBeInTheDocument()
    expect(within(dialog).getByText('Đã ly hôn')).toBeInTheDocument()
    expect(within(dialog).getByText('Đã góa')).toBeInTheDocument()
  })
})
