import { http, HttpResponse } from 'msw'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { useSearchParams } from 'next/navigation'
import { VerifyEmailScreen } from './VerifyEmailScreen'
import { envelope, errorEnvelope, server } from '@/shared/testing/msw'
import { expected, renderWithProviders } from '@/shared/testing/render'
import messages from '../../../../messages/vi.json'

vi.mock('next/navigation', () => ({ useSearchParams: vi.fn() }))
vi.mock('next/link', () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}))

const mockUseSearchParams = vi.mocked(useSearchParams)
const API = `${process.env.NEXT_PUBLIC_API_ORIGIN ?? 'http://localhost:8000'}/api/v1`

describe('VerifyEmailScreen (spec §7.1c surface 1)', () => {
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

  it('asks for the address when reached with none, and resends to the one typed', async () => {
    // The expired confirmation link sends a person here (#200), and a `token_hash` names no
    // address, so this screen is the one that asks for it.
    mockUseSearchParams.mockReturnValue(
      new URLSearchParams('') as unknown as ReturnType<typeof useSearchParams>,
    )
    let seenBody: unknown = null
    server.use(
      http.post(`${API}/auth/resend-verification`, async ({ request }) => {
        seenBody = await request.json()
        return HttpResponse.json(envelope({ message: 'Đã gửi lại thư xác thực.' }))
      }),
    )

    renderWithProviders(<VerifyEmailScreen />, { messages })

    expect(screen.getByText(expected(messages.auth.verify_email_body_no_email))).toBeInTheDocument()
    const resend = screen.getByRole('button', {
      name: expected(messages.auth.verify_email_resend_button),
    })
    expect(resend).toBeDisabled()
    // T-17: still a way forward with no email known.
    expect(
      screen.getByRole('link', { name: expected(messages.auth.verify_email_back_to_login) }),
    ).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText(expected(messages.auth.email)), {
      target: { value: '  lan@example.com ' },
    })
    expect(resend).toBeEnabled()
    fireEvent.click(resend)

    await waitFor(() =>
      expect(screen.getByRole('status')).toHaveTextContent(
        expected(messages.auth.verify_email_resend_sent),
      ),
    )
    expect(seenBody).toEqual({ email: 'lan@example.com' })
  })

  it('does not ask for an address the link already carried', () => {
    mockUseSearchParams.mockReturnValue(
      new URLSearchParams('email=lan%40example.com') as unknown as ReturnType<
        typeof useSearchParams
      >,
    )

    renderWithProviders(<VerifyEmailScreen />, { messages })

    expect(screen.queryByLabelText(expected(messages.auth.email))).not.toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: expected(messages.auth.verify_email_resend_button) }),
    ).toBeEnabled()
  })
})
