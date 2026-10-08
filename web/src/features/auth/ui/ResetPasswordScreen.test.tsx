import { fireEvent, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useSearchParams } from 'next/navigation'
import { createClient } from '@/shared/supabase/client'
import { server } from '@/shared/testing/msw'
import { expected, renderWithProviders } from '@/shared/testing/render'
import { ResetPasswordScreen } from './ResetPasswordScreen'
import enMessages from '../../../../messages/en.json'
import viMessages from '../../../../messages/vi.json'

/**
 * #201, ADR-063 § 2 and § 3. The real Supabase browser client runs, and MSW stands in for GoTrue,
 * so what is counted is a request on the wire, in the order it left: `POST <supabase>/auth/v1/verify`
 * and `PUT <supabase>/auth/v1/user`. A fake client would count calls to a method.
 *
 * The two 422 bodies were read from the local stack on 2026-10-08, by `PUT /auth/v1/user` as a
 * seeded user with `"a"` and with the seeded password itself. The 403 is #200's, read the same
 * way. Tokens are placeholders; every other field keeps the shape GoTrue sent.
 */

vi.mock('next/navigation', () => ({ useSearchParams: vi.fn() }))
vi.mock('next/link', () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}))

const SUPABASE = 'https://reset-password-test.supabase.co'
const VERIFY = `${SUPABASE}/auth/v1/verify`
const USER = `${SUPABASE}/auth/v1/user`
const TOKEN_HASH = 'f0e1d2c3b4a5968778695a4b3c2d1e0ff0e1d2c3b4a5968778695a4b'
const ACCESS_TOKEN = 'access-token-from-recovery'
const EMAIL = 'lan@example.com'
const USER_ID = 'b2e12273-cf25-447a-a129-039841e69ab2'
const NEW_PASSWORD = 'a-new-password-201'

function user() {
  const now = new Date().toISOString()
  return {
    id: USER_ID,
    aud: 'authenticated',
    role: 'authenticated',
    email: EMAIL,
    email_confirmed_at: now,
    phone: '',
    recovery_sent_at: now,
    confirmed_at: now,
    last_sign_in_at: now,
    app_metadata: { provider: 'email', providers: ['email'] },
    user_metadata: { email_verified: true },
    identities: [],
    created_at: now,
    updated_at: now,
    is_anonymous: false,
  }
}

function recoveredSession() {
  return {
    access_token: ACCESS_TOKEN,
    token_type: 'bearer',
    expires_in: 3600,
    expires_at: Math.floor(Date.now() / 1000) + 3600,
    refresh_token: 'refresh-token-from-recovery',
    user: user(),
  }
}

const API_VERSION = { 'X-Supabase-Api-Version': '2024-01-01' }

function otpExpired() {
  return HttpResponse.json(
    { code: 'otp_expired', message: 'Email link is invalid or has expired' },
    { status: 403, headers: API_VERSION },
  )
}

function weakPassword() {
  return HttpResponse.json(
    {
      code: 'weak_password',
      message: 'Password should be at least 6 characters.',
      weak_password: { reasons: ['length'] },
    },
    { status: 422, headers: API_VERSION },
  )
}

function samePassword() {
  return HttpResponse.json(
    { code: 'same_password', message: 'New password should be different from the old password.' },
    { status: 422, headers: API_VERSION },
  )
}

interface Sent {
  kind: 'verify' | 'update'
  body: Record<string, unknown>
  authorization: string | null
}

/**
 * Every verify and every update the page sends, in the order they left, each answered by its own
 * responder. The responders see how many of their kind came before.
 */
function recordGoTrue(
  answer: {
    verify?: (n: number) => Response | Promise<Response>
    update?: (n: number) => Response | Promise<Response>
  } = {},
): Sent[] {
  const sent: Sent[] = []
  const verify = answer.verify ?? (() => HttpResponse.json(recoveredSession()))
  const update = answer.update ?? (() => HttpResponse.json(user()))
  server.use(
    http.post(VERIFY, async ({ request }) => {
      const n = sent.filter((s) => s.kind === 'verify').length
      sent.push({
        kind: 'verify',
        body: (await request.json()) as Record<string, unknown>,
        authorization: request.headers.get('authorization'),
      })
      return verify(n)
    }),
    http.put(USER, async ({ request }) => {
      const n = sent.filter((s) => s.kind === 'update').length
      sent.push({
        kind: 'update',
        body: (await request.json()) as Record<string, unknown>,
        authorization: request.headers.get('authorization'),
      })
      return update(n)
    }),
  )
  return sent
}

