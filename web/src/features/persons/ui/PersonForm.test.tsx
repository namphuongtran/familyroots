import { http, HttpResponse } from 'msw'
import { describe, expect, it, vi } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { AbstractIntlMessages } from 'next-intl'
import { envelope, errorEnvelope, server as mswServer } from '@/shared/testing/msw'
import { renderWithProviders } from '@/shared/testing/render'
import type { Person } from '@/domain/person/person'
import type { RequestContext } from '@/shared/http/request-context'
import viMessages from '../../../../messages/vi.json'
import { PersonForm } from './PersonForm'

/**
 * `viMessages` is the real locale file, not a hand-written subset — this
 * form's `member_form` namespace grew to ~85 keys, and a copied subset would
 * be exactly the risk `shared/testing/render.tsx`'s own doc comment warns
 * about: a test that supplies its own copy cannot catch a missing key in the
 * real file.
 */
const messages = viMessages as unknown as AbstractIntlMessages

const API = `${process.env.NEXT_PUBLIC_API_ORIGIN ?? 'http://localhost:8000'}/api/v1`
const context: RequestContext = { locale: 'vi', clanId: 'clan-1', accessToken: 'tok-1' }

function wirePerson(overrides: Partial<Record<string, unknown>> = {}): Record<string, unknown> {
  return {
    id: 'person-1',
    created_by_clan_id: null,
    full_name: 'Nguyễn Văn An',
    birth_name: null,
    courtesy_name: null,
    posthumous_name: null,
    alias_name: null,
    gender: 'male',
    birth_date: { date: '1900-01-01', precision: 'exact', display: null, lunar: null },
    death_date: undefined,
    birth_place: 'Hà Nội',
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
    version: 3,
    ...overrides,
  }
}

function personProp(overrides: Partial<Person> = {}): Person {
  return {
    id: 'person-1',
    createdByClanId: null,
    fullName: 'Nguyễn Văn An',
    birthName: null,
    courtesyName: null,
    posthumousName: null,
    aliasName: null,
    gender: 'male',
    birthDate: { date: '1900-01-01', precision: 'exact', display: null, lunar: null },
    deathDate: null,
    birthPlace: 'Hà Nội',
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
    version: 3,
    ...overrides,
  }
}

describe('PersonForm — edit, a plain successful save', () => {
  it('shows the save-success confirmation and hands the updated person to onSuccess', async () => {
    mswServer.use(
      http.patch(`${API}/persons/person-1`, () =>
        HttpResponse.json(envelope(wirePerson({ notes: 'ghi chú mới', version: 4 }))),
      ),
    )
    const onSuccess = vi.fn()
    renderWithProviders(
      <PersonForm
        mode="edit"
        person={personProp()}
        context={context}
        onSuccess={onSuccess}
        onCancel={vi.fn()}
      />,
      { messages },
    )

    await userEvent.type(screen.getByLabelText('Ghi chú'), 'ghi chú mới')
    await userEvent.click(screen.getByRole('button', { name: 'Lưu' }))

    await waitFor(() => expect(screen.getByText('Đã lưu thay đổi.')).toBeInTheDocument())
    await userEvent.click(screen.getByRole('button', { name: 'Tiếp tục' }))
    expect(onSuccess).toHaveBeenCalledWith(expect.objectContaining({ id: 'person-1', version: 4 }))
  })

  it('surfaces meta.warning as part of the confirmation text (spec §7.7a)', async () => {
    mswServer.use(
      http.patch(`${API}/persons/person-1`, () =>
        HttpResponse.json({
          data: wirePerson({ version: 4 }),
          meta: { warning: 'chênh lệch tuổi bất thường' },
        }),
      ),
    )
    renderWithProviders(
      <PersonForm
        mode="edit"
        person={personProp()}
        context={context}
        onSuccess={vi.fn()}
        onCancel={vi.fn()}
      />,
      { messages },
    )

    await userEvent.type(screen.getByLabelText('Ghi chú'), 'x')
    await userEvent.click(screen.getByRole('button', { name: 'Lưu' }))

    await waitFor(() =>
      expect(screen.getByText('Đã lưu. Lưu ý: chênh lệch tuổi bất thường')).toBeInTheDocument(),
    )
  })
})

/**
 * The 409 path. `handlePatch` below is a per-test call counter: the first
 * `PATCH` answers `409 stale_write`, exactly the shape
 * `docs/contracts/rest-persons-api.md` documents ("Optimistic concurrency
 * (ADR-017)"); the refetch (`GET /persons/person-1`) then answers with a
 * record that disagrees with the form in two fields, one the user touched
 * and one they did not, so the dialog's two default-choice branches
 * (`diffPersonFormValues`'s own unit tests already cover the pure logic;
 * this proves the real form wires it up) both appear in one run.
 */
