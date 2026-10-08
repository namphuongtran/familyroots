import { fireEvent, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it, vi } from 'vitest'
import { envelope, errorEnvelope, server } from '@/shared/testing/msw'
import { expected, renderWithProviders } from '@/shared/testing/render'
import { ForgotPasswordScreen } from './ForgotPasswordScreen'
import enMessages from '../../../../messages/en.json'
import viMessages from '../../../../messages/vi.json'

/**
 * #201. `POST /auth/forgot-password` answers 200 with one message for every address (ADR-021), so
 * the screen shows one message of its own for every 200 and never the server's, which a later
 * backend could word per case. The 200 body and the 429 body are the backend's
 * (`backend/app/api/v1/auth.py`, `backend/app/core/rate_limit.py`), read at source 2026-10-08.
 */

vi.mock('next/link', () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}))

const API = `${process.env.NEXT_PUBLIC_API_ORIGIN ?? 'http://localhost:8000'}/api/v1`
const FORGOT = `${API}/auth/forgot-password`

type Messages = typeof viMessages | typeof enMessages

function requestReset(messages: Messages, email: string) {
  fireEvent.change(screen.getByLabelText(expected(messages.auth.email)), {
    target: { value: email },
  })
  fireEvent.click(
    screen.getByRole('button', { name: expected(messages.auth.forgot_password_submit) }),
  )
}

describe('ForgotPasswordScreen (#201)', () => {
  it('sends the address, and shows the same message whatever the server says', async () => {
    const bodies: unknown[] = []
    const serverMessages = [
      'Nếu email này đã đăng ký, chúng tôi đã gửi liên kết đặt lại mật khẩu.',
      'A message a later backend might word differently for another address.',
    ]
    server.use(
      http.post(FORGOT, async ({ request }) => {
        bodies.push(await request.json())
        return HttpResponse.json(envelope({ message: serverMessages[bodies.length - 1] }))
      }),
    )

    renderWithProviders(<ForgotPasswordScreen />, { messages: viMessages })

    expect(
      screen.getByRole('heading', { name: expected(viMessages.auth.forgot_password_heading) }),
    ).toBeInTheDocument()

    requestReset(viMessages, 'lan@example.com')
    expect(await screen.findByRole('status')).toHaveTextContent(
      expected(viMessages.auth.forgot_password_sent),
    )

    requestReset(viMessages, 'no-account@example.com')
    await vi.waitFor(() => expect(bodies).toHaveLength(2))
    expect(await screen.findByRole('status')).toHaveTextContent(
      expected(viMessages.auth.forgot_password_sent),
    )

    expect(bodies).toEqual([{ email: 'lan@example.com' }, { email: 'no-account@example.com' }])
    for (const said of serverMessages) expect(screen.queryByText(said)).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows the rate-limit message on a 429, and never claims a mail was sent', async () => {
    server.use(
      http.post(FORGOT, () =>
        HttpResponse.json(
          errorEnvelope('rate_limited', 'Quá nhiều yêu cầu; vui lòng chậm lại', {
            retry_after: 42,
          }),
          { status: 429, headers: { 'Retry-After': '42' } },
        ),
      ),
    )

    renderWithProviders(<ForgotPasswordScreen />, { messages: viMessages })
    requestReset(viMessages, 'lan@example.com')

    expect(await screen.findByRole('alert')).toHaveTextContent(
      expected(viMessages.auth.forgot_password_rate_limited),
    )
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('shows a general error on any other failure', async () => {
    server.use(
      http.post(FORGOT, () =>
        HttpResponse.json(errorEnvelope('internal_error', 'Lỗi hệ thống'), { status: 500 }),
      ),
    )

    renderWithProviders(<ForgotPasswordScreen />, { messages: viMessages })
    requestReset(viMessages, 'lan@example.com')

    expect(await screen.findByRole('alert')).toHaveTextContent(
      expected(viMessages.auth.forgot_password_error),
    )
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('reads in the reader’s locale, with the URL’s locale on the way back', async () => {
    server.use(http.post(FORGOT, () => HttpResponse.json(envelope({ message: 'sent' }))))

    renderWithProviders(<ForgotPasswordScreen />, { locale: 'en', messages: enMessages })

    expect(
      screen.getByRole('link', { name: expected(enMessages.auth.verify_email_back_to_login) }),
    ).toHaveAttribute('href', '/en/login')

    requestReset(enMessages, 'lan@example.com')
    expect(await screen.findByRole('status')).toHaveTextContent(
      expected(enMessages.auth.forgot_password_sent),
    )
  })
})
