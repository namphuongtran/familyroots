import { fireEvent, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { components } from '@/generated/api-types'
import { createClientOrNull } from '@/shared/supabase/client'
import { clearClanCookie, readCurrentClanId } from '@/shared/http/context.client'
import { envelope, server } from '@/shared/testing/msw'
import { renderWithProviders } from '@/shared/testing/render'
import { fakeSupabaseClient, type FakeSupabaseOptions } from '@/shared/testing/supabase'
import { LoginScreen } from './LoginScreen'
import messages from '../../../../messages/vi.json'

/**
 * #183, verification 5, and where a sign-in lands. The real `useAuthActions` runs: the Supabase
 * browser client is a fake, and the session it then reads comes from MSW.
 *
 * Sign-in stays Supabase-direct (ADR-061 § 7), so an account whose email is not confirmed is
 * refused by Supabase with the code `email_not_confirmed`, never by the backend's `403
 * email_not_verified`. That code is what routes to `/verify-email`.
 */

const push = vi.fn()
vi.mock('next/navigation', () => ({ useRouter: () => ({ push, replace: vi.fn() }) }))
vi.mock('@/shared/supabase/client', () => ({ createClientOrNull: vi.fn() }))

const API = `${process.env.NEXT_PUBLIC_API_ORIGIN ?? 'http://localhost:8000'}/api/v1`
const CLAN_A = 'aaaaaaaa-0000-4000-8000-000000000001'

function profile(
  overrides: Partial<components['schemas']['UserProfile']> = {},
): components['schemas']['UserProfile'] {
  return {
    id: '11111111-1111-4111-8111-111111111111',
    email: 'lan@example.com',
    full_name: 'Nguyễn Thị Lan',
    clan_id: null,
    clan_name: null,
    role: null,
    is_approved: false,
    has_pending_membership: false,
    person_id: null,
    preferred_locale: 'vi',
    platform_role: 'user',
    ...overrides,
  }
}

function serveSession(
  me: components['schemas']['UserProfile'],
  clans: components['schemas']['UserClanMembership'][],
) {
  server.use(
    http.get(`${API}/auth/me`, () => HttpResponse.json(envelope(me))),
    http.get(`${API}/me/clans`, () => HttpResponse.json(envelope(clans))),
  )
}

function renderWithSupabase(options: FakeSupabaseOptions = {}) {
  const fake = fakeSupabaseClient(options)
  vi.mocked(createClientOrNull).mockReturnValue(fake.client as never)
  renderWithProviders(<LoginScreen />, { messages })
  return fake
}

function signIn(email = 'lan@example.com') {
  fireEvent.change(screen.getByLabelText(messages.auth.email), { target: { value: email } })
  fireEvent.change(screen.getByLabelText(messages.auth.password), {
    target: { value: 'correct horse battery' },
  })
  fireEvent.click(screen.getByRole('button', { name: messages.auth.sign_in }))
}

beforeEach(() => push.mockReset())
afterEach(() => clearClanCookie())

describe('signing in with an email Supabase has not confirmed', () => {
  it('goes to /vi/verify-email with the address, and shows no error', async () => {
    const fake = renderWithSupabase({
      signInError: { code: 'email_not_confirmed', message: 'Email not confirmed', status: 400 },
    })

    signIn('lan@example.com')

    await waitFor(() =>
      expect(push).toHaveBeenCalledWith('/vi/verify-email?email=lan%40example.com'),
    )
    expect(fake.auth.signInWithPassword).toHaveBeenCalledWith({
      email: 'lan@example.com',
      password: 'correct horse battery',
    })
    expect(screen.queryByText('Email not confirmed')).not.toBeInTheDocument()
  })

  it('any other refusal stays on the form and shows what Supabase said', async () => {
    renderWithSupabase({
      signInError: {
        code: 'invalid_credentials',
        message: 'Invalid login credentials',
        status: 400,
      },
    })

    signIn()

    expect(await screen.findByText('Invalid login credentials')).toBeInTheDocument()
    expect(push).not.toHaveBeenCalled()
  })
})

describe('where a sign-in lands', () => {
  it('a member of one clan lands on the dashboard, with that clan in the cookie', async () => {
    serveSession(profile({ clan_id: CLAN_A, role: 'admin', is_approved: true }), [
      { clan_id: CLAN_A, clan_name: 'Nguyễn Phúc', clan_slug: 'nguyen-phuc', role: 'admin' },
    ])
    renderWithSupabase()

    signIn()

    await waitFor(() => expect(push).toHaveBeenCalledWith('/vi/dashboard'))
    expect(readCurrentClanId()).toBe(CLAN_A)
  })

  it('a pending account lands on /pending-approval', async () => {
    serveSession(profile({ has_pending_membership: true }), [])
    renderWithSupabase()

    signIn()

    await waitFor(() => expect(push).toHaveBeenCalledWith('/vi/pending-approval'))
    expect(readCurrentClanId()).toBeNull()
  })

  it('a super_admin with no membership lands on the platform', async () => {
    serveSession(profile({ platform_role: 'super_admin' }), [])
    renderWithSupabase()

    signIn()

    await waitFor(() => expect(push).toHaveBeenCalledWith('/vi/platform/clans'))
  })
})
