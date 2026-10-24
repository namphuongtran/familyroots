import { fireEvent, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { components } from '@/generated/api-types'
import { envelope, server } from '@/shared/testing/msw'
import { renderWithProviders } from '@/shared/testing/render'
import { useSession } from '../hooks/use-session'
import { RegisterScreen } from './RegisterScreen'
import messages from '../../../../messages/vi.json'
import enMessages from '../../../../messages/en.json'
import frMessages from '../../../../messages/fr.json'
import zhMessages from '../../../../messages/zh.json'

/**
 * #291, ADR-075: the clan step is onboarding's, and it opens on **create**. A signed-in person
 * with no membership lands on `/{locale}/register?mode=oauth` (`model/landing.ts`), whether they
 * signed up with a password or arrived from Google, and production had no clan to join. Joining by
 * code stays one choice away, the secondary path ADR-057 made it.
 *
 * **What this reads is the request the form sends**, `POST /auth/onboard`'s body as the backend
 * would receive it (`.claude/rules/testing.md`, "A test pins an outcome, not a setting"). The real
 * `useAuthActions` and repository run against MSW. Only `useSession` is replaced, with a session
 * in the needs-onboarding state, because the form renders its clan step only for a signed-in
 * person and jsdom has no Supabase to sign in against. The actions keep the real
 * `sessionQueryOptions`: with no Supabase env there is no token, so the session they fetch after
 * onboarding is none, and the router mock takes the push.
 */

const searchParams = vi.hoisted(() => ({ current: new URLSearchParams('mode=oauth') }))

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  useSearchParams: () => searchParams.current,
}))

vi.mock('../hooks/use-session', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../hooks/use-session')>()),
  useSession: vi.fn(),
}))

const CLAN_ID = 'aaaaaaaa-0000-4000-8000-000000000001'

/** A person who registered with a password, confirmed, and signed in, holding no membership. */
function signedInWithNoClan(): void {
  vi.mocked(useSession).mockReturnValue({
    session: { profile: { fullName: 'Trần Văn A', email: 'a@example.com' }, memberships: [] },
    access: { kind: 'needs-onboarding' },
    activeClan: null,
    isLoading: false,
  } as unknown as ReturnType<typeof useSession>)
}

/** Serves the real 201 and the profile save, and returns every onboard body the form sent. */
function onboardAnswers201(): Record<string, unknown>[] {
  const bodies: Record<string, unknown>[] = []
  server.use(
    http.patch('*/api/v1/auth/me', () => HttpResponse.json(envelope({ message: 'ok' }))),
    http.post('*/api/v1/auth/onboard', async ({ request }) => {
      bodies.push((await request.json()) as Record<string, unknown>)
      return HttpResponse.json(
        envelope({
          user_id: '11111111-1111-4111-8111-111111111111',
          email: 'a@example.com',
          full_name: 'Trần Văn A',
          clan_id: CLAN_ID,
          is_approved: true,
          message: 'ok',
        } satisfies components['schemas']['RegisterResponse']),
        { status: 201 },
      )
    }),
  )
  return bodies
}

function completeSetup(): void {
  fireEvent.click(screen.getByRole('button', { name: messages.auth.complete_onboarding }))
}

describe('onboarding: the clan step opens on create', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    signedInWithNoClan()
  })

  it('has create chosen, with the clan name and code fields and no join code', () => {
    renderWithProviders(<RegisterScreen />, { messages })

    expect(screen.getByRole('radio', { name: messages.auth.create_clan })).toBeChecked()
    expect(screen.getByRole('radio', { name: messages.auth.join_clan })).not.toBeChecked()
    expect(screen.getByLabelText(messages.auth.clan_name)).toBeInTheDocument()
    expect(screen.queryByText(messages.auth.clan_slug_join_helper)).not.toBeInTheDocument()
  })

  it('a clan name alone is enough: it sends create with the name and the derived code', async () => {
    const bodies = onboardAnswers201()
    renderWithProviders(<RegisterScreen />, { messages })

    fireEvent.change(screen.getByLabelText(messages.auth.clan_name), {
      target: { value: 'Trần Gia' },
    })
    completeSetup()

    await waitFor(() => expect(bodies).toHaveLength(1))
    expect(bodies[0]).toEqual({
      clan_action: 'create',
      clan_name: 'Trần Gia',
      clan_slug: 'tran-gia',
    })
  })

  it('join is one choice away, and sends the code it was given', async () => {
    const bodies = onboardAnswers201()
    renderWithProviders(<RegisterScreen />, { messages })

    fireEvent.click(screen.getByRole('radio', { name: messages.auth.join_clan }))
    fireEvent.change(screen.getByLabelText(messages.auth.clan_slug), {
      target: { value: 'nguyen-phuc' },
    })
    completeSetup()

    await waitFor(() => expect(bodies).toHaveLength(1))
    expect(bodies[0]).toEqual({ clan_action: 'join', clan_code: 'nguyen-phuc' })
  })
})

/**
 * The screen used to open on "Bạn đã đăng nhập bằng Google", which every person who needs
 * onboarding read, a password sign-up included. Since ADR-075 every password sign-up does. The
 * product name is the one word that may stay, so the reading is the provider's name.
 */
describe('onboarding: the screen names no sign-in provider', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    signedInWithNoClan()
  })

  it.each([
    ['vi', messages],
    ['en', enMessages],
    ['zh', zhMessages],
    ['fr', frMessages],
  ] as const)('in %s', (locale, intl) => {
    const { container } = renderWithProviders(<RegisterScreen />, { locale, messages: intl })

    expect(screen.getByRole('button', { name: intl.auth.complete_onboarding })).toBeInTheDocument()
    expect(container.textContent).not.toMatch(/Google/)
  })
})
