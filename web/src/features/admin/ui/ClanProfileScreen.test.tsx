import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import type { AbstractIntlMessages } from 'next-intl'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { clearClanCookie, writeClanCookie } from '@/shared/http/context.client'
import { createClientOrNull } from '@/shared/supabase/client'
import { envelope, server } from '@/shared/testing/msw'
import { expected, renderWithProviders } from '@/shared/testing/render'
import { fakeSupabaseClient } from '@/shared/testing/supabase'
import viMessages from '../../../../messages/vi.json'
import { CLAN_ID, clanResponseDto } from '../model/clan-fixtures'
import { ClanProfileScreen } from './ClanProfileScreen'

/**
 * The clan profile form, against MSW.
 *
 * #194's reading moved here from the old page test: while the profile loads, the form says so
 * through `common.loading`, in Vietnamese.
 *
 * #314: a save sends only the four fields the form edits. The legacy form sent the whole row back,
 * `id`, `slug`, `is_active` and the timestamps included, which `PATCH /clans/me` refuses with
 * `422 field_not_updatable`. `toClanUpdateRequest` already drops keys outside the eight the
 * contract accepts, so what this case guards is the form blanking fields it never showed.
 * Negative control, 2026-11-22: with the loaded profile spread into the update ahead of the form
 * values, the case failed, the body carrying `motto`, `avatar_url`, `clan_rules` and
 * `ancestral_hall_location` as `null`, four fields the form does not edit.
 */

vi.mock('@/shared/supabase/client', () => ({ createClientOrNull: vi.fn() }))

const messages = viMessages as unknown as AbstractIntlMessages
const API = `${process.env.NEXT_PUBLIC_API_ORIGIN ?? 'http://localhost:8000'}/api/v1`

beforeEach(() => {
  vi.mocked(createClientOrNull).mockReturnValue(
    fakeSupabaseClient({ accessToken: 'tok-1' }).client as never,
  )
  writeClanCookie(CLAN_ID)
})

afterEach(() => {
  clearClanCookie()
})

describe('the clan profile form', () => {
  it('says in Vietnamese that it is loading while its profile loads', () => {
    server.use(http.get(`${API}/clans/me`, () => new Promise<never>(() => {})))
    renderWithProviders(<ClanProfileScreen />, { messages })

    expect(screen.getByText(expected(viMessages.common.loading))).toBeInTheDocument()
  })

  it('sends only the edited fields, an emptied one as null', async () => {
    const user = userEvent.setup()
    let body: unknown = null
    server.use(
      http.get(`${API}/clans/me`, () => HttpResponse.json(envelope(clanResponseDto()))),
      http.patch(`${API}/clans/me`, async ({ request }) => {
        body = await request.json()
        return HttpResponse.json(envelope(clanResponseDto({ name: 'Nguyễn Phúc tộc' })))
      }),
    )
    renderWithProviders(<ClanProfileScreen />, { messages })

    const name = await screen.findByDisplayValue('Nguyễn Phúc')
    await user.clear(name)
    await user.type(name, 'Nguyễn Phúc tộc')
    const origin = screen.getByDisplayValue('Huế')
    await user.clear(origin)
    await user.click(screen.getByRole('button', { name: expected(viMessages.admin.save_changes) }))

    await waitFor(() => expect(body).not.toBeNull())
    expect(body).toEqual({
      name: 'Nguyễn Phúc tộc',
      description: 'Dòng họ Nguyễn Phúc ở Huế',
      founded_year: 1750,
      origin_place: null,
    })
  })
})
