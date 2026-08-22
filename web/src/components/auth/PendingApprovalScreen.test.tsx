import { http, HttpResponse } from 'msw'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { useAuth } from '@/lib/hooks/useAuth'
import { PendingApprovalScreen } from './PendingApprovalScreen'
import { envelope, server } from '@/shared/testing/msw'
import { renderWithProviders } from '@/shared/testing/render'
import messages from '../../../messages/vi.json'

vi.mock('@/lib/hooks/useAuth', () => ({ useAuth: vi.fn() }))
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn(), replace: vi.fn() }) }))
vi.mock('next/link', () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}))

const mockUseAuth = vi.mocked(useAuth)
const API = `${process.env.NEXT_PUBLIC_API_ORIGIN ?? 'http://localhost:8000'}/api/v1`

function pendingAuthState(overrides: Partial<ReturnType<typeof useAuth>> = {}) {
  return {
    user: { clan_name: 'Nguyễn Hữu Thanh Oai' },
    currentClanId: undefined,
    clanMemberships: [],
    isLoading: false,
    isPendingApproval: true,
    needsOnboarding: false,
    needsClanSelection: false,
    isAuthenticated: true,
    isApproved: false,
    signInWithEmail: vi.fn(),
    signInWithGoogle: vi.fn(),
    signInWithApple: vi.fn(),
    signOut: vi.fn(),
    selectClan: vi.fn(),
    completeOnboarding: vi.fn(),
    syncAuthContext: vi.fn(async () => {}),
    ...overrides,
  } as unknown as ReturnType<typeof useAuth>
}

describe('PendingApprovalScreen (S-026, spec §7.2a)', () => {
  beforeEach(() => {
    mockUseAuth.mockReset()
  })

  it('shows the clan name from useAuth and the three-step progress list', () => {
    mockUseAuth.mockReturnValue(pendingAuthState())

    renderWithProviders(<PendingApprovalScreen />, { messages })

    expect(
      screen.getByText(
        'Bạn đã gửi yêu cầu tham gia dòng họ Nguyễn Hữu Thanh Oai. Quản trị dòng họ sẽ xem xét yêu cầu này.',
      ),
    ).toBeInTheDocument()
    // Does not promise a notification (S-026's end state overrides the older
    // spec copy — see the component's own doc comment).
    expect(screen.queryByText(/thông báo/)).not.toBeInTheDocument()
    expect(screen.getByText('Tạo tài khoản')).toBeInTheDocument()
    expect(screen.getByText('Gửi yêu cầu tham gia')).toBeInTheDocument()
    expect(screen.getByText('Chờ quản trị duyệt')).toBeInTheDocument()
  })

  it('falls back to the no-clan-name copy when the clan name is unknown', () => {
    mockUseAuth.mockReturnValue(pendingAuthState({ user: {} as never }))

    renderWithProviders(<PendingApprovalScreen />, { messages })

    expect(
      screen.getByText(
        'Bạn đã gửi yêu cầu tham gia một dòng họ. Quản trị dòng họ sẽ xem xét yêu cầu này.',
      ),
    ).toBeInTheDocument()
  })

  it('recheck against the real GET /auth/me envelope: still pending shows the pending toast', async () => {
    mockUseAuth.mockReturnValue(pendingAuthState())
    server.use(
      http.get(`${API}/auth/me`, () => HttpResponse.json(envelope({ is_approved: false }))),
    )

    renderWithProviders(<PendingApprovalScreen />, { messages })
    fireEvent.click(screen.getByRole('button', { name: 'Kiểm tra lại' }))

    await waitFor(() =>
      expect(screen.getByRole('status')).toHaveTextContent('Yêu cầu của bạn vẫn đang chờ duyệt.'),
    )
  })

  it('recheck against the real GET /auth/me envelope: approved refreshes the session before leaving', async () => {
    const syncAuthContext = vi.fn(async () => {})
    mockUseAuth.mockReturnValue(pendingAuthState({ syncAuthContext }))
    server.use(http.get(`${API}/auth/me`, () => HttpResponse.json(envelope({ is_approved: true }))))

    renderWithProviders(<PendingApprovalScreen />, { messages })
    fireEvent.click(screen.getByRole('button', { name: 'Kiểm tra lại' }))

    await waitFor(() => expect(syncAuthContext).toHaveBeenCalledTimes(1))
  })

  it('renders nothing once the membership is no longer pending (mid-redirect)', () => {
    mockUseAuth.mockReturnValue(pendingAuthState({ isPendingApproval: false }))

    const { container } = renderWithProviders(<PendingApprovalScreen />, { messages })

    expect(container).toBeEmptyDOMElement()
  })
})
