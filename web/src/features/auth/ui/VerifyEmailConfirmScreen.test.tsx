import { fireEvent, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useSearchParams } from 'next/navigation'
import { createClient } from '@/shared/supabase/client'
import { server } from '@/shared/testing/msw'
import { expected, renderWithProviders } from '@/shared/testing/render'
import { VerifyEmailConfirmScreen } from './VerifyEmailConfirmScreen'
import enMessages from '../../../../messages/en.json'
import viMessages from '../../../../messages/vi.json'

/**
 * #200, ADR-063 § 2 and § 3. The real Supabase browser client runs, and MSW stands in for GoTrue,
 * so what is counted is a request on the wire: `POST <supabase>/auth/v1/verify`. A fake client
 * would count calls to a method, which a mount effect could make through any other method.
 *
 * Both bodies were read from the local stack on 2026-10-07: the 200 is what GoTrue answered a
 * `token_hash` of a sign-up mail with `type: "email"`, and the 403 is what it answered the same
 * hash the second time. Tokens are placeholders; every other field keeps the shape GoTrue sent.
 */

vi.mock('next/navigation', () => ({ useSearchParams: vi.fn() }))
vi.mock('next/link', () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}))

const SUPABASE = 'https://verify-confirm-test.supabase.co'
const VERIFY = `${SUPABASE}/auth/v1/verify`
const TOKEN_HASH = 'a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c'
const ACCESS_TOKEN = 'access-token-from-verify'
const EMAIL = 'lan@example.com'
const USER_ID = 'b2e12273-cf25-447a-a129-039841e69ab2'

function verifiedSession() {
  const now = new Date().toISOString()
  return {
    access_token: ACCESS_TOKEN,
    token_type: 'bearer',
    expires_in: 3600,
    expires_at: Math.floor(Date.now() / 1000) + 3600,
    refresh_token: 'refresh-token-from-verify',
    user: {
      id: USER_ID,
      aud: 'authenticated',
      role: 'authenticated',
      email: EMAIL,
      email_confirmed_at: now,
      phone: '',
      confirmation_sent_at: now,
      confirmed_at: now,
      last_sign_in_at: now,
      app_metadata: { provider: 'email', providers: ['email'] },
      user_metadata: { email_verified: true },
      identities: [],
      created_at: now,
      updated_at: now,
      is_anonymous: false,
    },
  }
}

/** GoTrue's answer to a spent or unknown hash, under the API version auth-js sends. */
function otpExpired() {
  return HttpResponse.json(
    { code: 'otp_expired', message: 'Email link is invalid or has expired' },
    { status: 403, headers: { 'X-Supabase-Api-Version': '2024-01-01' } },
  )
}

/** Every `POST /auth/v1/verify` the page sends, with its body, answered by `respond`. */
function countVerify(respond: () => Response = () => HttpResponse.json(verifiedSession())) {
  const bodies: unknown[] = []
  server.use(
    http.post(VERIFY, async ({ request }) => {
      bodies.push(await request.json())
      return respond()
    }),
  )
  return bodies
}

function landOn(query: string) {
  vi.mocked(useSearchParams).mockReturnValue(
    new URLSearchParams(query) as unknown as ReturnType<typeof useSearchParams>,
  )
}

const LINK = `token_hash=${TOKEN_HASH}&type=email`

/** A press resolves through a real fetch, so each case then waits for the state it ends in. */
function pressConfirm(messages: typeof viMessages | typeof enMessages) {
  fireEvent.click(
    screen.getByRole('button', { name: expected(messages.auth.verify_confirm_button) }),
  )
}

beforeEach(() => {
  vi.stubEnv('NEXT_PUBLIC_SUPABASE_URL', SUPABASE)
  vi.stubEnv('NEXT_PUBLIC_SUPABASE_ANON_KEY', 'test-anon-key')
})

afterEach(async () => {
  // The browser client is one per page, and keeps the session in `document.cookie`, so a
  // session one case saved would otherwise reach the next.
  await createClient().auth.signOut({ scope: 'local' })
  for (const cookie of document.cookie.split(';')) {
    const name = cookie.split('=')[0]?.trim()
    if (name) document.cookie = `${name}=; max-age=0; path=/`
  }
  vi.unstubAllEnvs()
})

