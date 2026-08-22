import { http, HttpResponse } from 'msw'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { useSearchParams } from 'next/navigation'
import { VerifyEmailScreen } from './VerifyEmailScreen'
import { envelope, errorEnvelope, server } from '@/shared/testing/msw'
import { renderWithProviders } from '@/shared/testing/render'
import messages from '../../../messages/vi.json'

vi.mock('next/navigation', () => ({ useSearchParams: vi.fn() }))
vi.mock('next/link', () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}))

const mockUseSearchParams = vi.mocked(useSearchParams)
const API = `${process.env.NEXT_PUBLIC_API_ORIGIN ?? 'http://localhost:8000'}/api/v1`

describe('VerifyEmailScreen (S-026, spec §7.1c surface 1)', () => {
  it('shows the email in the body and resends against the real envelope on click', async () => {
    mockUseSearchParams.mockReturnValue(
      new URLSearchParams('email=lan%40example.com') as unknown as ReturnType<
        typeof useSearchParams
      >,
    )
    let seenBody: unknown = null
    server.use(
      http.post(`${API}/auth/resend-verification`, async ({ request }) => {
        seenBody = await request.json()
        return HttpResponse.json(envelope({ message: 'Đã gửi lại thư xác thực.' }))
      }),
    )

    renderWithProviders(<VerifyEmailScreen />, { messages })

    expect(screen.getByText(/lan@example\.com/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Gửi lại thư xác thực' }))

    await waitFor(() =>
      expect(screen.getByRole('status')).toHaveTextContent('Đã gửi lại thư xác thực'),
    )
    expect(seenBody).toEqual({ email: 'lan@example.com' })

    // The cooldown replaces the button's own label with a countdown, and
    // disables it.
    expect(screen.getByRole('button')).toBeDisabled()
    expect(screen.getByRole('button').textContent).toMatch(/Gửi lại sau \d+ giây/)
  })

  it('shows the resend-error state on a failed resend, and never claims success', async () => {
    mockUseSearchParams.mockReturnValue(
      new URLSearchParams('email=lan%40example.com') as unknown as ReturnType<
        typeof useSearchParams
      >,
    )
    server.use(
      http.post(`${API}/auth/resend-verification`, () =>
        HttpResponse.json(errorEnvelope('internal_error', 'Lỗi hệ thống'), { status: 500 }),
      ),
    )

    renderWithProviders(<VerifyEmailScreen />, { messages })

    fireEvent.click(screen.getByRole('button', { name: 'Gửi lại thư xác thực' }))

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('Không thể gửi lại thư xác thực'),
    )
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('falls back to the no-email copy and disables resend when reached with no address', () => {
    mockUseSearchParams.mockReturnValue(
      new URLSearchParams('') as unknown as ReturnType<typeof useSearchParams>,
    )

    renderWithProviders(<VerifyEmailScreen />, { messages })

    expect(
      screen.getByText(
        'Email của bạn chưa được xác thực. Xin mở hộp thư và bấm vào liên kết xác thực để tiếp tục đăng nhập.',
      ),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Gửi lại thư xác thực' })).toBeDisabled()
    // T-17: still a way forward with no email known.
    expect(screen.getByRole('link', { name: 'Về trang đăng nhập' })).toBeInTheDocument()
  })
})
