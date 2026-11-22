import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import type { AbstractIntlMessages } from 'next-intl'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { clearClanCookie, writeClanCookie } from '@/shared/http/context.client'
import { createClientOrNull } from '@/shared/supabase/client'
import { envelope, pageEnvelope, server } from '@/shared/testing/msw'
import { expected, renderWithProviders } from '@/shared/testing/render'
import { fakeSupabaseClient } from '@/shared/testing/supabase'
import viMessages from '../../../../messages/vi.json'
import { CLAN_ID, clanUserDto, pendingClanUserDto } from '../model/clan-fixtures'
import { AdminUsersScreen } from './AdminUsersScreen'

/**
 * The admin users screen, through the real request context against MSW handlers that build the
 * contract's envelopes (docs/contracts/rest-clans-api.md, "User list rows").
 *
 * #194's readings moved here from the old page test, which mocked the legacy hook: each approved
 * member's second line names the linked person or says none is linked, in Vietnamese.
 *
 * #314: a pending account is named by its display name, then its email, never its raw id when
 * either exists; approving one sends `POST …/approve` and the queue refetches.
 */

vi.mock('@/shared/supabase/client', () => ({ createClientOrNull: vi.fn() }))

const messages = viMessages as unknown as AbstractIntlMessages
const API = `${process.env.NEXT_PUBLIC_API_ORIGIN ?? 'http://localhost:8000'}/api/v1`
const PERSON_ID = 'cccccccc-0000-4000-8000-000000000003'

let pending: ReturnType<typeof pendingClanUserDto>[]
let writes: string[]

function serve() {
  server.use(
    http.get(`${API}/clans/me/users`, () =>
      HttpResponse.json(
        pageEnvelope([
          clanUserDto({ id: 'r-l', user_id: 'u-linked', person_id: PERSON_ID }),
          clanUserDto({ id: 'r-u', user_id: 'u-unlinked', display_name: 'Trần Văn An' }),
        ]),
      ),
    ),
    http.get(`${API}/clans/me/users/pending`, () => HttpResponse.json(pageEnvelope([...pending]))),
    http.post(`${API}/clans/me/users/:userId/approve`, ({ params, request }) => {
      writes.push(`approve ${String(params.userId)} ${request.headers.get('x-current-clan-id')}`)
      pending = pending.filter((p) => p.user_id !== params.userId)
      return HttpResponse.json(envelope({ message: 'approved' }))
    }),
  )
}

beforeEach(() => {
  pending = [
    pendingClanUserDto({ user_id: 'u-p1', display_name: 'Lê Thị Hoa', email: 'hoa@example.com' }),
    pendingClanUserDto({ id: 'r-p2', user_id: 'u-p2', email: 'binh@example.com' }),
  ]
  writes = []
  vi.mocked(createClientOrNull).mockReturnValue(
    fakeSupabaseClient({ accessToken: 'tok-1' }).client as never,
  )
  writeClanCookie(CLAN_ID)
  serve()
})

afterEach(() => {
  clearClanCookie()
})

describe("an approved member's linked person, under the vi locale", () => {
  it('names the linked person in Vietnamese', async () => {
    renderWithProviders(<AdminUsersScreen />, { messages })

    expect(
      await screen.findByText(expected(viMessages.admin.linked_person).replace('{id}', PERSON_ID)),
    ).toBeInTheDocument()
  })

  it('says in Vietnamese that no person is linked', async () => {
    renderWithProviders(<AdminUsersScreen />, { messages })

    expect(await screen.findByText(expected(viMessages.admin.no_linked_person))).toBeInTheDocument()
    expect(screen.getByText('Trần Văn An')).toBeInTheDocument()
  })
})

describe('the pending queue', () => {
  it('names each account by display name, else email', async () => {
    renderWithProviders(<AdminUsersScreen />, { messages })

    expect(await screen.findByText('Lê Thị Hoa')).toBeInTheDocument()
    expect(screen.getByText('binh@example.com')).toBeInTheDocument()
    expect(screen.queryByText('u-p1')).toBeNull()
  })

  it('approves an account in the active clan, and the queue refetches without it', async () => {
    const user = userEvent.setup()
    renderWithProviders(<AdminUsersScreen />, { messages })
    await screen.findByText('Lê Thị Hoa')

    const [first] = screen.getAllByRole('button', { name: expected(viMessages.admin.approve) })
    await user.click(first!)

    await waitFor(() => expect(screen.queryByText('Lê Thị Hoa')).toBeNull())
    expect(writes).toEqual([`approve u-p1 ${CLAN_ID}`])
    expect(screen.getByText('binh@example.com')).toBeInTheDocument()
  })
})