describe('VerifyEmailConfirmScreen (spec §7.1c surface 2, ADR-063)', () => {
  it('spends nothing on load, and spends the token once on a press', async () => {
    const bodies = countVerify()
    landOn(LINK)

    renderWithProviders(<VerifyEmailConfirmScreen />, { messages: viMessages })

    expect(
      screen.getByRole('heading', { name: expected(viMessages.auth.verify_confirm_heading) }),
    ).toBeInTheDocument()
    // Long enough for a mount effect's request to reach MSW, had the page sent one.
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(bodies).toHaveLength(0)

    pressConfirm(viMessages)

    await screen.findByRole('heading', {
      name: expected(viMessages.auth.verify_confirm_success_heading),
    })
    expect(bodies).toHaveLength(1)
    expect(bodies[0]).toMatchObject({ token_hash: TOKEN_HASH, type: 'email' })
  })

  it('shows the verifying state while the press is in flight, and no second press', async () => {
    let release: () => void = () => {}
    const held = new Promise<void>((resolve) => {
      release = resolve
    })
    const bodies: unknown[] = []
    server.use(
      http.post(VERIFY, async ({ request }) => {
        bodies.push(await request.json())
        await held
        return HttpResponse.json(verifiedSession())
      }),
    )
    landOn(LINK)

    renderWithProviders(<VerifyEmailConfirmScreen />, { messages: viMessages })
    pressConfirm(viMessages)

    expect(await screen.findByRole('status')).toHaveTextContent(
      expected(viMessages.auth.verify_confirm_verifying),
    )
    expect(
      screen.queryByRole('button', { name: expected(viMessages.auth.verify_confirm_button) }),
    ).not.toBeInTheDocument()

    release()
    await screen.findByRole('heading', {
      name: expected(viMessages.auth.verify_confirm_success_heading),
    })
    expect(bodies).toHaveLength(1)
  })

  it('keeps the session it was given, and goes on to the guarded entry', async () => {
    countVerify()
    landOn(LINK)

    renderWithProviders(<VerifyEmailConfirmScreen />, { messages: viMessages })
    pressConfirm(viMessages)

    await screen.findByRole('heading', {
      name: expected(viMessages.auth.verify_confirm_success_heading),
    })
    expect(
      screen.getByText(expected(viMessages.auth.verify_confirm_success_body)),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: expected(viMessages.member_form.continue_label) }),
    ).toHaveAttribute('href', '/vi/dashboard')

    // ADR-063 § 3: a confirmed person stays signed in. The next request the browser makes
    // carries this token.
    const { data } = await createClient().auth.getSession()
    expect(data.session?.access_token).toBe(ACCESS_TOKEN)
  })

  it('shows the expired state, with the resend, when Supabase refuses the token', async () => {
    const bodies = countVerify(otpExpired)
    landOn(LINK)

    renderWithProviders(<VerifyEmailConfirmScreen />, { messages: viMessages })
    pressConfirm(viMessages)

    await screen.findByRole('heading', {
      name: expected(viMessages.auth.verify_confirm_expired_heading),
    })
    expect(
      screen.getByRole('link', { name: expected(viMessages.auth.verify_email_resend_button) }),
    ).toHaveAttribute('href', '/vi/verify-email')
    expect(bodies).toHaveLength(1)

    const { data } = await createClient().auth.getSession()
    expect(data.session).toBeNull()
  })

  it.each([
    ['no token_hash', 'type=email'],
    ['an empty token_hash', 'token_hash=&type=email'],
    ['no type', `token_hash=${TOKEN_HASH}`],
    ['a type other than email', `token_hash=${TOKEN_HASH}&type=recovery`],
  ])('shows the expired state for a link with %s, and sends nothing', async (_, query) => {
    const bodies = countVerify()
    landOn(query)

    renderWithProviders(<VerifyEmailConfirmScreen />, { messages: viMessages })

    expect(
      screen.getByRole('heading', {
        name: expected(viMessages.auth.verify_confirm_expired_heading),
      }),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: expected(viMessages.auth.verify_confirm_button) }),
    ).not.toBeInTheDocument()
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(bodies).toHaveLength(0)
  })

  it('reads in the reader’s locale, with the URL’s locale on every link', async () => {
    countVerify()
    landOn(LINK)

    renderWithProviders(<VerifyEmailConfirmScreen />, { locale: 'en', messages: enMessages })
    pressConfirm(enMessages)

    await screen.findByRole('heading', {
      name: expected(enMessages.auth.verify_confirm_success_heading),
    })
    expect(
      screen.getByRole('link', { name: expected(enMessages.member_form.continue_label) }),
    ).toHaveAttribute('href', '/en/dashboard')
  })
})
