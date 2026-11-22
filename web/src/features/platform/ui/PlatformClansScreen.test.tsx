import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { components } from '@/generated/api-types'
import { clearClanCookie, writeClanCookie } from '@/shared/http/context.client'
import { createClientOrNull } from '@/shared/supabase/client'
import { pageEnvelope, server } from '@/shared/testing/msw'
import { expected, renderWithProviders } from '@/shared/testing/render'
import { fakeSupabaseClient } from '@/shared/testing/supabase'
import enMessages from '../../../../messages/en.json'
import { PlatformClansScreen } from './PlatformClansScreen'

/**
 * #194: the platform clan list said `Đang tải…` while loading and `Hoạt động` / `Tạm ngưng` on each
 * clan's status, in Vietnamese for every locale. The status is the only text channel the badge
 * has (ADR-055), so an English super_admin could not read it. These readings moved here from the
 * old page test, which mocked the legacy hook; they now go through MSW.
 *
 * #314: the platform is not clan-scoped, so no `X-Current-Clan-Id` leaves even with a clan cookie
 * set.
 */

vi.mock('@/shared/supabase/client', () => ({ createClientOrNull: vi.fn() }))

const API = `${process.env.NEXT_PUBLIC_API_ORIGIN ?? 'http://localhost:8000'}/api/v1`

function clan(id: string, isActive: boolean): components['schemas']['ClanSummaryResponse'] {
  return { id, name: `Clan ${id}`, slug: `clan-${id}`, is_active: isActive, created_at: null }
}

beforeEach(() => {
  vi.mocked(createClientOrNull).mockReturnValue(
    fakeSupabaseClient({ accessToken: 'tok-1' }).client as never,
  )
  writeClanCookie('aaaaaaaa-0000-4000-8000-000000000001')
})

afterEach(() => {
  clearClanCookie()
})

describe('the platform clan list, under the en locale', () => {
  it('says it is loading in English', () => {
    server.use(http.get(`${API}/platform/clans`, () => new Promise<never>(() => {})))
    renderWithProviders(<PlatformClansScreen />, { locale: 'en', messages: enMessages })

    expect(screen.getByText(expected(enMessages.common.loading))).toBeInTheDocument()
  })

  it("reads each clan's status in English, with no clan header sent", async () => {
    const clanHeaders: (string | null)[] = []
    server.use(
      http.get(`${API}/platform/clans`, ({ request }) => {
        clanHeaders.push(request.headers.get('x-current-clan-id'))
        return HttpResponse.json(pageEnvelope([clan('a', true), clan('b', false)]))
      }),
    )
    renderWithProviders(<PlatformClansScreen />, { locale: 'en', messages: enMessages })

    expect(await screen.findByText(expected(enMessages.platform.active))).toBeInTheDocument()
    expect(screen.getByText(expected(enMessages.platform.inactive))).toBeInTheDocument()
    expect(clanHeaders).toEqual([null])
  })
})
