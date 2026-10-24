import { screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { server } from '@/shared/testing/msw'
import { expected, renderWithProviders } from '@/shared/testing/render'
import { gotrueSettings } from '@/shared/testing/supabase'
import { RegisterScreen } from './RegisterScreen'
import messages from '../../../../messages/vi.json'

/**
 * #290, the register half: "Continue with Google" is offered only while GoTrue's
 * `GET /auth/v1/settings` reports `external.google` true. `LoginScreen.test.tsx` holds the
 * failed-read case for the shared hook.
 *
 * Mocks only `next/navigation`, as `RegisterScreen.invitee.test.tsx` does. Supabase is not
 * mocked: with no stored session the browser client asks GoTrue for nothing but the settings.
 */

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}))

const SUPABASE = 'https://register-oauth-test.supabase.co'

function serveSettings(google: boolean): { reads: () => number } {
  let reads = 0
  server.use(
    http.get(`${SUPABASE}/auth/v1/settings`, () => {
      reads += 1
      return HttpResponse.json(gotrueSettings({ google }))
    }),
  )
  return { reads: () => reads }
}

afterEach(() => vi.unstubAllEnvs())

describe('the register screen’s Google button', () => {
  const name = () => expected(messages.auth.google_register)

  it('is offered when GoTrue reports Google on', async () => {
    vi.stubEnv('NEXT_PUBLIC_SUPABASE_URL', SUPABASE)
    vi.stubEnv('NEXT_PUBLIC_SUPABASE_ANON_KEY', 'test-anon-key')
    serveSettings(true)
    renderWithProviders(<RegisterScreen />, { messages })

    expect(await screen.findByRole('button', { name: name() })).toBeInTheDocument()
  })

  it('is not offered when GoTrue reports Google off', async () => {
    vi.stubEnv('NEXT_PUBLIC_SUPABASE_URL', SUPABASE)
    vi.stubEnv('NEXT_PUBLIC_SUPABASE_ANON_KEY', 'test-anon-key')
    const settings = serveSettings(false)
    const { queryClient } = renderWithProviders(<RegisterScreen />, { messages })

    // Parsed, not only sent: an absent button is then the answer, not a read in flight.
    await waitFor(() =>
      expect(queryClient.getQueryState(['auth', 'oauth-providers'])?.status).toBe('success'),
    )
    expect(settings.reads()).toBe(1)
    expect(screen.getByRole('button', { name: messages.auth.register })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: name() })).not.toBeInTheDocument()
  })
})