describe('PersonForm — edit, 409 stale_write (spec §7.7c)', () => {
  function mockConflictThenSuccess() {
    let patchCalls = 0
    const patchBodies: Record<string, unknown>[] = []
    mswServer.use(
      http.patch(`${API}/persons/person-1`, async ({ request }) => {
        patchCalls += 1
        const body = (await request.json()) as Record<string, unknown>
        patchBodies.push(body)
        if (patchCalls === 1) {
          return HttpResponse.json(
            errorEnvelope('stale_write', 'Hồ sơ đã được cập nhật', { current_version: 5 }),
            { status: 409 },
          )
        }
        // A realistic `PersonResponse`, deliberately not built by echoing
        // `body` — that request is in the *update* wire shape (flat
        // `birth_date`/`birth_date_precision`/`birth_date_display`), and a
        // response's `birth_date` is the nested `HistoricalDate` object;
        // spreading one onto the other silently produces an
        // unparseable fixture. `patchBodies` is what the second test below
        // asserts the resolved request against instead.
        return HttpResponse.json(envelope(wirePerson({ version: 6 })))
      }),
      http.get(`${API}/persons/person-1`, () =>
        HttpResponse.json(
          envelope(wirePerson({ birth_place: 'Đà Nẵng', notes: null, version: 5 })),
        ),
      ),
    )
    return { patchCalls: () => patchCalls, patchBodies }
  }

  it('opens the field-level conflict dialog instead of a generic error banner', async () => {
    mockConflictThenSuccess()
    renderWithProviders(
      <PersonForm
        mode="edit"
        person={personProp()}
        context={context}
        onSuccess={vi.fn()}
        onCancel={vi.fn()}
      />,
      { messages },
    )

    await userEvent.type(screen.getByLabelText('Ghi chú'), 'ghi chú của tôi')
    await userEvent.click(screen.getByRole('button', { name: 'Lưu' }))

    await waitFor(() =>
      expect(screen.getByText('Người khác vừa sửa hồ sơ này')).toBeInTheDocument(),
    )
    // No generic error banner underneath it — the 409 was fully absorbed by the dialog.
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()

    // Both row labels also match the underlying (still-mounted) form's own
    // field labels, so every query below is scoped to the dialog itself.
    const dialog = screen.getByRole('dialog')

    // The field the user touched: mine differs from the original, so it defaults to "mine".
    const notesRow = within(dialog).getByText('Ghi chú').closest('li')
    expect(notesRow).not.toBeNull()
    expect(within(notesRow!).getByRole('radio', { name: 'Giữ bản của tôi' })).toHaveAttribute(
      'aria-checked',
      'true',
    )

    // The field the user never touched: mine matches the original, so it defaults to "latest".
    const birthPlaceRow = within(dialog).getByText('Nơi sinh').closest('li')
    expect(birthPlaceRow).not.toBeNull()
    expect(within(birthPlaceRow!).getByRole('radio', { name: 'Dùng bản mới' })).toHaveAttribute(
      'aria-checked',
      'true',
    )

    // The birth date never changed on either side, so it never became a row at all.
    expect(within(dialog).queryByText('Ngày sinh')).not.toBeInTheDocument()
  })

  it('resolving and saving resubmits with the fresh version and the chosen values', async () => {
    const { patchCalls, patchBodies } = mockConflictThenSuccess()
    renderWithProviders(
      <PersonForm
        mode="edit"
        person={personProp()}
        context={context}
        onSuccess={vi.fn()}
        onCancel={vi.fn()}
      />,
      { messages },
    )

    await userEvent.type(screen.getByLabelText('Ghi chú'), 'ghi chú của tôi')
    await userEvent.click(screen.getByRole('button', { name: 'Lưu' }))
    await waitFor(() =>
      expect(screen.getByText('Người khác vừa sửa hồ sơ này')).toBeInTheDocument(),
    )

    await userEvent.click(screen.getByRole('button', { name: 'Lưu bản đã chọn' }))

    await waitFor(() => expect(screen.getByText('Đã lưu thay đổi.')).toBeInTheDocument())
    expect(patchCalls()).toBe(2)

    // The second request carries the fresh `expected_version` from the
    // refetch (5, not the stale 3 the form started with) and the default
    // resolution of each row: "mine" for the note the user typed, "latest"
    // for the place the user never touched.
    const resolvedBody = patchBodies[1]
    expect(resolvedBody.expected_version).toBe(5)
    expect(resolvedBody.notes).toBe('ghi chú của tôi')
    expect(resolvedBody.birth_place).toBe('Đà Nẵng')
  })

  it('"Bỏ thay đổi của tôi, tải lại" discards the conflict and loads the latest record into the form', async () => {
    mockConflictThenSuccess()
    renderWithProviders(
      <PersonForm
        mode="edit"
        person={personProp()}
        context={context}
        onSuccess={vi.fn()}
        onCancel={vi.fn()}
      />,
      { messages },
    )

    await userEvent.type(screen.getByLabelText('Ghi chú'), 'ghi chú của tôi')
    await userEvent.click(screen.getByRole('button', { name: 'Lưu' }))
    await waitFor(() =>
      expect(screen.getByText('Người khác vừa sửa hồ sơ này')).toBeInTheDocument(),
    )

    await userEvent.click(screen.getByRole('button', { name: 'Bỏ thay đổi của tôi, tải lại' }))

    await waitFor(() =>
      expect(screen.queryByText('Người khác vừa sửa hồ sơ này')).not.toBeInTheDocument(),
    )
    expect(screen.getByLabelText('Nơi sinh')).toHaveValue('Đà Nẵng')
    expect(screen.getByLabelText('Ghi chú')).toHaveValue('')
  })

  /**
   * **The negative control this seed's own instructions ask for.** Run by
   * hand and reverted, not committed as a second permanent test:
   *
   *   1. In `PersonForm.tsx`'s `onSubmit`, change
   *      `error instanceof ApiError && error.code === STALE_WRITE_CODE` to
   *      `false`.
   *   2. `pnpm vitest run --project component PersonForm.test.tsx` —
   *      "opens the field-level conflict dialog" fails: the `waitFor` on
   *      `'Người khác vừa sửa hồ sơ này'` times out, because the 409 now
   *      falls through to the generic `setSubmitError` branch instead. The
   *      failing output names the missing text, not a thrown exception —
   *      exactly the silent-loss shape this seed exists to prevent.
   *   3. Revert the change.
   *
   * See the commit message for the actual failing output captured from
   * this run.
   */
})
