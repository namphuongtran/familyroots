import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { AbstractIntlMessages } from 'next-intl'
import { getCapabilities } from '@/domain/capability/capability'
import { envelope, server as mswServer } from '@/shared/testing/msw'
import { expected, renderWithProviders } from '@/shared/testing/render'
import { CLAN_COOKIE } from '@/shared/http/request-context'
import viMessages from '../../../../messages/vi.json'
import { toFamilyTree, treeResponseDtoSchema, type TreeResponseDto } from '../model/tree-dto'
import { FATHER_ID, focusViewDto, treeNodeDto, treeResponseDto } from '../model/tree-fixtures'
import { treeToFlow } from './tree-layout'
import { TreeListView } from './TreeListView'
import { TreeScreen } from './TreeScreen'

/**
 * Spec T-08: the list view exposes the same nodes the canvas draws, with đời spoken and the
 * § 3.3 wife groups, and every entry is a keyboard target that opens the focus panel.
 */
vi.mock('@/shared/supabase/client', () => ({ createClientOrNull: vi.fn(() => null) }))
// The screen reads capabilities only to gate the long-press sheet; the session is not under test.
vi.mock('@/features/auth', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/auth')>()),
  useCapabilities: () => getCapabilities('viewer'),
}))

const API = `${process.env.NEXT_PUBLIC_API_ORIGIN ?? 'http://localhost:8000'}/api/v1`
const CLAN_ID = '4bf92f35-77b3-4da6-a3ce-929d0e0e4736'
const messages = viMessages as unknown as AbstractIntlMessages
const tree = viMessages.tree
const TRAC_ID = '00000000-0000-0000-0000-0000000000c3'
const LOC_ID = '00000000-0000-0000-0000-0000000000c1'

/**
 * The § 7.4a fixture, plus a pedigree-collapse stub of the second wife's child under the first
 * wife's child. The stub's branch is walked first, so a list that dedupes by id drops one of them.
 */
function fixture(): TreeResponseDto {
  const dto = treeResponseDto()
  const loc = dto.tree.children.find((c) => c.id === LOC_ID)!
  loc.children = [
    treeNodeDto({
      id: TRAC_ID,
      full_name: 'Nguyễn Hữu Trác',
      generation: 6,
      pedigree_collapse_ref: true,
    }),
  ]
  return dto
}

function rootOf(dto: TreeResponseDto) {
  return toFamilyTree(treeResponseDtoSchema.parse(dto)).root
}

function listEntries() {
  const list = screen.getByRole('list', { name: expected(tree.list_view_label) })
  return within(list).getAllByRole('button')
}

beforeEach(() => {
  document.cookie = `${CLAN_COOKIE}=${CLAN_ID}; path=/`
})

afterEach(() => {
  document.cookie = `${CLAN_COOKIE}=; path=/; max-age=0`
})

describe('TreeListView', () => {
  it('has one entry for every node the canvas draws: persons, spouses and stubs', () => {
    const root = rootOf(fixture())
    renderWithProviders(<TreeListView root={root} onSelectPerson={() => {}} />, { messages })

    const listed = listEntries()
      .map((b) => b.dataset.personId)
      .sort()
    const drawn = treeToFlow(root)
      .nodes.map((n) => n.data.personId)
      .sort()

    expect(listed).toEqual(drawn)
    // Father, two wives, four children, one stub.
    expect(listed).toHaveLength(8)
  })

  it('marks the stub with its Nhánh chính ở nơi khác text', () => {
    renderWithProviders(<TreeListView root={rootOf(fixture())} onSelectPerson={() => {}} />, {
      messages,
    })

    const trac = screen.getAllByRole('button', { name: /Nguyễn Hữu Trác/ })
    expect(trac).toHaveLength(2)
    expect(trac.filter((b) => b.textContent?.includes(expected(tree.pedigree_stub)))).toHaveLength(
      1,
    )
  })

  it('speaks each entry’s đời the way the canvas badge does', () => {
    renderWithProviders(<TreeListView root={rootOf(fixture())} onSelectPerson={() => {}} />, {
      messages,
    })

    expect(screen.getByRole('button', { name: /Nguyễn Hữu Đàm/ })).toHaveAccessibleName(
      `Nguyễn Hữu Đàm ${expected(tree.generation_sr).replace('{n}', '4')}`,
    )
    expect(screen.getByRole('button', { name: /Nguyễn Hữu Bảo/ })).toHaveAccessibleName(
      `Nguyễn Hữu Bảo ${expected(tree.generation_unknown_sr)}`,
    )
  })

  it('groups a father’s children under Vợ cả, Vợ hai, then Chưa rõ mẹ', () => {
    renderWithProviders(
      <TreeListView root={rootOf(treeResponseDto())} onSelectPerson={() => {}} />,
      {
        messages,
      },
    )

    const children = screen.getByRole('list', { name: 'Con cái của Nguyễn Hữu Đàm' })
    const groupLists = within(children)
      .getAllByRole('list')
      .map((l) => l.getAttribute('aria-label'))
    expect(groupLists).toEqual([
      'Vợ cả · Trần Thị Mão',
      'Vợ hai · Lê Thị Nhàn',
      expected(tree.unknown_mother),
    ])

    const second = screen.getByRole('list', { name: 'Vợ hai · Lê Thị Nhàn' })
    expect(
      within(second)
        .getAllByRole('button')
        .map((b) => b.dataset.personId),
    ).toEqual([TRAC_ID])
  })
})

