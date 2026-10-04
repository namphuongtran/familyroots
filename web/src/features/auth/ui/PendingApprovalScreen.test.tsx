import { http, HttpResponse } from 'msw'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { components } from '@/generated/api-types'
import { createClientOrNull } from '@/shared/supabase/client'
import { clearClanCookie } from '@/shared/http/context.client'
import { envelope, errorEnvelope, server } from '@/shared/testing/msw'
import { renderWithProviders } from '@/shared/testing/render'
import { fakeSupabaseClient } from '@/shared/testing/supabase'
import { PendingApprovalScreen } from './PendingApprovalScreen'
import messages from '../../../../messages/vi.json'

/**
 * The real session hook runs: MSW serves `GET /auth/me` and `GET /me/clans` as the backend
 * sends them, and only the Supabase browser client is a fake. So "check again" is read as what
 * it does, a second read of the session, and its outcome is where the screen goes.
 */

const replace = vi.fn()
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn(), replace }) }))
vi.mock('next/link', () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}))
vi.mock('@/shared/supabase/client', () => ({ createClientOrNull: vi.fn() }))

const API = `${process.env.NEXT_PUBLIC_API_ORIGIN ?? 'http://localhost:8000'}/api/v1`
const CLAN_A = 'aaaaaaaa-0000-4000-8000-000000000001'

function pendingProfile(): components['schemas']['UserProfile'] {
  return {
    id: '11111111-1111-4111-8111-111111111111',
    email: 'lan@example.com',
    full_name: 'Nguyễn Thị Lan',
    clan_id: null,
    clan_name: null,
    role: null,
    is_approved: false,
    has_pending_membership: true,
    person_id: null,
    preferred_locale: 'vi',
    platform_role: 'user',
  }
}

const APPROVED_IN_A: components['schemas']['UserClanMembership'][] = [
  { clan_id: CLAN_A, clan_name: 'Nguyễn Phúc', clan_slug: 'nguyen-phuc', role: 'viewer' },
]

/** Each read of `/me/clans` takes the next answer; the last one repeats. */
function serveSession(clansAnswers: Array<() => Response>) {
  let reads = 0
  server.use(
    http.get(`${API}/auth/me`, () => HttpResponse.json(envelope(pendingProfile()))),
    http.get(`${API}/me/clans`, () => {
      const answer = clansAnswers[Math.min(reads, clansAnswers.length - 1)]
      reads += 1
      return answer()
    }),
  )
}

const stillPending = () => HttpResponse.json(envelope([]))

beforeEach(() => {
  replace.mockReset()
  vi.mocked(createClientOrNull).mockReturnValue(
    fakeSupabaseClient({ accessToken: 'tok-1' }).client as never,
  )
})

afterEach(() => clearClanCookie())

describe('PendingApprovalScreen (spec §7.2a)', () => {
  it('shows the three-step progress list, and names no clan it cannot know', async () => {
    serveSession([stillPending])

    renderWithProviders(<PendingApprovalScreen />, { messages })

    expect(await screen.findByText(messages.auth.pending_screen_body_no_clan)).toBeInTheDocument()
    // Does not promise a notification (the pending-approval screen's end state overrides the older
    // spec copy — see the component's own doc comment).
    expect(screen.queryByText(/thông báo/)).not.toBeInTheDocument()
    expect(screen.getByText('Tạo tài khoản')).toBeInTheDocument()
    expect(screen.getByText('Gửi yêu cầu tham gia')).toBeInTheDocument()
    expect(screen.getByText('Chờ quản trị duyệt')).toBeInTheDocument()
    expect(replace).not.toHaveBeenCalled()
  })

  it('check again, still pending: says so, and stays', async () => {
    serveSession([stillPending])
    renderWithProviders(<PendingApprovalScreen />, { messages })

    fireEvent.click(await screen.findByRole('button', { name: 'Kiểm tra lại' }))

    await waitFor(() =>
      expect(screen.getByRole('status')).toHaveTextContent('Yêu cầu của bạn vẫn đang chờ duyệt.'),
    )
    expect(replace).not.toHaveBeenCalled()
  })

  it('check again, approved in the meantime: goes to the dashboard', async () => {
    serveSession([stillPending, () => HttpResponse.json(envelope(APPROVED_IN_A))])
    renderWithProviders(<PendingApprovalScreen />, { messages })

    fireEvent.click(await screen.findByRole('button', { name: 'Kiểm tra lại' }))

    await waitFor(() => expect(replace).toHaveBeenCalledWith('/vi/dashboard'))
  })

  it('check again, and the read fails: says so, rather than claiming still pending', async () => {
    serveSession([
      stillPending,
      () => HttpResponse.json(errorEnvelope('internal_error', 'Lỗi hệ thống'), { status: 500 }),
    ])
    renderWithProviders(<PendingApprovalScreen />, { messages })

    fireEvent.click(await screen.findByRole('button', { name: 'Kiểm tra lại' }))

    await waitFor(() =>
      expect(screen.getByRole('status')).toHaveTextContent(
        messages.auth.pending_screen_recheck_error,
      ),
    )
  })

  it('renders nothing for a user who is not pending, and sends them where they belong', async () => {
    serveSession([() => HttpResponse.json(envelope(APPROVED_IN_A))])

    const { container } = renderWithProviders(<PendingApprovalScreen />, { messages })

    await waitFor(() => expect(replace).toHaveBeenCalledWith('/vi/dashboard'))
    expect(container).toBeEmptyDOMElement()
  })
})