function landOn(query: string) {
  vi.mocked(useSearchParams).mockReturnValue(
    new URLSearchParams(query) as unknown as ReturnType<typeof useSearchParams>,
  )
}

const LINK = `token_hash=${TOKEN_HASH}&type=recovery`

/** Long enough for a mount effect's request to reach MSW, had the page sent one. */
function settle() {
  return new Promise((resolve) => setTimeout(resolve, 50))
}

function typePassword(messages: typeof viMessages | typeof enMessages, password: string) {
  fireEvent.change(screen.getByLabelText(expected(messages.auth.reset_password_new_password)), {
    target: { value: password },
  })
}

function submit(messages: typeof viMessages | typeof enMessages) {
  fireEvent.click(
    screen.getByRole('button', { name: expected(messages.auth.reset_password_submit) }),
  )
}

beforeEach(() => {
  vi.stubEnv('NEXT_PUBLIC_SUPABASE_URL', SUPABASE)
  vi.stubEnv('NEXT_PUBLIC_SUPABASE_ANON_KEY', 'test-anon-key')
})

afterEach(async () => {
  // The browser client is one per page, and keeps the session in `document.cookie`, so a
  // session one case saved would otherwise reach the next. Signing out sends `/logout`.
  server.use(http.post(`${SUPABASE}/auth/v1/logout`, () => new HttpResponse(null, { status: 204 })))
  await createClient().auth.signOut({ scope: 'local' })
  for (const cookie of document.cookie.split(';')) {
    const name = cookie.split('=')[0]?.trim()
    if (name) document.cookie = `${name}=; max-age=0; path=/`
  }
  vi.unstubAllEnvs()
})