describe('TreeScreen', () => {
  it('toggles to the list view, and Tab then Enter on an entry opens its focus panel', async () => {
    const user = userEvent.setup()
    const focusRequests: string[] = []
    mswServer.use(
      http.get(`${API}/tree`, () => HttpResponse.json(envelope(fixture()))),
      http.get(`${API}/tree/focus/:id`, ({ params }) => {
        focusRequests.push(String(params.id))
        return HttpResponse.json(envelope(focusViewDto()))
      }),
    )
    renderWithProviders(<TreeScreen />, { messages })

    const toggle = screen.getByRole('button', { name: expected(tree.list_view) })
    expect(toggle).toHaveAttribute('aria-pressed', 'false')
    await user.click(toggle)
    expect(toggle).toHaveAttribute('aria-pressed', 'true')

    await screen.findByRole('list', { name: expected(tree.list_view_label) })
    const entries = listEntries()

    // Tab from the toggle walks every entry in order.
    for (const entry of entries) {
      await user.tab()
      expect(entry).toHaveFocus()
    }

    const father = entries.find((b) => b.dataset.personId === FATHER_ID)!
    father.focus()
    await user.keyboard('{Enter}')

    expect(await screen.findByRole('complementary', { name: tree.details })).toBeInTheDocument()
    await waitFor(() => expect(focusRequests).toEqual([FATHER_ID]))
  })

  it('opens the focus panel on Space too', async () => {
    const user = userEvent.setup()
    const focusRequests: string[] = []
    mswServer.use(
      http.get(`${API}/tree`, () => HttpResponse.json(envelope(fixture()))),
      http.get(`${API}/tree/focus/:id`, ({ params }) => {
        focusRequests.push(String(params.id))
        return HttpResponse.json(envelope(focusViewDto()))
      }),
    )
    renderWithProviders(<TreeScreen />, { messages })
    await user.click(screen.getByRole('button', { name: expected(tree.list_view) }))
    await screen.findByRole('list', { name: expected(tree.list_view_label) })

    const loc = listEntries().find((b) => b.dataset.personId === LOC_ID)!
    loc.focus()
    await user.keyboard(' ')

    await waitFor(() => expect(focusRequests).toEqual([LOC_ID]))
  })

  it('marks the tree region busy with the loading text while GET /tree is pending', async () => {
    const user = userEvent.setup()
    let release!: () => void
    const held = new Promise<void>((resolve) => (release = resolve))
    mswServer.use(
      http.get(`${API}/tree`, async () => {
        await held
        return HttpResponse.json(envelope(fixture()))
      }),
    )
    renderWithProviders(<TreeScreen />, { messages })
    // The list view, so the loaded tree renders without XYFlow, which jsdom cannot lay out.
    await user.click(screen.getByRole('button', { name: expected(tree.list_view) }))

    const region = screen.getByRole('region', { name: expected(tree.page_title) })
    await waitFor(() => expect(region).toHaveAttribute('aria-busy', 'true'))
    expect(within(region).getByRole('status')).toHaveTextContent('Đang tải cây gia phả...')

    release()

    await within(region).findByRole('list', { name: expected(tree.list_view_label) })
    expect(region).not.toHaveAttribute('aria-busy')
    expect(within(region).queryByText('Đang tải cây gia phả...')).not.toBeInTheDocument()
  })
})
