import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import type { AbstractIntlMessages } from 'next-intl'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { clearClanCookie, writeClanCookie } from '@/shared/http/context.client'
import { createClientOrNull } from '@/shared/supabase/client'
import { envelope, errorEnvelope, server } from '@/shared/testing/msw'
import { expected, renderWithProviders } from '@/shared/testing/render'
import { fakeSupabaseClient } from '@/shared/testing/supabase'
import viMessages from '../../../../messages/vi.json'
import { CLAN_ID, clanResponseDto, clanStatsDto } from '../../admin/model/clan-fixtures'
import { BackofficeDashboard } from './BackofficeDashboard'

/**
 * #314's reading: the dashboard's numbers come from `GET /clans/me?include=stats`, through the real
 * request context and an MSW handler that builds the contract's envelope. The badge and the
 * pending tile read the backend's `pending_users`. The two stats no endpoint backs say so in words.
 *
 * Negative control, 2026-11-22: with the old page's mock values put back in place of the stats
 * read (tiles 248 / 7 / 134 / 73, `badge="7"`), four of the five cases failed. The badge case
 * failed on its text content (`/^3$/` against `7`), the not-counted case with `Unable to find an
 * element with the text: Chưa được đếm`, and the zero and failed-read cases because the mock
 * numbers stood where `0` and `Không tải được` belong. Only the label case, which does not read a
 * number, stayed green.
 *
 * #197's reading moved here from the old page test: the four labels read in Vietnamese.
 */

vi.mock('@/shared/supabase/client', () => ({ createClientOrNull: vi.fn() }))

const messages = viMessages as unknown as AbstractIntlMessages
const API = `${process.env.NEXT_PUBLIC_API_ORIGIN ?? 'http://localhost:8000'}/api/v1`
const bo = viMessages.Backoffice

let seen: { include: string | null; clan: string | null }[]

function serveStats(stats = clanStatsDto({ pending_users: 3, total_members: 248 })) {
  server.use(
    http.get(`${API}/clans/me`, ({ request }) => {
      seen.push({
        include: new URL(request.url).searchParams.get('include'),
        clan: request.headers.get('x-current-clan-id'),
      })
      return HttpResponse.json(envelope({ ...clanResponseDto(), stats }))
    }),
  )
}

function tile(label: string): HTMLElement {
  const item = screen.getByText(expected(label)).closest('li')
  if (!item) throw new Error(`no tile for ${label}`)
  return item
}

beforeEach(() => {
  seen = []
  vi.mocked(createClientOrNull).mockReturnValue(
    fakeSupabaseClient({ accessToken: 'tok-1' }).client as never,
  )
  writeClanCookie(CLAN_ID)
})

afterEach(() => {
  clearClanCookie()
})

describe('the backoffice dashboard', () => {
  it('badges the approvals action with the 3 pending accounts the API counts', async () => {
    serveStats()
    renderWithProviders(<BackofficeDashboard locale="vi" />, { messages })

    expect(await screen.findByTestId('approvals-badge')).toHaveTextContent(/^3$/)
    expect(within(tile(viMessages.admin.pending_approval)).getByText('3')).toBeInTheDocument()
    expect(within(tile(viMessages.platform.total_members)).getByText('248')).toBeInTheDocument()
    expect(seen).toEqual([{ include: 'stats', clan: CLAN_ID }])
  })

  it('says a stat no endpoint backs is not yet counted, and shows no number for it', async () => {
    serveStats()
    renderWithProviders(<BackofficeDashboard locale="vi" />, { messages })
    await screen.findByTestId('approvals-badge')

    for (const label of [viMessages.dashboard.documents, bo.stat_tree_completeness]) {
      const item = tile(label)
      expect(within(item).getByText(expected(bo.stat_not_counted))).toBeInTheDocument()
      expect(item.textContent).not.toMatch(/\d/)
    }
  })

  it('shows no badge when nobody is waiting', async () => {
    serveStats(clanStatsDto({ pending_users: 0 }))
    renderWithProviders(<BackofficeDashboard locale="vi" />, { messages })

    expect(
      await within(tile(viMessages.admin.pending_approval)).findByText('0'),
    ).toBeInTheDocument()
    expect(screen.queryByTestId('approvals-badge')).toBeNull()
  })

  it('says the counts could not load, and invents none, when the read fails', async () => {
    server.use(
      http.get(`${API}/clans/me`, () =>
        HttpResponse.json(errorEnvelope('internal_error', 'boom'), { status: 500 }),
      ),
    )
    renderWithProviders(<BackofficeDashboard locale="vi" />, { messages })

    expect(await screen.findAllByText(expected(bo.stat_unavailable))).toHaveLength(2)
    expect(screen.queryByTestId('approvals-badge')).toBeNull()
  })

  it('reads its four stat labels in Vietnamese under the vi locale', async () => {
    serveStats()
    renderWithProviders(<BackofficeDashboard locale="vi" />, { messages })
    await screen.findByTestId('approvals-badge')

    for (const label of [
      viMessages.platform.total_members,
      viMessages.admin.pending_approval,
      viMessages.dashboard.documents,
      bo.stat_tree_completeness,
    ]) {
      expect(screen.getByText(expected(label))).toBeInTheDocument()
    }
  })
})