describe('ResetPasswordScreen (ADR-063 § 2, § 3)', () => {
  it('shows the form at once and spends nothing on load; a submit verifies, then updates', async () => {
    const sent = recordGoTrue()
    landOn(LINK)

    renderWithProviders(<ResetPasswordScreen />, { messages: viMessages })

    expect(
      screen.getByRole('heading', { name: expected(viMessages.auth.reset_password_heading) }),
    ).toBeInTheDocument()
    expect(
      screen.getByLabelText(expected(viMessages.auth.reset_password_new_password)),
    ).toBeInTheDocument()
    await settle()
    expect(sent).toEqual([])

    typePassword(viMessages, NEW_PASSWORD)
    submit(viMessages)

    await screen.findByRole('heading', {
      name: expected(viMessages.auth.reset_password_success_heading),
    })
    expect(sent.map((s) => s.kind)).toEqual(['verify', 'update'])
    expect(sent[0]?.body).toMatchObject({ token_hash: TOKEN_HASH, type: 'recovery' })
    expect(sent[1]?.body).toMatchObject({ password: NEW_PASSWORD })
    // The update rides on the session the verify returned.
    expect(sent[1]?.authorization).toBe(`Bearer ${ACCESS_TOKEN}`)
  })

  it('a retry after a refused update sends an update and no verify', async () => {
    const sent = recordGoTrue({
      update: (n) => (n === 0 ? weakPassword() : HttpResponse.json(user())),
    })
    landOn(LINK)

    renderWithProviders(<ResetPasswordScreen />, { messages: viMessages })
    typePassword(viMessages, 'a')
    submit(viMessages)

    expect(await screen.findByRole('alert')).toHaveTextContent(
      expected(viMessages.auth.reset_password_weak),
    )
    expect(sent.map((s) => s.kind)).toEqual(['verify', 'update'])
    // Still the form, not the expired state: the token is spent and the session holds.
    expect(
      screen.getByLabelText(expected(viMessages.auth.reset_password_new_password)),
    ).toBeInTheDocument()

    typePassword(viMessages, NEW_PASSWORD)
    submit(viMessages)

    await screen.findByRole('heading', {
      name: expected(viMessages.auth.reset_password_success_heading),
    })
    expect(sent.map((s) => s.kind)).toEqual(['verify', 'update', 'update'])
    expect(sent[2]?.body).toMatchObject({ password: NEW_PASSWORD })
  })

  it('names the same-password refusal on the form', async () => {
    recordGoTrue({ update: () => samePassword() })
    landOn(LINK)

    renderWithProviders(<ResetPasswordScreen />, { messages: viMessages })
    typePassword(viMessages, NEW_PASSWORD)
    submit(viMessages)

    expect(await screen.findByRole('alert')).toHaveTextContent(
      expected(viMessages.auth.reset_password_same),
    )
  })

  it('submits once when the button is pressed twice before the first submit settles', async () => {
    let release: () => void = () => {}
    const held = new Promise<void>((resolve) => {
      release = resolve
    })
    const sent = recordGoTrue({
      verify: async () => {
        await held
        return HttpResponse.json(recoveredSession())
      },
    })
    landOn(LINK)

    renderWithProviders(<ResetPasswordScreen />, { messages: viMessages })
    typePassword(viMessages, NEW_PASSWORD)
    submit(viMessages)
    fireEvent.submit(
      screen.getByLabelText(expected(viMessages.auth.reset_password_new_password)).closest('form')!,
    )

    release()
    await screen.findByRole('heading', {
      name: expected(viMessages.auth.reset_password_success_heading),
    })
    await settle()
    expect(sent.map((s) => s.kind)).toEqual(['verify', 'update'])
  })

  it('keeps the session, and goes on to the guarded entry', async () => {
    recordGoTrue()
    landOn(LINK)

    renderWithProviders(<ResetPasswordScreen />, { messages: viMessages })
    typePassword(viMessages, NEW_PASSWORD)
    submit(viMessages)

    await screen.findByRole('heading', {
      name: expected(viMessages.auth.reset_password_success_heading),
    })
    expect(
      screen.getByText(expected(viMessages.auth.reset_password_success_body)),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: expected(viMessages.member_form.continue_label) }),
    ).toHaveAttribute('href', '/vi/dashboard')

    // ADR-063 § 3: a person who reset their password stays signed in.
    const { data } = await createClient().auth.getSession()
    expect(data.session?.access_token).toBe(ACCESS_TOKEN)
  })

  it('shows the expired state, with a link to ask again, when Supabase refuses the token', async () => {
    const sent = recordGoTrue({ verify: () => otpExpired() })
    landOn(LINK)

    renderWithProviders(<ResetPasswordScreen />, { messages: viMessages })
    typePassword(viMessages, NEW_PASSWORD)
    submit(viMessages)

    await screen.findByRole('heading', {
      name: expected(viMessages.auth.verify_confirm_expired_heading),
    })
    expect(
      screen.getByText(expected(viMessages.auth.reset_password_expired_body)),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: expected(viMessages.auth.reset_password_request_new) }),
    ).toHaveAttribute('href', '/vi/forgot-password')
    expect(sent.map((s) => s.kind)).toEqual(['verify'])

    const { data } = await createClient().auth.getSession()
    expect(data.session).toBeNull()
  })

  it.each([
    ['no token_hash', 'type=recovery'],
    ['an empty token_hash', 'token_hash=&type=recovery'],
    ['no type', `token_hash=${TOKEN_HASH}`],
    ['a type other than recovery', `token_hash=${TOKEN_HASH}&type=email`],
  ])('shows the expired state for a link with %s, and sends nothing', async (_, query) => {
    const sent = recordGoTrue()
    landOn(query)

    renderWithProviders(<ResetPasswordScreen />, { messages: viMessages })

    expect(
      screen.getByRole('heading', {
        name: expected(viMessages.auth.verify_confirm_expired_heading),
      }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: expected(viMessages.auth.reset_password_request_new) }),
    ).toHaveAttribute('href', '/vi/forgot-password')
    expect(
      screen.queryByLabelText(expected(viMessages.auth.reset_password_new_password)),
    ).not.toBeInTheDocument()
    await settle()
    expect(sent).toEqual([])
  })

  it('reads in the reader’s locale, with the URL’s locale on every link', async () => {
    recordGoTrue({ verify: () => otpExpired() })
    landOn(LINK)

    renderWithProviders(<ResetPasswordScreen />, { locale: 'en', messages: enMessages })
    typePassword(enMessages, NEW_PASSWORD)
    submit(enMessages)

    await screen.findByRole('heading', {
      name: expected(enMessages.auth.verify_confirm_expired_heading),
    })
    expect(
      screen.getByRole('link', { name: expected(enMessages.auth.reset_password_request_new) }),
    ).toHaveAttribute('href', '/en/forgot-password')
  })
})
