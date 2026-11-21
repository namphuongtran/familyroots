import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { AbstractIntlMessages } from 'next-intl'
import { envelope, server as mswServer } from '@/shared/testing/msw'
import { expected, renderWithProviders } from '@/shared/testing/render'
import { CLAN_COOKIE } from '@/shared/http/request-context'
import viMessages from '../../../../messages/vi.json'
import { FATHER_ID, focusViewDto } from '../model/tree-fixtures'
import { FocusPanel } from './FocusPanel'

/**
 * The panel builds its own `RequestContext` through `useClientRequestContext`, so the test drives
 * the real inputs: the clan cookie, and no Supabase session.
 */
vi.mock('@/shared/supabase/client', () => ({ createClientOrNull: vi.fn(() => null) }))

const API = `${process.env.NEXT_PUBLIC_API_ORIGIN ?? 'http://localhost:8000'}/api/v1`
const CLAN_ID = '4bf92f35-77b3-4da6-a3ce-929d0e0e4736'
const messages = viMessages as unknown as AbstractIntlMessages
const tree = viMessages.tree

beforeEach(() => {
  document.cookie = `${CLAN_COOKIE}=${CLAN_ID}; path=/`
  mswServer.use(
    http.get(`${API}/tree/focus/${FATHER_ID}`, () => HttpResponse.json(envelope(focusViewDto()))),
  )
})

afterEach(() => {
  document.cookie = `${CLAN_COOKIE}=; path=/; max-age=0`
})

function renderPanel() {
  return renderWithProviders(
    <FocusPanel personId={FATHER_ID} onSelectPerson={() => {}} onClose={() => {}} />,
    { messages },
  )
}

describe('FocusPanel', () => {
  it('groups the children under Vợ cả, Vợ hai, then Chưa rõ mẹ, each with its own children', async () => {
    renderPanel()

    await screen.findByRole('heading', { level: 2, name: 'Nguyễn Hữu Đàm' })
    const headers = screen.getAllByRole('heading', { level: 4 })

    expect(headers.map((h) => h.textContent)).toEqual([
      'Vợ cảTrần Thị Mão',
      'Vợ haiLê Thị Nhàn',
      expected(tree.unknown_mother),
    ])

    const groupChildren = headers.map((h) =>
      within(h.closest('section')!)
        .getAllByRole('listitem')
        .map((li) => li.querySelector('span')?.textContent),
    )
    expect(groupChildren).toEqual([
      ['Nguyễn Hữu Lộc', 'Nguyễn Thị Sen'],
      ['Nguyễn Hữu Trác'],
      ['Nguyễn Hữu Bảo'],
    ])
  })

  it('reads Đời ? for a child whose đời is null, and Đời n for the rest', async () => {
    renderPanel()

    const unknownGroup = (
      await screen.findByRole('heading', { name: tree.unknown_mother })
    ).closest('section')!
    expect(within(unknownGroup).getByText(expected(tree.generation_unknown))).toBeInTheDocument()
    expect(screen.getAllByText('Đời 5')).toHaveLength(3)
    expect(screen.getByText('Đời 4')).toBeInTheDocument()
  })

  it('re-focuses on a child when it is pressed', async () => {
    const onSelectPerson = vi.fn()
    renderWithProviders(
      <FocusPanel personId={FATHER_ID} onSelectPerson={onSelectPerson} onClose={() => {}} />,
      { messages },
    )

    await userEvent.click(await screen.findByRole('button', { name: /Nguyễn Hữu Trác/ }))

    expect(onSelectPerson).toHaveBeenCalledWith('00000000-0000-0000-0000-0000000000c3')
  })
})
