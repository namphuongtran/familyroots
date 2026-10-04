import { screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import type { AbstractIntlMessages } from 'next-intl'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ClanRole } from '@/domain/capability/capability'
import { useSession } from '@/features/auth'
import type { components } from '@/generated/api-types'
import { clearClanCookie, writeClanCookie } from '@/shared/http/context.client'
import { createClientOrNull } from '@/shared/supabase/client'
import { envelope, server } from '@/shared/testing/msw'
import { renderWithProviders } from '@/shared/testing/render'
import { fakeSupabaseClient } from '@/shared/testing/supabase'
import viMessages from '../../../../../../messages/vi.json'
import NewMemberPage from './page'

/**
 * #185: the create route gates on `editPerson`, read from `useCapabilities()` in `@/features/auth`
 * through the real session hook. MSW serves `GET /auth/me` and the `GET /me/clans` envelope, so
 * the role the page gates on is the role the backend sent. Only the Supabase browser client is a
 * fake.
 *
 * Each case waits until the session has settled on the active clan before reading the page.
 * Every capability is false while the session loads, so the page shows its no-permission line
 * then too, and a viewer case read before the session arrived would pass whatever role came back.
 */

vi.mock('@/shared/supabase/client', () => ({ createClientOrNull: vi.fn() }))
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), back: vi.fn() }),
  useParams: () => ({ locale: 'vi' }),
}))

const messages = viMessages as unknown as AbstractIntlMessages
const API = `${process.env.NEXT_PUBLIC_API_ORIGIN ?? 'http://localhost:8000'}/api/v1`
const CLAN_A = 'aaaaaaaa-0000-4000-8000-000000000001'

function profile(): components['schemas']['UserProfile'] {
  return {
    id: '11111111-1111-4111-8111-111111111111',
    email: 'lan@example.com',
    full_name: 'Nguyễn Thị Lan',
    clan_id: CLAN_A,
    clan_name: 'Nguyễn Phúc',
    role: null,
    is_approved: true,
    has_pending_membership: false,
    person_id: null,
    preferred_locale: 'vi',
    platform_role: 'user',
  }
}

function serveSessionAs(role: ClanRole) {
  server.use(
    http.get(`${API}/auth/me`, () => HttpResponse.json(envelope(profile()))),
    http.get(`${API}/me/clans`, () =>
      HttpResponse.json(
        envelope<components['schemas']['UserClanMembership'][]>([
          { clan_id: CLAN_A, clan_name: 'Nguyễn Phúc', clan_slug: 'nguyen-phuc', role },
        ]),
      ),
    ),
  )
}

function ActiveRole() {
  return <p data-testid="active-role">{useSession().activeClan?.role ?? 'none'}</p>
}

async function renderPageAs(role: ClanRole) {
  serveSessionAs(role)
  renderWithProviders(
    <>
      <ActiveRole />
      <NewMemberPage />
    </>,
    { messages },
  )
  await waitFor(() => expect(screen.getByTestId('active-role')).toHaveTextContent(role))
}

beforeEach(() => {
  vi.mocked(createClientOrNull).mockReturnValue(
    fakeSupabaseClient({ accessToken: 'tok-1' }).client as never,
  )
  writeClanCookie(CLAN_A)
})

afterEach(() => {
  clearClanCookie()
})

describe('members/new gates on editPerson', () => {
  it('an editor sees the create form', async () => {
    await renderPageAs('editor')

    expect(screen.getByRole('heading', { name: 'Thêm thành viên' })).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: 'Lưu' })).toBeInTheDocument()
    expect(screen.queryByText('Bạn không có quyền chỉnh sửa thành viên.')).not.toBeInTheDocument()
  })

  it('a viewer sees the no-permission line, and no form', async () => {
    await renderPageAs('viewer')

    expect(screen.getByText('Bạn không có quyền chỉnh sửa thành viên.')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Thêm thành viên' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Lưu' })).not.toBeInTheDocument()
  })
})
